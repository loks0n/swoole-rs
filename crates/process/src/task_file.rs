//! `Server::task_unpack` for a task too large for the pipe: its payload is in a
//! temporary file. Open it, read `length` bytes into the native buffer (`File::read_all`:
//! pread from offset 0, retrying EINTR/EAGAIN, stopping at EOF or another error),
//! close it and unlink it unless the task is only peeked. Native code keeps sizing the
//! buffer, the warnings and the packet.
use std::ffi::{CStr, c_char};

/// What reading a task's temporary file did.
#[repr(C)]
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct TaskFileRead {
    /// 0 read and (unless peeking) unlinked; 1 open failed; 2 short read at EOF;
    /// 3 pread failed after `read` bytes.
    pub status: u32,
    /// The errno of status 1 and 3.
    pub error: i32,
    /// The descriptor that status 3's pread used.
    pub fd: i32,
    /// Bytes read.
    pub read: usize,
}

fn errno() -> i32 {
    std::io::Error::last_os_error().raw_os_error().unwrap_or(0)
}

/// Reads `length` bytes of the file at `path` into `buffer`.
///
/// # Safety
/// `path` is a NUL-terminated string and `buffer` is writable for `length` bytes.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_process_task_file_read(
    path: *const c_char,
    buffer: *mut u8,
    length: usize,
    peek: bool,
) -> TaskFileRead {
    // SAFETY: the caller passes a NUL-terminated path.
    let path = unsafe { CStr::from_ptr(path) };
    // SAFETY: `path` is NUL-terminated.
    let fd = unsafe { libc::open(path.as_ptr(), libc::O_RDONLY) };
    if fd < 0 {
        return TaskFileRead {
            status: 1,
            error: errno(),
            fd,
            read: 0,
        };
    }
    let mut outcome = TaskFileRead {
        fd,
        ..TaskFileRead::default()
    };
    while outcome.read < length {
        let Ok(offset) = libc::off_t::try_from(outcome.read) else {
            break;
        };
        // SAFETY: `buffer` is writable for `length` bytes and `read < length`.
        let rest = unsafe { buffer.add(outcome.read) };
        // SAFETY: `rest` is writable for `length - read` bytes and `fd` is open.
        let n = unsafe { libc::pread(fd, rest.cast(), length - outcome.read, offset) };
        if let Ok(n @ 1..) = usize::try_from(n) {
            outcome.read += n;
            continue;
        }
        let error = errno();
        if n < 0 && [libc::EINTR, libc::EAGAIN, libc::EWOULDBLOCK].contains(&error) {
            continue;
        }
        (outcome.status, outcome.error) = if n == 0 { (2, 0) } else { (3, error) };
        break;
    }
    // SAFETY: `fd` is open and owned here.
    unsafe { libc::close(fd) };
    if outcome.status == 0 && outcome.read == length && !peek {
        // SAFETY: `path` is NUL-terminated.
        unsafe { libc::unlink(path.as_ptr()) };
    }
    outcome
}

#[cfg(test)]
mod tests {
    use super::{TaskFileRead, swr_v1_process_task_file_read};
    use std::ffi::CString;

    fn read(path: &CString, length: usize, peek: bool) -> (TaskFileRead, Vec<u8>) {
        let mut buffer = vec![0; length];
        let outcome = unsafe {
            swr_v1_process_task_file_read(path.as_ptr(), buffer.as_mut_ptr(), length, peek)
        };
        (outcome, buffer)
    }

    #[test]
    fn reads_then_unlinks_unless_peeking() {
        let file = std::env::temp_dir().join(format!("swr-task-{}", std::process::id()));
        std::fs::write(&file, b"payload").unwrap();
        let path = CString::new(file.to_str().unwrap()).unwrap();

        let (outcome, data) = read(&path, 7, true);
        assert_eq!(
            (outcome.status, outcome.read, data.as_slice()),
            (0, 7, &b"payload"[..])
        );
        assert!(file.exists());

        let (outcome, _) = read(&path, 9, false);
        assert_eq!((outcome.status, outcome.read), (2, 7));
        assert!(file.exists());

        let (outcome, _) = read(&path, 7, false);
        assert_eq!(outcome.status, 0);
        assert!(!file.exists());

        let (outcome, _) = read(&path, 7, false);
        assert_eq!((outcome.status, outcome.error), (1, libc::ENOENT));
    }
}
