//! `Socket::shutdown` of the coroutine socket: admission, the TLS close, the
//! `shutdown(2)` call and the half-close flags. Native code keeps `set_err`,
//! `is_connected` and the TLS session.
use core::ffi::c_void;

/// The socket's `connected`, `shutdown_read` and `shutdown_write`, updated in place.
#[repr(C)]
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct ShutdownFlags {
    pub connected: bool,
    pub read: bool,
    pub write: bool,
}

/// `Socket::shutdown(how)` after `set_err(0)`: 0 on success, otherwise the error
/// to set. `live` is `is_connected()`; `ssl_shutdown`, when the socket has TLS,
/// closes the session first. `syscall` is `shutdown(2)`, which sets errno.
///
/// # Safety
/// `flags` is writable; `ssl_shutdown`, if set, acts on the live socket in `context`.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_hook_shutdown(
    syscall: unsafe extern "C" fn(i32, i32) -> i32,
    fd: i32,
    how: i32,
    live: bool,
    flags: *mut ShutdownFlags,
    ssl_shutdown: Option<unsafe extern "C" fn(*mut c_void)>,
    context: *mut c_void,
) -> i32 {
    // SAFETY: the caller passes writable flags (see above).
    let flags = unsafe { &mut *flags };
    if !live || how == libc::SHUT_RD && flags.read || how == libc::SHUT_WR && flags.write {
        return libc::ENOTCONN;
    }
    if let Some(ssl_shutdown) = ssl_shutdown {
        // SAFETY: a native effect on the live socket in `context`.
        unsafe { ssl_shutdown(context) };
    }
    // SAFETY: shutdown(2) on the socket's descriptor; failure is reported through errno.
    let error = if unsafe { syscall(fd, how) } < 0 {
        std::io::Error::last_os_error().raw_os_error().unwrap_or(0)
    } else {
        0
    };
    if error != 0 && error != libc::ENOTCONN {
        return error;
    }
    // A connection reset by the peer shuts both directions.
    let how = if error == libc::ENOTCONN {
        libc::SHUT_RDWR
    } else {
        how
    };
    match how {
        libc::SHUT_RD => flags.read = true,
        libc::SHUT_WR => flags.write = true,
        _ => {
            flags.read = true;
            flags.write = true;
        }
    }
    if flags.read && flags.write {
        flags.connected = false;
    }
    0
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pair() -> [i32; 2] {
        let mut fds = [0; 2];
        assert_eq!(
            unsafe { libc::socketpair(libc::AF_UNIX, libc::SOCK_STREAM, 0, fds.as_mut_ptr()) },
            0
        );
        fds
    }

    fn shutdown(fd: i32, how: i32, live: bool, flags: &mut ShutdownFlags) -> i32 {
        unsafe {
            swr_v1_hook_shutdown(
                libc::shutdown,
                fd,
                how,
                live,
                &raw mut *flags,
                None,
                core::ptr::null_mut(),
            )
        }
    }

    #[test]
    fn half_closes_then_both_disconnects() {
        let fds = pair();
        let mut flags = ShutdownFlags {
            connected: true,
            ..Default::default()
        };
        assert_eq!(shutdown(fds[0], libc::SHUT_RD, true, &mut flags), 0);
        assert_eq!(
            flags,
            ShutdownFlags {
                connected: true,
                read: true,
                write: false
            }
        );
        assert_eq!(
            shutdown(fds[0], libc::SHUT_RD, true, &mut flags),
            libc::ENOTCONN
        );
        assert_eq!(shutdown(fds[0], libc::SHUT_WR, true, &mut flags), 0);
        assert_eq!(
            flags,
            ShutdownFlags {
                connected: false,
                read: true,
                write: true
            }
        );
        unsafe { libc::close(fds[0]) };
        unsafe { libc::close(fds[1]) };
    }

    #[test]
    fn not_connected_and_bad_descriptors_fail() {
        let mut flags = ShutdownFlags::default();
        assert_eq!(
            shutdown(-1, libc::SHUT_RDWR, false, &mut flags),
            libc::ENOTCONN
        );
        flags.connected = true;
        assert_eq!(shutdown(-1, libc::SHUT_RDWR, true, &mut flags), libc::EBADF);
        assert_eq!(
            flags,
            ShutdownFlags {
                connected: true,
                read: false,
                write: false
            }
        );
    }

    #[test]
    fn tls_closes_first() {
        unsafe extern "C" fn mark(context: *mut c_void) {
            unsafe { *context.cast::<bool>() = true };
        }
        let fds = pair();
        let mut closed = false;
        let mut flags = ShutdownFlags {
            connected: true,
            ..Default::default()
        };
        let error = unsafe {
            swr_v1_hook_shutdown(
                libc::shutdown,
                fds[0],
                libc::SHUT_RDWR,
                true,
                &raw mut flags,
                Some(mark),
                (&raw mut closed).cast(),
            )
        };
        assert_eq!((error, closed, flags.connected), (0, true, false));
        unsafe { libc::close(fds[0]) };
        unsafe { libc::close(fds[1]) };
    }
}
