//! `Client_udp_connect` and `Client_tcp_send_async` of `network::Client` as whole
//! operations over the Rust-owned `ClientState`. Native code keeps the `Socket`,
//! DTLS, the reactor and the callbacks, and passes them in `UdpConnectOps` and
//! `SendOps`; it reads each fact afresh. A callback that throws returns false:
//! Rust stops there and native rethrows after it returns.
use crate::state::{
    ACTIVE, ASYNC, ClientState, ONERROR_CALLED, WAIT_DNS, swr_v1_clients_flag,
    swr_v1_clients_set_flag,
};
use core::ffi::c_void;

macro_rules! call {
    ($ops:ident . $effect:ident $(, $arg:expr)*) => {
        // SAFETY: a native effect on the live client in `context`.
        unsafe { ($ops.$effect)($ops.context $(, $arg)*) }
    };
}

fn flag(state: *mut ClientState, name: u32) -> bool {
    // SAFETY: the client's live handle.
    unsafe { swr_v1_clients_flag(state, name) }
}

fn set(state: *mut ClientState, name: u32, value: bool) {
    // SAFETY: the client's live handle, not borrowed across this call.
    unsafe { swr_v1_clients_set_flag(state, name, value) };
}

/// The client's effects for a datagram (or Unix datagram) connect.
#[repr(C)]
pub struct UdpConnectOps {
    pub context: *mut c_void,
    pub state: *mut ClientState,
    pub timeout: f64,
    /// The caller's `udp_connect`; DTLS turns it on.
    pub udp_connect: i32,
    pub set_timeout: unsafe extern "C" fn(*mut c_void),
    /// `socket->set_kernel_timeout(timeout)`.
    pub kernel_timeout: unsafe extern "C" fn(*mut c_void),
    /// `sock_flags_ = udp_connect`.
    pub publish_flags: unsafe extern "C" fn(*mut c_void),
    pub address: unsafe extern "C" fn(*mut c_void) -> i32,
    pub has_on_receive: unsafe extern "C" fn(*mut c_void) -> bool,
    pub warn_receive: unsafe extern "C" fn(*mut c_void),
    pub has_on_error: unsafe extern "C" fn(*mut c_void) -> bool,
    pub warn_error: unsafe extern "C" fn(*mut c_void),
    pub dns_lookup: unsafe extern "C" fn(*mut c_void) -> i32,
    /// The socket's buffer size, after Rust activates the client.
    pub activate: unsafe extern "C" fn(*mut c_void),
    /// `socket->set_timeout(timeout)`.
    pub socket_timeout: unsafe extern "C" fn(*mut c_void),
    pub is_unix: unsafe extern "C" fn(*mut c_void) -> bool,
    /// Binds the Unix datagram socket to its path; negative on failure.
    pub bind_unix: unsafe extern "C" fn(*mut c_void) -> i32,
    pub warn_bind: unsafe extern "C" fn(*mut c_void),
    pub open_ssl: unsafe extern "C" fn(*mut c_void) -> bool,
    /// Enables DTLS; false (after its warning) when unsupported.
    pub enable_dtls: unsafe extern "C" fn(*mut c_void) -> bool,
    pub connect: unsafe extern "C" fn(*mut c_void) -> i32,
    pub clean: unsafe extern "C" fn(*mut c_void),
    /// Marks the socket removed and closes the client.
    pub fail_close: unsafe extern "C" fn(*mut c_void),
    /// `onError`; false when it threw.
    pub on_error: unsafe extern "C" fn(*mut c_void) -> bool,
    pub has_on_connect: unsafe extern "C" fn(*mut c_void) -> bool,
    /// `swoole_event_add(socket, SW_EVENT_READ)`.
    pub add_event: unsafe extern "C" fn(*mut c_void) -> i32,
    /// `execute_onConnect`; false when it threw.
    pub on_connect: unsafe extern "C" fn(*mut c_void) -> bool,
    pub ssl_handshake: unsafe extern "C" fn(*mut c_void) -> i32,
}

/// `Client_udp_connect`: 0, -1, or the DNS lookup's result when it must resolve
/// first.
///
/// # Safety
/// `ops` is live for the call; its callbacks act on the client in `context`.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_clients_udp_connect(ops: *const UdpConnectOps) -> i32 {
    // SAFETY: the caller passes a live table (see above).
    let ops = unsafe { &*ops };
    let state = ops.state;
    call!(ops.set_timeout);
    if !flag(state, ASYNC) && ops.timeout > 0.0 {
        call!(ops.kernel_timeout);
    }
    call!(ops.publish_flags);
    if call!(ops.address) < 0 {
        return -1;
    }
    if flag(state, ASYNC) && !call!(ops.has_on_receive) {
        call!(ops.warn_receive);
        return -1;
    }
    if flag(state, WAIT_DNS) && flag(state, ASYNC) {
        if call!(ops.has_on_error) {
            return call!(ops.dns_lookup);
        }
        call!(ops.warn_error);
        return -1;
    }
    set(state, ACTIVE, true);
    call!(ops.activate);
    if ops.timeout > 0.0 {
        call!(ops.socket_timeout);
    }
    if call!(ops.is_unix) && call!(ops.bind_unix) < 0 {
        call!(ops.warn_bind);
        return -1;
    }
    let mut udp_connect = ops.udp_connect;
    if call!(ops.open_ssl) {
        if !call!(ops.enable_dtls) {
            return -1;
        }
        udp_connect = 1;
    }
    if udp_connect == 1 {
        if call!(ops.connect) != 0 {
            set(state, ACTIVE, false);
            call!(ops.fail_close);
            if flag(state, ASYNC) && call!(ops.has_on_error) {
                set(state, ONERROR_CALLED, true);
                call!(ops.on_error);
            }
            return -1;
        }
        call!(ops.clean);
    }
    if flag(state, ASYNC)
        && call!(ops.has_on_connect)
        && (call!(ops.add_event) < 0 || !call!(ops.on_connect))
    {
        return -1;
    }
    if call!(ops.open_ssl) && call!(ops.ssl_handshake) < 0 {
        return -1;
    }
    0
}

/// The client's effects for an async TCP send.
#[repr(C)]
pub struct SendOps {
    pub context: *mut c_void,
    /// `swoole_event_write`'s result.
    pub write: unsafe extern "C" fn(*mut c_void) -> i32,
    /// The last error is `SW_ERROR_OUTPUT_BUFFER_OVERFLOW`.
    pub overflowed: unsafe extern "C" fn(*mut c_void) -> bool,
    /// Sets `high_watermark`.
    pub mark_high: unsafe extern "C" fn(*mut c_void),
    /// `onBufferFull` is set, not yet at the high watermark, and the output
    /// buffer reached it.
    pub full: unsafe extern "C" fn(*mut c_void) -> bool,
    /// `onBufferFull`; false when it threw.
    pub on_buffer_full: unsafe extern "C" fn(*mut c_void) -> bool,
}

/// `Client_tcp_send_async`: `length`, -1 after an overflow (reported once), or -1
/// when the write failed otherwise.
///
/// # Safety
/// `ops` is live for the call; its callbacks act on the client in `context`.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_clients_send_async(ops: *const SendOps, length: isize) -> isize {
    // SAFETY: the caller passes a live table (see above).
    let ops = unsafe { &*ops };
    let mut sent = length;
    if call!(ops.write) < 0 {
        if !call!(ops.overflowed) {
            return -1;
        }
        sent = -1;
        call!(ops.mark_high);
    }
    if call!(ops.full) {
        call!(ops.mark_high);
        call!(ops.on_buffer_full);
    }
    sent
}

#[cfg(test)]
mod tests {
    use super::*;

    #[derive(Default)]
    struct Fake {
        write: i32,
        overflow: bool,
        full: bool,
        events: Vec<&'static str>,
    }
    unsafe fn fake<'a>(c: *mut c_void) -> &'a mut Fake {
        unsafe { &mut *c.cast::<Fake>() }
    }
    unsafe extern "C" fn write(c: *mut c_void) -> i32 {
        unsafe { fake(c) }.write
    }
    unsafe extern "C" fn overflowed(c: *mut c_void) -> bool {
        unsafe { fake(c) }.overflow
    }
    unsafe extern "C" fn mark_high(c: *mut c_void) {
        unsafe { fake(c) }.events.push("high");
    }
    unsafe extern "C" fn full(c: *mut c_void) -> bool {
        unsafe { fake(c) }.full
    }
    unsafe extern "C" fn on_buffer_full(c: *mut c_void) -> bool {
        unsafe { fake(c) }.events.push("full");
        true
    }

    fn send(mut f: Fake) -> (isize, Vec<&'static str>) {
        let ops = SendOps {
            context: (&raw mut f).cast(),
            write,
            overflowed,
            mark_high,
            full,
            on_buffer_full,
        };
        let sent = unsafe { swr_v1_clients_send_async(&raw const ops, 4) };
        (sent, f.events)
    }

    #[test]
    fn async_send_reports_overflow_and_buffer_full() {
        assert_eq!(send(Fake::default()), (4, vec![]));
        assert_eq!(
            send(Fake {
                write: -1,
                ..Fake::default()
            }),
            (-1, vec![])
        );
        assert_eq!(
            send(Fake {
                write: -1,
                overflow: true,
                ..Fake::default()
            }),
            (-1, vec!["high"])
        );
        assert_eq!(
            send(Fake {
                full: true,
                ..Fake::default()
            }),
            (4, vec!["high", "full"])
        );
    }
}
