//! `Client_onStreamRead` and `Client_onWrite`, the reactor handlers of an async
//! `network::Client`, as whole operations over the Rust-owned `ClientState`: the
//! proxy and TLS handshakes that finish a connect, protocol framing, plain reads,
//! and the writable path. Native code keeps the `Socket`, the proxies, the buffer
//! and the callbacks, and passes them in `ReadOps`/`WriteOps`, reading each fact
//! afresh. User callbacks end the handler: nothing touches the client after one.
use crate::state::{ACTIVE, CLOSED, ClientState, swr_v1_clients_flag, swr_v1_clients_set_flag};
use core::ffi::c_void;

macro_rules! call {
    ($ops:ident . $effect:ident $(, $arg:expr)*) => {
        // SAFETY: a native effect on the live client in `context`.
        unsafe { ($ops.$effect)($ops.context $(, $arg)*) }
    };
}

fn set(state: *mut ClientState, name: u32, value: bool) {
    // SAFETY: the client's live handle, not borrowed across this call.
    unsafe { swr_v1_clients_set_flag(state, name, value) };
}

/// The handshake that failed, for `fail`: `SW_ERROR_HTTP_PROXY_HANDSHAKE_ERROR`,
/// `SW_ERROR_SOCKS5_HANDSHAKE_FAILED` or `SW_ERROR_SSL_HANDSHAKE_FAILED`.
pub const FAIL_HTTP: u32 = 0;
pub const FAIL_SOCKS: u32 = 1;
pub const FAIL_SSL: u32 = 2;
/// `catch_read_error`'s verdicts.
pub const READ_ERROR: i32 = 0;
pub const READ_CLOSE: i32 = 1;

/// The client's effects for a readable event.
#[repr(C)]
pub struct ReadOps {
    pub context: *mut c_void,
    pub state: *mut ClientState,
    /// `open_ssl` when the event arrived.
    pub ssl_requested: bool,
    /// An HTTP proxy is set and not ready.
    pub http_pending: unsafe extern "C" fn(*mut c_void) -> bool,
    /// `recv` into the buffer's free space.
    pub receive: unsafe extern "C" fn(*mut c_void) -> isize,
    pub http_handshake: unsafe extern "C" fn(*mut c_void, isize) -> bool,
    /// Marks the HTTP proxy ready and clears the buffer.
    pub http_ready: unsafe extern "C" fn(*mut c_void),
    /// A SOCKS5 proxy is set and not ready.
    pub socks_pending: unsafe extern "C" fn(*mut c_void) -> bool,
    pub socks_handshake: unsafe extern "C" fn(*mut c_void, isize) -> bool,
    pub socks_ready: unsafe extern "C" fn(*mut c_void) -> bool,
    pub clear_buffer: unsafe extern "C" fn(*mut c_void),
    /// TLS is on and not ready.
    pub ssl_pending: unsafe extern "C" fn(*mut c_void) -> bool,
    pub ssl_handshake: unsafe extern "C" fn(*mut c_void) -> isize,
    pub ssl_ready: unsafe extern "C" fn(*mut c_void) -> bool,
    /// `open_eof_check || open_length_check`.
    pub framed: unsafe extern "C" fn(*mut c_void) -> bool,
    /// The EOF or length protocol's receive, remembering the socket it used.
    pub protocol_receive: unsafe extern "C" fn(*mut c_void) -> isize,
    /// That socket is still registered and the client asked to sleep.
    pub sleep_requested: unsafe extern "C" fn(*mut c_void) -> bool,
    /// `sleep()` and clears the request.
    pub sleep: unsafe extern "C" fn(*mut c_void),
    /// `catch_read_error(errno)`: `READ_ERROR`, `READ_CLOSE` or anything else.
    pub catch_error: unsafe extern "C" fn(*mut c_void) -> i32,
    pub warn: unsafe extern "C" fn(*mut c_void),
    pub close: unsafe extern "C" fn(*mut c_void) -> i32,
    /// `onReceive` with the bytes read.
    pub on_receive: unsafe extern "C" fn(*mut c_void, isize),
    /// `execute_onConnect`.
    pub on_connect: unsafe extern "C" fn(*mut c_void),
    /// Sets the handshake's error, clears `active`, closes and calls `onError` when set.
    pub fail: unsafe extern "C" fn(*mut c_void, u32),
}

/// `Client_onStreamRead`: 0, or `close()`'s result when the peer closed.
///
/// # Safety
/// `ops` is live for the call; its callbacks act on the client in `context`, which
/// a user callback may destroy, so nothing touches it afterwards.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_clients_on_read(ops: *const ReadOps) -> i32 {
    // SAFETY: the caller passes a live table (see above).
    let ops = unsafe { &*ops };
    let fail = |kind: u32| {
        call!(ops.fail, kind);
        0
    };
    if call!(ops.http_pending) {
        let n = call!(ops.receive);
        if n <= 0 || !call!(ops.http_handshake, n) {
            return fail(FAIL_HTTP);
        }
        call!(ops.http_ready);
        if !ops.ssl_requested {
            call!(ops.on_connect);
            return 0;
        }
    }
    if call!(ops.socks_pending) {
        let n = call!(ops.receive);
        if n <= 0 || !call!(ops.socks_handshake, n) {
            return fail(FAIL_SOCKS);
        }
        if !call!(ops.socks_ready) {
            return 0;
        }
        call!(ops.clear_buffer);
        if !ops.ssl_requested {
            call!(ops.on_connect);
            return 0;
        }
    }
    if call!(ops.ssl_pending) {
        if call!(ops.ssl_handshake) < 0 {
            return fail(FAIL_SSL);
        }
        if call!(ops.ssl_ready) {
            call!(ops.on_connect);
        }
        return 0;
    }
    if call!(ops.framed) {
        if call!(ops.protocol_receive) < 0 {
            // SAFETY: the client's live handle.
            if !unsafe { swr_v1_clients_flag(ops.state, CLOSED) } {
                call!(ops.close);
            }
        } else if call!(ops.sleep_requested) {
            call!(ops.sleep);
        }
        return 0;
    }
    let n = call!(ops.receive);
    if n > 0 {
        call!(ops.on_receive, n);
        return 0;
    }
    if n == 0 {
        return call!(ops.close);
    }
    match call!(ops.catch_error) {
        READ_ERROR => {
            call!(ops.warn);
            0
        }
        READ_CLOSE => call!(ops.close),
        _ => 0,
    }
}

/// The client's effects for a writable event.
#[repr(C)]
pub struct WriteOps {
    pub context: *mut c_void,
    pub state: *mut ClientState,
    /// TLS is on and its stream is still waiting.
    pub ssl_waiting: unsafe extern "C" fn(*mut c_void) -> bool,
    pub ssl_handshake: unsafe extern "C" fn(*mut c_void) -> i32,
    pub ssl_ready: unsafe extern "C" fn(*mut c_void) -> bool,
    pub ssl_wants_read: unsafe extern "C" fn(*mut c_void) -> bool,
    /// `swoole_event_set(socket, SW_EVENT_READ)`.
    pub read_interest: unsafe extern "C" fn(*mut c_void),
    /// `Reactor::_writable_callback`.
    pub writable: unsafe extern "C" fn(*mut c_void) -> i32,
    /// `onBufferEmpty` is set, the client hit its high watermark, and the output
    /// buffer drained to the low one.
    pub drained: unsafe extern "C" fn(*mut c_void) -> bool,
    /// Clears the high watermark and calls `onBufferEmpty`.
    pub on_drained: unsafe extern "C" fn(*mut c_void),
    /// `getsockopt(SO_ERROR)`, publishing the error as the last error.
    pub get_option: unsafe extern "C" fn(*mut c_void) -> i32,
    pub warn_option: unsafe extern "C" fn(*mut c_void),
    /// The last error is 0.
    pub connected: unsafe extern "C" fn(*mut c_void) -> bool,
    pub socks_waiting: unsafe extern "C" fn(*mut c_void) -> bool,
    /// Sends the SOCKS5 negotiation; its result is the handler's.
    pub socks_send: unsafe extern "C" fn(*mut c_void) -> i32,
    pub http_waiting: unsafe extern "C" fn(*mut c_void) -> bool,
    /// Sends the HTTP proxy request; its result is the handler's.
    pub http_send: unsafe extern "C" fn(*mut c_void) -> i32,
    pub open_ssl: unsafe extern "C" fn(*mut c_void) -> bool,
    /// Marks the TLS stream as waiting.
    pub ssl_wait: unsafe extern "C" fn(*mut c_void),
    pub on_connect: unsafe extern "C" fn(*mut c_void),
    /// Sets the TLS error when `ssl`, clears `active`, closes and calls `onError`.
    pub fail: unsafe extern "C" fn(*mut c_void, bool),
}

/// `Client_onWrite`: 0, -1, or the proxy request's send result.
///
/// # Safety
/// `ops` is live for the call; its callbacks act on the client in `context`, which
/// a user callback may destroy, so nothing touches it afterwards.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_clients_on_write(ops: *const WriteOps) -> i32 {
    // SAFETY: the caller passes a live table (see above).
    let ops = unsafe { &*ops };
    let fail = |ssl: bool| {
        call!(ops.fail, ssl);
        0
    };
    // SAFETY: the client's live handle.
    if unsafe { swr_v1_clients_flag(ops.state, ACTIVE) } {
        if call!(ops.ssl_waiting) {
            if call!(ops.ssl_handshake) < 0 {
                return fail(true);
            }
            if call!(ops.ssl_ready) {
                call!(ops.on_connect);
            } else if call!(ops.ssl_wants_read) {
                call!(ops.read_interest);
            }
            return 0;
        }
        if call!(ops.writable) < 0 {
            return -1;
        }
        if call!(ops.drained) {
            call!(ops.on_drained);
        }
        return 0;
    }
    if call!(ops.get_option) < 0 {
        call!(ops.warn_option);
        return -1;
    }
    if !call!(ops.connected) {
        return fail(false);
    }
    call!(ops.read_interest);
    set(ops.state, ACTIVE, true);
    if call!(ops.socks_waiting) {
        return call!(ops.socks_send);
    }
    if call!(ops.http_waiting) {
        return call!(ops.http_send);
    }
    if call!(ops.open_ssl) {
        if call!(ops.ssl_handshake) < 0 {
            return fail(true);
        }
        call!(ops.ssl_wait);
        return 0;
    }
    call!(ops.on_connect);
    0
}
