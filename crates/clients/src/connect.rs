//! `Client_tcp_connect_sync` and `Client_tcp_connect_async` of `network::Client` as
//! whole operations over the Rust-owned `ClientState`: the timeouts, the connect
//! and its outcome, the SOCKS5 and HTTP proxy handshakes and TLS (sync), and the
//! callback check, buffer, DNS, `EINTR` retry, timer and reactor registration
//! (async). Native code keeps the `Socket`, the proxies and the callbacks, and
//! passes them in `ConnectOps`/`AsyncConnectOps`; it reads each fact afresh.
use crate::state::{
    ACTIVE, ASYNC_CONNECT, ClientState, WAIT_DNS, swr_v1_clients_flag, swr_v1_clients_set_flag,
};
use core::ffi::c_void;

/// `connect_nonblocking`'s outcomes (native `SW_READY` and `SW_WAIT`).
pub const READY: i32 = 1;
pub const WAIT: i32 = 2;

/// The client's effects for a blocking-capable connect. Every callback gets `context`.
#[repr(C)]
pub struct ConnectOps {
    pub context: *mut c_void,
    pub state: *mut ClientState,
    pub timeout: f64,
    pub nonblock: bool,
    /// `set_timeout(timeout)`.
    pub set_timeout: unsafe extern "C" fn(*mut c_void),
    /// `socket->set_kernel_timeout(timeout)`.
    pub kernel_timeout: unsafe extern "C" fn(*mut c_void),
    /// `Client_inet_addr`; negative on failure.
    pub address: unsafe extern "C" fn(*mut c_void) -> i32,
    /// `socket->connect_async`: `READY`, `WAIT` or anything else for failure.
    pub connect_nonblocking: unsafe extern "C" fn(*mut c_void) -> i32,
    /// `socket->connect_sync`'s result.
    pub connect_blocking: unsafe extern "C" fn(*mut c_void) -> i32,
    /// Takes the thread's receive buffer for the handshakes.
    pub activate: unsafe extern "C" fn(*mut c_void),
    pub has_socks: unsafe extern "C" fn(*mut c_void) -> bool,
    /// Packs and sends the SOCKS5 negotiation request.
    pub socks_send: unsafe extern "C" fn(*mut c_void) -> isize,
    /// Marks the proxy (taken at `socks_send`) as handshaking.
    pub socks_publish: unsafe extern "C" fn(*mut c_void),
    /// One `recv` into the receive buffer.
    pub receive: unsafe extern "C" fn(*mut c_void) -> isize,
    pub socks_handshake: unsafe extern "C" fn(*mut c_void, isize) -> bool,
    /// The current SOCKS5 proxy is ready.
    pub socks_ready: unsafe extern "C" fn(*mut c_void) -> bool,
    pub has_http: unsafe extern "C" fn(*mut c_void) -> bool,
    /// Packs and sends the HTTP proxy request.
    pub http_send: unsafe extern "C" fn(*mut c_void) -> isize,
    pub http_handshake: unsafe extern "C" fn(*mut c_void, isize) -> bool,
    pub open_ssl: unsafe extern "C" fn(*mut c_void) -> bool,
    pub ssl_handshake: unsafe extern "C" fn(*mut c_void) -> i32,
}

macro_rules! call {
    ($ops:ident . $effect:ident $(, $arg:expr)*) => {
        // SAFETY: a native effect on the live client in `context`.
        unsafe { ($ops.$effect)($ops.context $(, $arg)*) }
    };
}

fn set(state: *mut ClientState, flag: u32, value: bool) {
    // SAFETY: the client's live handle, not borrowed across this call.
    unsafe { swr_v1_clients_set_flag(state, flag, value) };
}

/// `Client_tcp_connect_sync`: 0 when a non-blocking connect is ready, -1 on any
/// failure (and while a non-blocking connect is pending, with `async_connect` set),
/// otherwise the blocking connect's result after the proxy and TLS handshakes.
///
/// # Safety
/// `ops` is live for the call; its callbacks act on the client in `context`.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_clients_connect(ops: *const ConnectOps) -> i32 {
    // SAFETY: the caller passes a live table (see above).
    let ops = unsafe { &*ops };
    call!(ops.set_timeout);
    if ops.timeout > 0.0 {
        call!(ops.kernel_timeout);
    }
    if call!(ops.address) < 0 {
        return -1;
    }
    if ops.nonblock {
        return match call!(ops.connect_nonblocking) {
            READY => 0,
            WAIT => {
                set(ops.state, ASYNC_CONNECT, true);
                -1
            }
            _ => -1,
        };
    }
    let result = call!(ops.connect_blocking);
    if result < 0 {
        return result;
    }
    set(ops.state, ACTIVE, true);
    call!(ops.activate);
    if call!(ops.has_socks) {
        if call!(ops.socks_send) < 0 {
            return -1;
        }
        call!(ops.socks_publish);
        loop {
            let received = call!(ops.receive);
            if received <= 0 || !call!(ops.socks_handshake, received) {
                return -1;
            }
            if call!(ops.socks_ready) {
                break;
            }
        }
    } else if call!(ops.has_http) {
        if call!(ops.http_send) < 0 {
            return -1;
        }
        let received = call!(ops.receive);
        if received <= 0 || !call!(ops.http_handshake, received) {
            return -1;
        }
    }
    if call!(ops.open_ssl) && call!(ops.ssl_handshake) < 0 {
        return -1;
    }
    result
}

/// The client's effects for an async connect. Every callback gets `context`.
#[repr(C)]
pub struct AsyncConnectOps {
    pub context: *mut c_void,
    pub state: *mut ClientState,
    pub timeout: f64,
    /// `onConnect`, `onError`, `onClose` and `onReceive` are all set.
    pub callbacks_set: unsafe extern "C" fn(*mut c_void) -> bool,
    /// Warns that they are not.
    pub warn_callbacks: unsafe extern "C" fn(*mut c_void),
    pub set_timeout: unsafe extern "C" fn(*mut c_void),
    /// Allocates the input buffer when there is none.
    pub buffer: unsafe extern "C" fn(*mut c_void),
    /// Sets the high watermark when `onBufferFull` is set and it is zero.
    pub watermark: unsafe extern "C" fn(*mut c_void),
    pub address: unsafe extern "C" fn(*mut c_void) -> i32,
    /// `Client_dns_lookup`'s result.
    pub dns_lookup: unsafe extern "C" fn(*mut c_void) -> i32,
    /// `socket->connect`'s result; errno is set when it fails.
    pub connect: unsafe extern "C" fn(*mut c_void) -> i32,
    /// Adds the connect timer; true when one is set.
    pub add_timer: unsafe extern "C" fn(*mut c_void) -> bool,
    /// `swoole_event_add(socket, SW_EVENT_WRITE)`.
    pub add_event: unsafe extern "C" fn(*mut c_void) -> i32,
    /// Marks the socket removed, closes the client and calls `onError` when set;
    /// false when it threw. The client may be gone afterwards.
    pub fail: unsafe extern "C" fn(*mut c_void) -> bool,
}

fn errno() -> i32 {
    std::io::Error::last_os_error().raw_os_error().unwrap_or(0)
}

/// `Client_tcp_connect_async`: -1 on a missing callback, a bad address or a failed
/// timer; the DNS lookup's result when it must resolve first; the failed connect's
/// result after `onError`; otherwise the reactor registration's result.
///
/// # Safety
/// `ops` is live for the call; its callbacks act on the client in `context`, which
/// `fail` may destroy, so nothing touches it afterwards.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_clients_connect_async(ops: *const AsyncConnectOps) -> i32 {
    // SAFETY: the caller passes a live table (see above).
    let ops = unsafe { &*ops };
    if !call!(ops.callbacks_set) {
        call!(ops.warn_callbacks);
        return -1;
    }
    call!(ops.set_timeout);
    call!(ops.buffer);
    call!(ops.watermark);
    if call!(ops.address) < 0 {
        return -1;
    }
    // SAFETY: the client's live handle.
    if unsafe { swr_v1_clients_flag(ops.state, WAIT_DNS) } {
        return call!(ops.dns_lookup);
    }
    let result = loop {
        let result = call!(ops.connect);
        if result >= 0 || errno() != libc::EINTR {
            break result;
        }
    };
    if result != 0 && (result >= 0 || errno() != libc::EINPROGRESS) {
        set(ops.state, ACTIVE, false);
        // The client's last effect here; it may destroy the client.
        call!(ops.fail);
        return result;
    }
    if result < 0 && ops.timeout > 0.0 && !call!(ops.add_timer) {
        return -1;
    }
    call!(ops.add_event)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::state::{swr_v1_clients_state_free, swr_v1_clients_state_new};
    use std::collections::VecDeque;

    #[derive(Default)]
    struct Fake {
        results: VecDeque<i32>,
        socks: bool,
        http: bool,
        ssl: bool,
        ready_after: u32,
        handshakes: u32,
        events: Vec<String>,
    }

    unsafe fn fake<'a>(c: *mut c_void) -> &'a mut Fake {
        unsafe { &mut *c.cast::<Fake>() }
    }
    fn next(c: *mut c_void, name: &str) -> i32 {
        let this = unsafe { fake(c) };
        this.events.push(name.into());
        this.results.pop_front().unwrap_or(0)
    }
    unsafe extern "C" fn mark(c: *mut c_void) {
        unsafe { fake(c) }.events.push("effect".into());
    }
    unsafe extern "C" fn int(c: *mut c_void) -> i32 {
        next(c, "call")
    }
    unsafe extern "C" fn size(c: *mut c_void) -> isize {
        next(c, "io") as isize
    }
    unsafe extern "C" fn socks(c: *mut c_void) -> bool {
        unsafe { fake(c) }.socks
    }
    unsafe extern "C" fn http(c: *mut c_void) -> bool {
        unsafe { fake(c) }.http
    }
    unsafe extern "C" fn ssl(c: *mut c_void) -> bool {
        unsafe { fake(c) }.ssl
    }
    unsafe extern "C" fn handshake(c: *mut c_void, _: isize) -> bool {
        let this = unsafe { fake(c) };
        this.handshakes += 1;
        this.events.push("handshake".into());
        true
    }
    unsafe extern "C" fn ready(c: *mut c_void) -> bool {
        let this = unsafe { fake(c) };
        this.handshakes >= this.ready_after
    }

    fn sync(fake: &mut Fake, nonblock: bool, timeout: f64) -> (i32, bool, bool) {
        let state = swr_v1_clients_state_new(false);
        let ops = ConnectOps {
            context: (&raw mut *fake).cast(),
            state,
            timeout,
            nonblock,
            set_timeout: mark,
            kernel_timeout: mark,
            address: int,
            connect_nonblocking: int,
            connect_blocking: int,
            activate: mark,
            has_socks: socks,
            socks_send: size,
            socks_publish: mark,
            receive: size,
            socks_handshake: handshake,
            socks_ready: ready,
            has_http: http,
            http_send: size,
            http_handshake: handshake,
            open_ssl: ssl,
            ssl_handshake: int,
        };
        let result = unsafe { swr_v1_clients_connect(&raw const ops) };
        let flags = unsafe {
            (
                swr_v1_clients_flag(state, ACTIVE),
                swr_v1_clients_flag(state, ASYNC_CONNECT),
            )
        };
        unsafe { swr_v1_clients_state_free(state) };
        (result, flags.0, flags.1)
    }

    #[test]
    fn nonblocking_connect_reports_ready_or_pending() {
        let mut f = Fake {
            results: [0, READY].into(),
            ..Fake::default()
        };
        assert_eq!(sync(&mut f, true, 0.0), (0, false, false));
        let mut f = Fake {
            results: [0, WAIT].into(),
            ..Fake::default()
        };
        assert_eq!(sync(&mut f, true, 0.0), (-1, false, true));
        let mut f = Fake {
            results: [-1].into(),
            ..Fake::default()
        };
        assert_eq!(sync(&mut f, true, 1.0), (-1, false, false));
        assert_eq!(f.events, ["effect", "effect", "call"]);
    }

    #[test]
    fn blocking_connect_runs_the_proxy_and_tls_handshakes() {
        let mut f = Fake {
            results: [0, 3, 5, 9, 9].into(),
            socks: true,
            ready_after: 2,
            ..Fake::default()
        };
        assert_eq!(sync(&mut f, false, 0.0), (3, true, false));
        assert_eq!(
            f.events,
            [
                "effect",
                "call",
                "call",
                "effect",
                "io",
                "effect",
                "io",
                "handshake",
                "io",
                "handshake"
            ]
        );
        let mut f = Fake {
            results: [0, 0, 4, 0].into(),
            http: true,
            ..Fake::default()
        };
        assert_eq!(sync(&mut f, false, 0.0), (-1, true, false));
        let mut f = Fake {
            results: [0, 0, -1].into(),
            ssl: true,
            ..Fake::default()
        };
        assert_eq!(sync(&mut f, false, 0.0), (-1, true, false));
        let mut f = Fake {
            results: [0, -7].into(),
            ..Fake::default()
        };
        assert_eq!(sync(&mut f, false, 0.0), (-7, false, false));
    }
}
