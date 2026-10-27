//! The hooked stdio, directory and file-system functions (`swoole_coroutine_fopen`,
//! `swoole_coroutine_stat`, …): inside a coroutine each libc call runs on the async
//! thread pool while the coroutine waits; outside one it runs here. Native code passes
//! its `async` as `Offload` (null outside a coroutine), which also restores the
//! worker's errno.
use libc::{
    DIR, FILE, c_char, c_int, c_uint, c_void, dirent, mode_t, off_t, size_t, ssize_t, stat, statvfs,
};

/// Runs `job(context)` on the async pool and parks the coroutine until it is done;
/// false if the pool refused it.
pub type Offload = unsafe extern "C" fn(unsafe extern "C" fn(*mut c_void), *mut c_void) -> bool;

/// `call()` here without `offload`, else on the pool; `refused` if the pool refuses.
///
/// # Safety
/// `offload` is native's `async`, valid in the current coroutine. `call` runs on a
/// pool thread while this frame waits, so it may only touch what the caller lent.
unsafe fn offloaded<T, F: FnMut() -> T>(offload: Option<Offload>, refused: T, call: F) -> T {
    struct Job<F, T> {
        call: F,
        result: Option<T>,
    }
    unsafe extern "C" fn run<F: FnMut() -> T, T>(job: *mut c_void) {
        // SAFETY: `offloaded` passes its own `Job<F, T>`, alive until `offload` returns.
        let job = unsafe { &mut *job.cast::<Job<F, T>>() };
        job.result = Some((job.call)());
    }
    let mut call = call;
    let Some(offload) = offload else {
        return call();
    };
    let mut job = Job { call, result: None };
    // SAFETY: `run` matches `job`'s type; the caller passes native `async`.
    unsafe { offload(run::<F, T>, (&raw mut job).cast()) };
    job.result.unwrap_or(refused)
}

macro_rules! hooked {
    ($($name:ident($($arg:ident: $ty:ty),*) -> $ret:ty, refused $refused:expr => $call:expr;)*) => {$(
        #[doc = concat!("Hooked `", stringify!($call), "`.")]
        ///
        /// # Safety
        /// The arguments are valid for the libc call; `offload` as in [`Offload`].
        #[unsafe(no_mangle)]
        pub unsafe extern "C" fn $name($($arg: $ty,)* offload: Option<Offload>) -> $ret {
            // SAFETY: the caller's arguments are valid for the libc call.
            let call = || unsafe { $call };
            // SAFETY: the caller passes native `async` or null.
            unsafe { offloaded(offload, $refused, call) }
        }
    )*};
}

/// `fdatasync` where libc has it (`HAVE_FDATASYNC`), else `fsync`.
///
/// # Safety
/// As for `fsync`.
unsafe fn datasync(fd: c_int) -> c_int {
    #[cfg(target_os = "linux")]
    // SAFETY: as for fsync.
    return unsafe { libc::fdatasync(fd) };
    #[cfg(not(target_os = "linux"))]
    // SAFETY: as above.
    return unsafe { libc::fsync(fd) };
}

hooked! {
    swr_v1_hook_fopen(pathname: *const c_char, mode: *const c_char) -> *mut FILE, refused std::ptr::null_mut() => libc::fopen(pathname, mode);
    swr_v1_hook_fdopen(fd: c_int, mode: *const c_char) -> *mut FILE, refused std::ptr::null_mut() => libc::fdopen(fd, mode);
    swr_v1_hook_freopen(pathname: *const c_char, mode: *const c_char, stream: *mut FILE) -> *mut FILE, refused std::ptr::null_mut() => libc::freopen(pathname, mode, stream);
    swr_v1_hook_fread(ptr: *mut c_void, size: size_t, nmemb: size_t, stream: *mut FILE) -> size_t, refused 0 => libc::fread(ptr, size, nmemb, stream);
    swr_v1_hook_fwrite(ptr: *const c_void, size: size_t, nmemb: size_t, stream: *mut FILE) -> size_t, refused 0 => libc::fwrite(ptr, size, nmemb, stream);
    swr_v1_hook_fgets(s: *mut c_char, size: c_int, stream: *mut FILE) -> *mut c_char, refused std::ptr::null_mut() => libc::fgets(s, size, stream);
    swr_v1_hook_fputs(s: *const c_char, stream: *mut FILE) -> c_int, refused -1 => libc::fputs(s, stream);
    swr_v1_hook_feof(stream: *mut FILE) -> c_int, refused -1 => libc::feof(stream);
    swr_v1_hook_fflush(stream: *mut FILE) -> c_int, refused -1 => libc::fflush(stream);
    swr_v1_hook_fclose(stream: *mut FILE) -> c_int, refused -1 => libc::fclose(stream);
    swr_v1_hook_opendir(name: *const c_char) -> *mut DIR, refused std::ptr::null_mut() => libc::opendir(name);
    swr_v1_hook_readdir(dirp: *mut DIR) -> *mut dirent, refused std::ptr::null_mut() => libc::readdir(dirp);
    swr_v1_hook_closedir(dirp: *mut DIR) -> c_int, refused -1 => libc::closedir(dirp);
    swr_v1_hook_open(pathname: *const c_char, flags: c_int, mode: mode_t) -> c_int, refused -1 => libc::open(pathname, flags, c_uint::from(mode));
    swr_v1_hook_fstat(fd: c_int, statbuf: *mut stat) -> c_int, refused -1 => libc::fstat(fd, statbuf);
    swr_v1_hook_stat(path: *const c_char, statbuf: *mut stat) -> c_int, refused -1 => libc::stat(path, statbuf);
    swr_v1_hook_lstat(path: *const c_char, statbuf: *mut stat) -> c_int, refused -1 => libc::lstat(path, statbuf);
    swr_v1_hook_unlink(pathname: *const c_char) -> c_int, refused -1 => libc::unlink(pathname);
    swr_v1_hook_mkdir(pathname: *const c_char, mode: mode_t) -> c_int, refused -1 => libc::mkdir(pathname, mode);
    swr_v1_hook_rmdir(pathname: *const c_char) -> c_int, refused -1 => libc::rmdir(pathname);
    swr_v1_hook_rename(oldpath: *const c_char, newpath: *const c_char) -> c_int, refused -1 => libc::rename(oldpath, newpath);
    swr_v1_hook_fsync(fd: c_int) -> c_int, refused -1 => libc::fsync(fd);
    swr_v1_hook_fdatasync(fd: c_int) -> c_int, refused -1 => datasync(fd);
    swr_v1_hook_ftruncate(fd: c_int, length: off_t) -> c_int, refused -1 => libc::ftruncate(fd, length);
    swr_v1_hook_lseek(fd: c_int, offset: off_t, whence: c_int) -> off_t, refused -1 => libc::lseek(fd, offset, whence);
    swr_v1_hook_readlink(pathname: *const c_char, buf: *mut c_char, len: size_t) -> ssize_t, refused -1 => libc::readlink(pathname, buf, len);
    swr_v1_hook_statvfs(path: *const c_char, buf: *mut statvfs) -> c_int, refused -1 => libc::statvfs(path, buf);
    swr_v1_hook_access(pathname: *const c_char, mode: c_int) -> c_int, refused -1 => libc::access(pathname, mode);
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::Cell;
    use std::ffi::CString;

    thread_local! {
        static OFFLOADED: Cell<u32> = const { Cell::new(0) };
    }
    /// Runs the job on another thread, as the pool would.
    unsafe extern "C" fn pool(
        job: unsafe extern "C" fn(*mut c_void),
        context: *mut c_void,
    ) -> bool {
        OFFLOADED.set(OFFLOADED.get() + 1);
        let context = context as usize;
        std::thread::spawn(move || unsafe { job(context as *mut c_void) })
            .join()
            .unwrap();
        true
    }
    unsafe extern "C" fn refuse(_: unsafe extern "C" fn(*mut c_void), _: *mut c_void) -> bool {
        false
    }

    #[test]
    fn runs_here_or_on_the_pool() {
        let path = std::env::temp_dir().join(format!("swr-stdio-{}", std::process::id()));
        let name = CString::new(path.to_str().unwrap()).unwrap();
        unsafe {
            let file = swr_v1_hook_fopen(name.as_ptr(), c"w".as_ptr(), Some(pool));
            assert!(!file.is_null());
            assert_eq!(
                swr_v1_hook_fwrite(b"line\n".as_ptr().cast(), 1, 5, file, Some(pool)),
                5
            );
            assert_eq!(swr_v1_hook_fclose(file, None), 0);

            let file = swr_v1_hook_fopen(name.as_ptr(), c"r".as_ptr(), None);
            let mut buffer = [0 as c_char; 16];
            assert!(!swr_v1_hook_fgets(buffer.as_mut_ptr(), 16, file, Some(pool)).is_null());
            assert_eq!(std::ffi::CStr::from_ptr(buffer.as_ptr()), c"line\n");
            assert_eq!(swr_v1_hook_feof(file, Some(pool)), 0);
            assert_eq!(
                swr_v1_hook_fgets(buffer.as_mut_ptr(), 16, file, Some(pool)),
                std::ptr::null_mut()
            );
            assert_ne!(swr_v1_hook_feof(file, Some(pool)), 0);
            assert_eq!(swr_v1_hook_feof(file, Some(refuse)), -1);
            assert_eq!(swr_v1_hook_fclose(file, Some(pool)), 0);

            let dir = CString::new(std::env::temp_dir().to_str().unwrap()).unwrap();
            let dirp = swr_v1_hook_opendir(dir.as_ptr(), Some(pool));
            assert!(!swr_v1_hook_readdir(dirp, Some(pool)).is_null());
            assert_eq!(swr_v1_hook_closedir(dirp, Some(pool)), 0);
            assert_eq!(
                swr_v1_hook_opendir(c"/nonexistent-swr".as_ptr(), Some(refuse)),
                std::ptr::null_mut()
            );
        }
        assert_eq!(OFFLOADED.get(), 10);
        std::fs::remove_file(path).unwrap();
    }

    #[test]
    fn file_system_calls_on_the_pool() {
        let base = std::env::temp_dir().join(format!("swr-fs-{}", std::process::id()));
        let (dir, moved) = (
            CString::new(base.to_str().unwrap()).unwrap(),
            CString::new(format!("{}-moved", base.to_str().unwrap())).unwrap(),
        );
        let file = CString::new(format!("{}-moved/file", base.to_str().unwrap())).unwrap();
        unsafe {
            assert_eq!(swr_v1_hook_mkdir(dir.as_ptr(), 0o700, Some(pool)), 0);
            assert_eq!(
                swr_v1_hook_rename(dir.as_ptr(), moved.as_ptr(), Some(pool)),
                0
            );
            assert_eq!(
                swr_v1_hook_access(moved.as_ptr(), libc::W_OK, Some(pool)),
                0
            );
            let fd = swr_v1_hook_open(
                file.as_ptr(),
                libc::O_CREAT | libc::O_WRONLY,
                0o600,
                Some(pool),
            );
            assert!(fd >= 0);
            assert_eq!(swr_v1_hook_ftruncate(fd, 9, Some(pool)), 0);
            assert_eq!(swr_v1_hook_lseek(fd, 0, libc::SEEK_END, Some(pool)), 9);
            assert_eq!(swr_v1_hook_fdatasync(fd, Some(pool)), 0);
            let mut info: stat = std::mem::zeroed();
            assert_eq!(swr_v1_hook_fstat(fd, &raw mut info, Some(pool)), 0);
            assert_eq!(info.st_size, 9);
            assert_eq!(libc::close(fd), 0);
            assert_eq!(swr_v1_hook_stat(file.as_ptr(), &raw mut info, None), 0);
            assert_eq!(swr_v1_hook_unlink(file.as_ptr(), Some(pool)), 0);
            assert_eq!(
                swr_v1_hook_lstat(file.as_ptr(), &raw mut info, Some(pool)),
                -1
            );
            assert_eq!(swr_v1_hook_rmdir(moved.as_ptr(), Some(pool)), 0);
            assert_eq!(swr_v1_hook_rmdir(moved.as_ptr(), Some(refuse)), -1);
        }
    }
}
