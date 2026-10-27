//! `network::Socket::ssl_recv`/`ssl_send` as whole operations, OpenSSL call
//! included: clear the error queue, `SSL_read`/`SSL_write`, and classify a failure.
//! Native code keeps the want flags, errno and `ssl_catch_error`'s log, which needs
//! the socket's address.
use openssl_sys::{
    ERR_clear_error, SSL, SSL_ERROR_SSL, SSL_ERROR_SYSCALL, SSL_ERROR_WANT_READ,
    SSL_ERROR_WANT_WRITE, SSL_get_error, SSL_read, SSL_write,
};
use std::os::raw::{c_int, c_void};

/// `SW_ERROR_SSL_BAD_CLIENT` and `SW_ERROR_SSL_RESET`.
const BAD_CLIENT: c_int = 1015;
const RESET: c_int = 1017;

/// A TLS read or write: what `ssl_recv`/`ssl_send` return, the socket's new want
/// flags, the errno to set when nonzero, and whether to log a protocol error first.
#[repr(C)]
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct SslIoResult {
    pub value: isize,
    pub want_read: bool,
    pub want_write: bool,
    pub error: c_int,
    pub protocol_error: bool,
}

fn classify(ssl: *const SSL, n: c_int, write: bool) -> SslIoResult {
    let mut result = SslIoResult {
        value: n as isize,
        ..SslIoResult::default()
    };
    if n >= 0 {
        return result;
    }
    // SAFETY: `ssl` is the caller's live SSL and `n` its last I/O result.
    match unsafe { SSL_get_error(ssl, n) } {
        SSL_ERROR_WANT_READ => {
            result.want_read = true;
            result.error = libc::EAGAIN;
        }
        SSL_ERROR_WANT_WRITE => {
            result.want_write = true;
            result.error = libc::EAGAIN;
        }
        SSL_ERROR_SYSCALL if write => result.error = RESET,
        SSL_ERROR_SYSCALL => {
            if std::io::Error::last_os_error().raw_os_error() == Some(0) {
                result.value = 0;
            }
        }
        SSL_ERROR_SSL => {
            result.protocol_error = true;
            result.error = BAD_CLIENT;
        }
        _ => {}
    }
    result
}

/// `Socket::ssl_recv`: `SSL_read` up to `length` bytes.
///
/// # Safety
/// `ssl` is a live SSL owned by the caller and `buffer` denotes `length` writable bytes.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_socket_ssl_recv(
    ssl: *mut SSL,
    buffer: *mut c_void,
    length: usize,
) -> SslIoResult {
    // SAFETY: clears this thread's OpenSSL error queue.
    unsafe { ERR_clear_error() };
    #[expect(
        clippy::cast_possible_truncation,
        clippy::cast_possible_wrap,
        reason = "upstream passes its size_t to SSL_read's int the same way"
    )]
    // SAFETY: the caller lends `length` writable bytes to its SSL.
    let n = unsafe { SSL_read(ssl, buffer, length as c_int) };
    classify(ssl, n, false)
}

/// `Socket::ssl_send`: `SSL_write` of `length` bytes (native code applies the DTLS
/// chunk limit first).
///
/// # Safety
/// `ssl` is a live SSL owned by the caller and `buffer` denotes `length` readable bytes.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_socket_ssl_send(
    ssl: *mut SSL,
    buffer: *const c_void,
    length: usize,
) -> SslIoResult {
    // SAFETY: clears this thread's OpenSSL error queue.
    unsafe { ERR_clear_error() };
    #[expect(
        clippy::cast_possible_truncation,
        clippy::cast_possible_wrap,
        reason = "upstream passes its size_t to SSL_write's int the same way"
    )]
    // SAFETY: the caller lends `length` readable bytes to its SSL.
    let n = unsafe { SSL_write(ssl, buffer, length as c_int) };
    classify(ssl, n, true)
}

#[cfg(test)]
mod tests {
    use super::*;
    use openssl_sys::*;
    use std::os::raw::c_int;

    /// A client SSL over memory BIOs, before its handshake; returns it and its read BIO.
    unsafe fn client() -> (*mut SSL, *mut BIO) {
        unsafe {
            let context = SSL_CTX_new(TLS_method());
            let ssl = SSL_new(context);
            SSL_CTX_free(context);
            let (read, write) = (BIO_new(BIO_s_mem()), BIO_new(BIO_s_mem()));
            SSL_set_bio(ssl, read, write);
            SSL_set_connect_state(ssl);
            (ssl, read)
        }
    }

    #[test]
    fn want_read_before_the_handshake() {
        unsafe {
            let (ssl, _) = client();
            let mut buffer = [0_u8; 16];
            let read = swr_v1_socket_ssl_recv(ssl, buffer.as_mut_ptr().cast(), buffer.len());
            assert_eq!(
                read,
                SslIoResult {
                    value: -1,
                    want_read: true,
                    error: libc::EAGAIN,
                    ..Default::default()
                }
            );
            let sent = swr_v1_socket_ssl_send(ssl, buffer.as_ptr().cast(), buffer.len());
            assert_eq!(sent, read, "a write also waits for the server's hello");
            SSL_free(ssl);
        }
    }

    #[test]
    fn garbage_is_a_protocol_error() {
        unsafe {
            let (ssl, read) = client();
            let mut buffer = [0_u8; 16];
            swr_v1_socket_ssl_recv(ssl, buffer.as_mut_ptr().cast(), buffer.len());
            let garbage = [
                0x16_u8, 0x03, 0x03, 0x00, 0x05, 0xff, 0xff, 0xff, 0xff, 0xff,
            ];
            BIO_write(
                read,
                garbage.as_ptr().cast(),
                c_int::try_from(garbage.len()).unwrap(),
            );
            let result = swr_v1_socket_ssl_recv(ssl, buffer.as_mut_ptr().cast(), buffer.len());
            assert_eq!(
                result,
                SslIoResult {
                    value: -1,
                    error: BAD_CLIENT,
                    protocol_error: true,
                    ..Default::default()
                }
            );
            assert_ne!(ERR_get_error(), 0, "the queue is left for ssl_catch_error");
            SSL_free(ssl);
        }
    }
}
