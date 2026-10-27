//! The hooked stdio and directory functions (`swoole_coroutine_fopen` …
//! `swoole_coroutine_closedir`): inside a coroutine each libc call runs on the async
//! thread pool while the coroutine waits; outside one it runs here. Native code passes
//! its `async` as `Offload` (null outside a coroutine), which also restores the
//! worker's errno.
use libc::{DIR, FILE, c_char, c_int, c_void, dirent, size_t};

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
    ($($name:ident => $libc:ident($($arg:ident: $ty:ty),*) -> $ret:ty, refused $refused:expr;)*) => {$(
        #[doc = concat!("`swoole_coroutine_", stringify!($libc), "`.")]
        ///
        /// # Safety
        /// The arguments are valid for the libc call; `offload` as in [`Offload`].
        #[unsafe(no_mangle)]
        pub unsafe extern "C" fn $name($($arg: $ty,)* offload: Option<Offload>) -> $ret {
            // SAFETY: the caller's arguments are valid for the libc call.
            let call = || unsafe { libc::$libc($($arg),*) };
            // SAFETY: the caller passes native `async` or null.
            unsafe { offloaded(offload, $refused, call) }
        }
    )*};
}

hooked! {
    swr_v1_hook_fopen => fopen(pathname: *const c_char, mode: *const c_char) -> *mut FILE, refused std::ptr::null_mut();
    swr_v1_hook_fdopen => fdopen(fd: c_int, mode: *const c_char) -> *mut FILE, refused std::ptr::null_mut();
    swr_v1_hook_freopen => freopen(pathname: *const c_char, mode: *const c_char, stream: *mut FILE) -> *mut FILE, refused std::ptr::null_mut();
    swr_v1_hook_fread => fread(ptr: *mut c_void, size: size_t, nmemb: size_t, stream: *mut FILE) -> size_t, refused 0;
    swr_v1_hook_fwrite => fwrite(ptr: *const c_void, size: size_t, nmemb: size_t, stream: *mut FILE) -> size_t, refused 0;
    swr_v1_hook_fgets => fgets(s: *mut c_char, size: c_int, stream: *mut FILE) -> *mut c_char, refused std::ptr::null_mut();
    swr_v1_hook_fputs => fputs(s: *const c_char, stream: *mut FILE) -> c_int, refused -1;
    swr_v1_hook_feof => feof(stream: *mut FILE) -> c_int, refused -1;
    swr_v1_hook_fflush => fflush(stream: *mut FILE) -> c_int, refused -1;
    swr_v1_hook_fclose => fclose(stream: *mut FILE) -> c_int, refused -1;
    swr_v1_hook_opendir => opendir(name: *const c_char) -> *mut DIR, refused std::ptr::null_mut();
    swr_v1_hook_readdir => readdir(dirp: *mut DIR) -> *mut dirent, refused std::ptr::null_mut();
    swr_v1_hook_closedir => closedir(dirp: *mut DIR) -> c_int, refused -1;
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
}
