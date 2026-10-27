//! `network::Socket::ssl_recv`/`ssl_send` as whole operations, OpenSSL call
//! included: clear the error queue, `SSL_read`/`SSL_write`, and classify a failure.
//! Native code keeps the want flags, errno and `ssl_catch_error`'s log, which needs
//! the socket's address.
use openssl_sys::{
    ERR_clear_error, SSL, SSL_ERROR_SSL, SSL_ERROR_SYSCALL, SSL_ERROR_WANT_READ,
    SSL_ERROR_WANT_WRITE, SSL_ERROR_ZERO_RETURN, SSL_accept, SSL_connect, SSL_get_error, SSL_read,
    SSL_write,
};
use std::os::raw::{c_int, c_void};

/// `SW_ERROR_SSL_BAD_CLIENT` and `SW_ERROR_SSL_RESET`.
const BAD_CLIENT: c_int = 1015;
const RESET: c_int = 1017;
/// `SW_ERROR_SSL_HANDSHAKE_FAILED`.
const HANDSHAKE_FAILED: c_int = 1018;
/// `swReturnCode`'s `SW_WAIT`, `SW_ERROR` and `SW_READY`; `SW_OK`/`SW_ERR`.
const WAIT: c_int = 2;
const ERROR: c_int = 4;
const READY: c_int = 5;
const OK: c_int = 0;
const ERR: c_int = -1;
/// `SW_SSL_STATE_READY` and `SW_SSL_STATE_WAIT_STREAM`.
const STATE_READY: c_int = 1;
const STATE_WAIT_STREAM: c_int = 2;

fn errno() -> c_int {
    std::io::Error::last_os_error().raw_os_error().unwrap_or(0)
}

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
            if errno() == 0 {
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

/// A handshake step for `Socket::ssl_accept`/`ssl_connect`. Native code stores the
/// want flags, the `ssl_state` when `state` is nonnegative and the last error when
/// `last_error` is nonzero, then logs: 1 a bad client (accept), 2 a failed handshake
/// with `ssl_error`, 3 a peer that closed (connect, debug). `code` is what the
/// method returns.
#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct SslHandshakeResult {
    pub code: c_int,
    pub want_read: bool,
    pub want_write: bool,
    pub state: c_int,
    pub last_error: c_int,
    pub log: c_int,
    pub ssl_error: c_int,
}

impl SslHandshakeResult {
    const fn returning(code: c_int) -> Self {
        Self {
            code,
            want_read: false,
            want_write: false,
            state: -1,
            last_error: 0,
            log: 0,
            ssl_error: 0,
        }
    }
}

/// `Socket::ssl_accept`: one `SSL_accept` step. A DTLS socket waits to read on a
/// syscall error that left errno 0.
///
/// # Safety
/// `ssl` is a live SSL owned by the caller.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_socket_ssl_accept(ssl: *mut SSL, dtls: bool) -> SslHandshakeResult {
    // SAFETY: clears this thread's OpenSSL error queue.
    unsafe { ERR_clear_error() };
    // SAFETY: the caller's live SSL.
    let n = unsafe { SSL_accept(ssl) };
    if n == 1 {
        return SslHandshakeResult {
            state: STATE_READY,
            ..SslHandshakeResult::returning(READY)
        };
    }
    if n == 0 {
        return SslHandshakeResult::returning(ERROR);
    }
    // SAFETY: `ssl` is the caller's live SSL and `n` its last result.
    let error = unsafe { SSL_get_error(ssl, n) };
    let mut result = SslHandshakeResult::returning(ERROR);
    match error {
        SSL_ERROR_WANT_READ => {
            result.want_read = true;
            result.code = WAIT;
        }
        SSL_ERROR_WANT_WRITE => {
            result.want_write = true;
            result.code = WAIT;
        }
        SSL_ERROR_SSL => result.log = 1,
        SSL_ERROR_SYSCALL => {
            if dtls && errno() == 0 {
                result.want_read = true;
                result.code = WAIT;
            }
        }
        _ => {
            result.log = 2;
            result.ssl_error = error;
        }
    }
    result
}

/// `Socket::ssl_connect`: one `SSL_connect` step.
///
/// # Safety
/// `ssl` is a live SSL owned by the caller.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_socket_ssl_connect(ssl: *mut SSL) -> SslHandshakeResult {
    // SAFETY: clears this thread's OpenSSL error queue.
    unsafe { ERR_clear_error() };
    // SAFETY: the caller's live SSL.
    let n = unsafe { SSL_connect(ssl) };
    if n == 1 {
        return SslHandshakeResult {
            state: STATE_READY,
            ..SslHandshakeResult::returning(OK)
        };
    }
    // SAFETY: `ssl` is the caller's live SSL and `n` its last result.
    let error = unsafe { SSL_get_error(ssl, n) };
    let mut result = SslHandshakeResult::returning(ERR);
    match error {
        SSL_ERROR_WANT_READ | SSL_ERROR_WANT_WRITE => {
            result.want_read = error == SSL_ERROR_WANT_READ;
            result.want_write = error == SSL_ERROR_WANT_WRITE;
            result.state = STATE_WAIT_STREAM;
            result.code = OK;
            return result;
        }
        SSL_ERROR_ZERO_RETURN => {
            result.last_error = RESET;
            result.log = 3;
            return result;
        }
        SSL_ERROR_SYSCALL if n != 0 => {
            result.last_error = errno();
            return result;
        }
        SSL_ERROR_SYSCALL => {}
        _ => result.last_error = HANDSHAKE_FAILED,
    }
    result.log = 2;
    result.ssl_error = error;
    result
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
    fn handshake_steps() {
        unsafe {
            let (ssl, read) = client();
            assert_eq!(
                swr_v1_socket_ssl_connect(ssl),
                SslHandshakeResult {
                    want_read: true,
                    state: STATE_WAIT_STREAM,
                    ..SslHandshakeResult::returning(OK)
                },
                "the client hello is out; waiting for the server"
            );
            let garbage = [
                0x16_u8, 0x03, 0x03, 0x00, 0x05, 0xff, 0xff, 0xff, 0xff, 0xff,
            ];
            BIO_write(
                read,
                garbage.as_ptr().cast(),
                c_int::try_from(garbage.len()).unwrap(),
            );
            let failed = swr_v1_socket_ssl_connect(ssl);
            assert_eq!(
                (failed.code, failed.last_error, failed.log),
                (ERR, HANDSHAKE_FAILED, 2)
            );
            assert_eq!(failed.ssl_error, SSL_ERROR_SSL);
            SSL_free(ssl);

            let context = SSL_CTX_new(TLS_method());
            let server = SSL_new(context);
            SSL_CTX_free(context);
            SSL_set_bio(server, BIO_new(BIO_s_mem()), BIO_new(BIO_s_mem()));
            assert_eq!(
                swr_v1_socket_ssl_accept(server, false),
                SslHandshakeResult {
                    want_read: true,
                    ..SslHandshakeResult::returning(WAIT)
                },
                "no client hello yet"
            );
            SSL_free(server);
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
