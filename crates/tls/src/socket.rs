//! `network::Socket`'s TLS operations, OpenSSL calls included: creating the SSL,
//! handshake steps, reads and writes, host and verify checks, PEM export and error
//! reasons. Native code keeps the socket's flags, errno, last error and logs, which
//! need the socket's address.
use openssl_sys::{
    BIO_ctrl, BIO_free_all, BIO_new, BIO_read, BIO_s_mem, ERR_GET_REASON, ERR_clear_error,
    ERR_get_error, ERR_reason_error_string, PEM_write_bio_X509, SSL, SSL_CTX, SSL_ERROR_SSL,
    SSL_ERROR_SYSCALL, SSL_ERROR_WANT_READ, SSL_ERROR_WANT_WRITE, SSL_ERROR_ZERO_RETURN,
    SSL_accept, SSL_connect, SSL_get_error, SSL_get_verify_result, SSL_new, SSL_read,
    SSL_set_accept_state, SSL_set_connect_state, SSL_set_ex_data, SSL_write, X509,
    X509_V_ERR_DEPTH_ZERO_SELF_SIGNED_CERT, X509_V_OK, X509_check_host, X509_free,
};

// SAFETY: libssl/libcrypto's own declarations; openssl-sys binds neither.
unsafe extern "C" {
    fn SSL_set_fd(ssl: *mut SSL, fd: c_int) -> c_int;
    fn ERR_peek_error() -> std::os::raw::c_ulong;
}

/// `BIO_CTRL_PENDING`, behind the `BIO_pending` macro.
const BIO_CTRL_PENDING: c_int = 10;
/// `SW_SSL_SERVER` and `SW_SSL_CLIENT`.
const SERVER: c_int = 1;
const CLIENT: c_int = 2;
use std::os::raw::{c_char, c_int, c_long, c_void};

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

/// `Socket::ssl_check_host`: whether the peer certificate `cert` (consumed; null when
/// the peer sent none) matches the `length` bytes at `name` under `X509_check_host`.
/// Returns 0 without a certificate, 1 on a match and 2 on none (native code warns).
///
/// # Safety
/// `cert` is null or an owned X509 reference, and `name` denotes `length` readable bytes.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_socket_ssl_check_host(
    cert: *mut X509,
    name: *const c_char,
    length: usize,
) -> c_int {
    if cert.is_null() {
        return 0;
    }
    // SAFETY: the caller's certificate and `length` bytes of host name.
    let matched = unsafe { X509_check_host(cert, name, length, 0, std::ptr::null_mut()) } == 1;
    // SAFETY: drops the reference the caller handed over.
    unsafe { X509_free(cert) };
    if matched { 1 } else { 2 }
}

/// `Socket::ssl_verify`: the peer's verify result if it rejects the peer, else
/// `X509_V_OK`. A self-signed leaf passes when `allow_self_signed`.
///
/// # Safety
/// `ssl` is a live SSL owned by the caller.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_socket_ssl_verify(
    ssl: *const SSL,
    allow_self_signed: bool,
) -> c_long {
    // SAFETY: the caller's live SSL.
    let result = unsafe { SSL_get_verify_result(ssl) };
    if allow_self_signed && result == c_long::from(X509_V_ERR_DEPTH_ZERO_SELF_SIGNED_CERT) {
        return c_long::from(X509_V_OK);
    }
    result
}

/// `_ssl_read_x509_file`: `cert` as PEM into at most `length` bytes at `buffer`.
/// Returns the bytes written, or -1 when `BIO_new` failed and -2 when
/// `PEM_write_bio_X509` failed (native code warns). When `consume`, frees `cert`.
///
/// # Safety
/// `cert` is a live X509 (owned by the caller when `consume`), and `buffer` denotes
/// `length` writable bytes.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_socket_ssl_pem(
    cert: *mut X509,
    buffer: *mut c_char,
    length: usize,
    consume: bool,
) -> c_int {
    // SAFETY: OpenSSL's static memory BIO method.
    let method = unsafe { BIO_s_mem() };
    // SAFETY: a fresh BIO of that method.
    let bio = unsafe { BIO_new(method) };
    let written = if bio.is_null() {
        -1
    // SAFETY: the caller's certificate into the fresh BIO.
    } else if unsafe { PEM_write_bio_X509(bio, cert) } == 0 {
        -2
    } else {
        // SAFETY: the live BIO; BIO_pending.
        let pending = unsafe { BIO_ctrl(bio, BIO_CTRL_PENDING, 0, std::ptr::null_mut()) };
        let room = c_long::try_from(length).unwrap_or(c_long::MAX);
        let count = c_int::try_from(pending.min(room)).unwrap_or(c_int::MAX);
        // SAFETY: at most `length` bytes into the caller's buffer.
        unsafe { BIO_read(bio, buffer.cast(), count) }
    };
    if !bio.is_null() {
        // SAFETY: frees the BIO made above.
        unsafe { BIO_free_all(bio) };
    }
    if consume {
        // SAFETY: drops the reference the caller handed over.
        unsafe { X509_free(cert) };
    }
    written
}

/// `Socket::ssl_get_error_reason`: pops the oldest queued OpenSSL error and
/// returns its reason string, storing its reason code in `reason` when given.
///
/// # Safety
/// `reason` is null or writable.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_socket_ssl_error_reason(reason: *mut c_int) -> *const c_char {
    // SAFETY: this thread's OpenSSL error queue.
    let error = unsafe { ERR_get_error() };
    // SAFETY: `reason` is null or writable.
    if let Some(reason) = unsafe { reason.as_mut() } {
        *reason = ERR_GET_REASON(error);
    }
    // SAFETY: OpenSSL's static string table.
    unsafe { ERR_reason_error_string(error) }
}

/// `Socket::ssl_catch_error`'s reason: the oldest queued error's reason code, left queued.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_socket_ssl_peek_reason() -> c_int {
    // SAFETY: this thread's OpenSSL error queue, read without popping.
    ERR_GET_REASON(unsafe { ERR_peek_error() })
}

/// `Socket::ssl_create`: a new SSL from `context` on `fd`, in connect state for
/// `SW_SSL_CLIENT` or accept state for `SW_SSL_SERVER`, carrying `socket` as its
/// ex data at `index`. `*ssl` is set once made. Returns 0, or 1 when `SSL_new`
/// failed, 2 when `SSL_set_fd` failed (`*error` holds the peeked error) and 3 when
/// `SSL_set_ex_data` failed; native code warns.
///
/// # Safety
/// `context` is a live `SSL_CTX`; `ssl` and `error` are writable.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_socket_ssl_new(
    context: *mut SSL_CTX,
    fd: c_int,
    flags: c_int,
    index: c_int,
    socket: *mut c_void,
    ssl: *mut *mut SSL,
    error: *mut std::os::raw::c_ulong,
) -> c_int {
    // SAFETY: clears this thread's OpenSSL error queue.
    unsafe { ERR_clear_error() };
    // SAFETY: the caller's live context.
    let made = unsafe { SSL_new(context) };
    // SAFETY: the caller's slot for the new SSL.
    unsafe { ssl.write(made) };
    if made.is_null() {
        return 1;
    }
    // SAFETY: the new SSL and the caller's descriptor.
    if unsafe { SSL_set_fd(made, fd) } == 0 {
        // SAFETY: the queue holds SSL_set_fd's error.
        let peeked = unsafe { ERR_peek_error() };
        // SAFETY: the caller's error slot.
        unsafe { error.write(peeked) };
        return 2;
    }
    if flags & CLIENT != 0 {
        // SAFETY: the new SSL.
        unsafe { SSL_set_connect_state(made) };
    } else if flags & SERVER != 0 {
        // SAFETY: the new SSL.
        unsafe { SSL_set_accept_state(made) };
    }
    // SAFETY: the new SSL keeps the caller's socket pointer as opaque ex data.
    if unsafe { SSL_set_ex_data(made, index, socket) } == 0 {
        return 3;
    }
    0
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

    unsafe extern "C" {
        /// Not bound by openssl-sys; sets what a handshake would have verified.
        fn SSL_set_verify_result(ssl: *mut SSL, result: c_long);
    }

    #[test]
    fn check_host_and_verify() {
        unsafe {
            let check = |cert, name: &str| {
                swr_v1_socket_ssl_check_host(cert, name.as_ptr().cast(), name.len())
            };
            assert_eq!(
                check(std::ptr::null_mut(), "example.com"),
                0,
                "no certificate"
            );
            let named = |common: &str| {
                let cert = X509_new();
                let name = X509_get_subject_name(cert);
                let common = std::ffi::CString::new(common).unwrap();
                X509_NAME_add_entry_by_txt(
                    name,
                    c"CN".as_ptr(),
                    MBSTRING_ASC,
                    common.as_ptr().cast(),
                    -1,
                    -1,
                    0,
                );
                cert
            };
            assert_eq!(check(named("example.com"), "EXAMPLE.com"), 1);
            assert_eq!(
                check(named("*.example.com"), "a.example.com"),
                1,
                "wildcard"
            );
            assert_eq!(check(named("example.com"), "example.org"), 2);

            let (ssl, _) = client();
            assert_eq!(
                swr_v1_socket_ssl_verify(ssl, false),
                c_long::from(X509_V_OK)
            );
            SSL_set_verify_result(ssl, c_long::from(X509_V_ERR_DEPTH_ZERO_SELF_SIGNED_CERT));
            assert_eq!(swr_v1_socket_ssl_verify(ssl, true), c_long::from(X509_V_OK));
            assert_eq!(
                swr_v1_socket_ssl_verify(ssl, false),
                c_long::from(X509_V_ERR_DEPTH_ZERO_SELF_SIGNED_CERT)
            );
            SSL_set_verify_result(ssl, c_long::from(X509_V_ERR_CERT_HAS_EXPIRED));
            assert_eq!(
                swr_v1_socket_ssl_verify(ssl, true),
                c_long::from(X509_V_ERR_CERT_HAS_EXPIRED)
            );
            SSL_free(ssl);
        }
    }

    #[test]
    fn pem_reason_and_new() {
        unsafe {
            let mut pem = [0_u8; 4096];
            let empty = X509_new();
            assert_eq!(
                swr_v1_socket_ssl_pem(empty, pem.as_mut_ptr().cast(), pem.len(), true),
                -2,
                "nothing to encode"
            );
            ERR_clear_error();
            // A self-signed Ed25519 certificate.
            let keygen = EVP_PKEY_CTX_new_id(EVP_PKEY_ED25519, std::ptr::null_mut());
            let mut key = std::ptr::null_mut();
            assert_eq!(EVP_PKEY_keygen_init(keygen), 1);
            assert_eq!(EVP_PKEY_keygen(keygen, &raw mut key), 1);
            EVP_PKEY_CTX_free(keygen);
            let cert = X509_new();
            assert_eq!(X509_set_pubkey(cert, key), 1);
            assert!(X509_sign(cert, key, std::ptr::null()) > 0);
            EVP_PKEY_free(key);
            let written = swr_v1_socket_ssl_pem(cert, pem.as_mut_ptr().cast(), pem.len(), false);
            assert!(written > 0);
            assert!(pem.starts_with(b"-----BEGIN CERTIFICATE-----"));
            let mut short = [0_u8; 10];
            assert_eq!(
                swr_v1_socket_ssl_pem(cert, short.as_mut_ptr().cast(), short.len(), true),
                10,
                "bounded by the buffer"
            );

            let context = SSL_CTX_new(TLS_method());
            let mut ssl = std::ptr::null_mut();
            let mut error = 0;
            let mut socket = 7_u8;
            let index = SSL_get_ex_new_index(0, std::ptr::null_mut(), None, None, None);
            let made = swr_v1_socket_ssl_new(
                context,
                3,
                CLIENT,
                index,
                (&raw mut socket).cast(),
                &raw mut ssl,
                &raw mut error,
            );
            assert_eq!(made, 0);
            assert_eq!(SSL_is_server(ssl), 0, "connect state");
            assert_eq!(SSL_get_ex_data(ssl, index), (&raw mut socket).cast());
            SSL_free(ssl);
            assert_eq!(
                swr_v1_socket_ssl_new(
                    context,
                    3,
                    SERVER,
                    index,
                    std::ptr::null_mut(),
                    &raw mut ssl,
                    &raw mut error
                ),
                0
            );
            assert_eq!(SSL_is_server(ssl), 1, "accept state");
            SSL_free(ssl);
            SSL_CTX_free(context);

            assert_eq!(swr_v1_socket_ssl_peek_reason(), 0, "empty queue");
            let mut reason = -1;
            assert!(swr_v1_socket_ssl_error_reason(&raw mut reason).is_null());
            assert_eq!(reason, 0);
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
