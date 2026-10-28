//! `Server::task_unpack` for a task too large for the pipe: its payload is in a
//! temporary file. Open it, read `length` bytes into the native buffer (`File::read_all`:
//! pread from offset 0, retrying EINTR/EAGAIN, stopping at EOF or another error),
//! close it and unlink it unless the task is only peeked. Native code keeps sizing the
//! buffer, the warnings and the packet.
use std::ffi::{CStr, c_char, c_int};

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

/// `SW_TASK_TMP_PATH_SIZE`.
const TASK_TMP_PATH_SIZE: usize = 256;

/// The payload descriptor written into `EventData::data` when a task spills to a
/// temp file (matches `swoole::PacketTask`).
#[repr(C)]
struct PacketTask {
    length: usize,
    tmpfile: [u8; TASK_TMP_PATH_SIZE],
}

/// What packing a task payload did.
#[repr(C)]
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct TaskPack {
    /// false on a temp-file create or write failure.
    pub ok: bool,
    /// true when the payload spilled to a temp file and `dest` holds a `PacketTask`.
    pub tmpfile: bool,
    /// The byte count for `info.len`: the payload length, or `sizeof(PacketTask)`.
    pub info_len: usize,
}

fn write_all(fd: c_int, data: *const u8, len: usize) -> bool {
    let mut written = 0;
    while written < len {
        // SAFETY: `data` lends `len` readable bytes and `written < len`.
        let rest = unsafe { data.add(written) };
        // SAFETY: `fd` is open; `rest` lends `len - written` readable bytes.
        let n = unsafe { libc::write(fd, rest.cast(), len - written) };
        if let Ok(n @ 1..) = usize::try_from(n) {
            written += n;
            continue;
        }
        let error = errno();
        if n < 0 && [libc::EINTR, libc::EAGAIN, libc::EWOULDBLOCK].contains(&error) {
            continue;
        }
        return false;
    }
    true
}

/// mkstemp (mkostemp on Linux, matching `swoole_tmpfile`) over the pattern in `buf`,
/// which is rewritten in place to the created path. Returns the fd, or negative.
fn make_tmpfile(buf: &mut [u8; TASK_TMP_PATH_SIZE]) -> c_int {
    let pattern = buf.as_mut_ptr().cast::<c_char>();
    #[cfg(target_os = "linux")]
    // SAFETY: `pattern` is a NUL-terminated mkstemp pattern buffer in `buf`.
    let fd = unsafe { libc::mkostemp(pattern, libc::O_WRONLY | libc::O_CREAT) };
    #[cfg(not(target_os = "linux"))]
    // SAFETY: `pattern` is a NUL-terminated mkstemp pattern buffer in `buf`.
    let fd = unsafe { libc::mkstemp(pattern) };
    fd
}

/// `Server::task_pack`'s payload placement: inline into `dest` when it fits in
/// `dest_cap`, otherwise a temp file created from `template` (an mkstemp pattern),
/// whose path and length are written into `dest` as a `PacketTask`. Native builds
/// the `EventData` header and sets its `len`/flag from the result; the Zend
/// serialization of the PHP value stays native.
///
/// # Safety
/// `dest` is writable for `dest_cap` bytes (at least `sizeof(PacketTask)` for the
/// temp-file case); `data` lends `len` readable bytes; `template` is a
/// NUL-terminated mkstemp pattern.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_process_task_pack(
    dest: *mut u8,
    dest_cap: usize,
    data: *const u8,
    len: usize,
    template: *const c_char,
) -> TaskPack {
    if len < dest_cap {
        // SAFETY: `dest` lends `dest_cap > len` writable bytes; `data` lends `len`.
        unsafe { std::ptr::copy_nonoverlapping(data, dest, len) };
        return TaskPack {
            ok: true,
            tmpfile: false,
            info_len: len,
        };
    }
    let mut pkg = PacketTask {
        length: len,
        tmpfile: [0; TASK_TMP_PATH_SIZE],
    };
    // SAFETY: `template` is a NUL-terminated string.
    let pattern = unsafe { CStr::from_ptr(template) }.to_bytes();
    if pattern.len() >= pkg.tmpfile.len() {
        return TaskPack::default();
    }
    for (byte, &pattern) in pkg.tmpfile.iter_mut().zip(pattern) {
        *byte = pattern;
    }
    let fd = make_tmpfile(&mut pkg.tmpfile);
    if fd < 0 {
        return TaskPack::default();
    }
    let wrote = write_all(fd, data, len);
    // SAFETY: `fd` is open and owned here.
    unsafe { libc::close(fd) };
    if !wrote {
        return TaskPack::default();
    }
    // SAFETY: `dest` lends `dest_cap` (>= sizeof(PacketTask)) bytes; copy the POD's bytes.
    unsafe {
        std::ptr::copy_nonoverlapping((&raw const pkg).cast::<u8>(), dest, size_of::<PacketTask>());
    }
    TaskPack {
        ok: true,
        tmpfile: true,
        info_len: size_of::<PacketTask>(),
    }
}

#[cfg(test)]
mod tests {
    use super::{
        PacketTask, TaskFileRead, TaskPack, swr_v1_process_task_file_read, swr_v1_process_task_pack,
    };
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

    #[test]
    fn packs_a_small_payload_inline() {
        let data = b"a small task payload";
        let mut dest = vec![0u8; 300];
        let template = CString::new("/unused/XXXXXX").unwrap();
        let out = unsafe {
            swr_v1_process_task_pack(
                dest.as_mut_ptr(),
                dest.len(),
                data.as_ptr(),
                data.len(),
                template.as_ptr(),
            )
        };
        assert_eq!(
            out,
            TaskPack {
                ok: true,
                tmpfile: false,
                info_len: data.len()
            }
        );
        assert_eq!(&dest[..data.len()], data);
    }

    #[test]
    fn packs_a_large_payload_to_a_temp_file() {
        let template = CString::new(
            std::env::temp_dir()
                .join(format!("swr-pack-{}-XXXXXX", std::process::id()))
                .to_str()
                .unwrap(),
        )
        .unwrap();
        let payload = vec![0xAB_u8; 500];
        let mut dest = vec![0u8; 300]; // smaller than the payload, so it spills to a file
        let out = unsafe {
            swr_v1_process_task_pack(
                dest.as_mut_ptr(),
                dest.len(),
                payload.as_ptr(),
                payload.len(),
                template.as_ptr(),
            )
        };
        assert_eq!(
            out,
            TaskPack {
                ok: true,
                tmpfile: true,
                info_len: size_of::<PacketTask>()
            }
        );
        // Decode the PacketTask { length, tmpfile } written into dest by byte offset.
        let length = usize::from_ne_bytes(dest[..size_of::<usize>()].try_into().unwrap());
        assert_eq!(length, payload.len());
        let path_bytes = &dest[size_of::<usize>()..];
        let nul = path_bytes.iter().position(|&b| b == 0).unwrap();
        let path = std::str::from_utf8(&path_bytes[..nul]).unwrap();
        assert_eq!(std::fs::read(path).unwrap(), payload);
        std::fs::remove_file(path).ok();
    }
}
