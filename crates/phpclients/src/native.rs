//! What only C++ can do, defined in the patched `ext-src/swoole_socket_coro.cc`
//! (declared in `native/clients/swoole_rs_phpclients.h`): the coroutine
//! `Socket` class (`SocketImpl`) is still C++, so each operation a method needs
//! is one call over its opaque pointer, plus Swoole's PHP error reporting.
use libc::{c_char, c_int, iovec, size_t, ssize_t};
use swoole_rs_zend::sys::{zend_object, zend_string, zval};

/// A `SocketImpl *`.
pub(crate) type Socket = *mut libc::c_void;

unsafe extern "C" {
    /// `php_swoole_error(level, "%s", message)`, or with `fatal`
    /// `php_swoole_fatal_error`.
    pub(crate) fn swoole_rs_php_error(level: c_int, fatal: bool, message: *const c_char);
    /// `swoole_fatal_error(SW_ERROR_WRONG_OPERATION, "must call constructor first")`.
    pub(crate) fn swoole_socket_coro_unconstructed();
    /// `php_swoole_check_reactor()`, then `new SocketImpl(domain, type, protocol)`;
    /// null with `errno` in `error` when it has no fd.
    pub(crate) fn swoole_socket_coro_create(
        domain: i64,
        kind: i64,
        protocol: i64,
        error: *mut c_int,
    ) -> Socket;
    /// `socket_coro_init`: zero-copy, the zend string allocator, and the fd,
    /// domain, type and protocol properties of `object`'s socket.
    pub(crate) fn swoole_socket_coro_init(object: *mut zend_object);
    /// `socket_coro_free_object` up to `zend_object_std_dtor`.
    pub(crate) fn swoole_socket_coro_release(object: *mut zend_object);
    /// `close()` after the reference check: free the length callable, then
    /// release an imported stream or close the socket.
    pub(crate) fn swoole_socket_coro_close(object: *mut zend_object);
    pub(crate) fn swoole_socket_coro_is_closed(socket: Socket) -> bool;
    /// `errCode`, with `errMsg` in `message`.
    pub(crate) fn swoole_socket_coro_error(socket: Socket, message: *mut *const c_char) -> c_int;
    /// `set_err(code, message)`.
    pub(crate) fn swoole_socket_coro_set_error(socket: Socket, code: c_int, message: *const c_char);
    pub(crate) fn swoole_socket_coro_bind(
        socket: Socket,
        address: *const c_char,
        length: size_t,
        port: i64,
    ) -> bool;
    pub(crate) fn swoole_socket_coro_listen(socket: Socket, backlog: i64) -> bool;
    /// `accept(timeout)`; the connection copies the listener's length callable.
    pub(crate) fn swoole_socket_coro_accept(socket: Socket, timeout: f64) -> Socket;
    pub(crate) fn swoole_socket_coro_port_required(socket: Socket) -> bool;
    /// `connect(host, port)` under a connect timeout of `timeout`.
    pub(crate) fn swoole_socket_coro_connect(
        socket: Socket,
        host: *const c_char,
        length: size_t,
        port: i64,
        timeout: f64,
    ) -> bool;
    pub(crate) fn swoole_socket_coro_check_liveness(socket: Socket) -> bool;
    pub(crate) fn swoole_socket_coro_bound_cid(socket: Socket, event: i64) -> i64;
    /// One `Transfer` of `length` bytes at `buffer` under `timeout`.
    pub(crate) fn swoole_socket_coro_transfer(
        socket: Socket,
        op: c_int,
        buffer: *mut c_char,
        length: size_t,
        timeout: f64,
    ) -> ssize_t;
    /// `recv_packet(timeout)`; with `clear_empty`, an empty packet clears the
    /// read buffer.
    pub(crate) fn swoole_socket_coro_recv_packet(
        socket: Socket,
        timeout: f64,
        clear_empty: bool,
    ) -> ssize_t;
    /// `pop_packet()`: the `ZSTR_VAL` of the packet's string, or null after
    /// `set_err(ENOMEM)`.
    pub(crate) fn swoole_socket_coro_pop_packet(socket: Socket) -> *mut c_char;
    /// `readv`/`readv_all`/`writev`/`writev_all` (`op` 0..=3) over `count`
    /// vectors under `timeout`; `index` and `offset` report where it stopped.
    pub(crate) fn swoole_socket_coro_vector(
        socket: Socket,
        op: c_int,
        vectors: *mut iovec,
        count: c_int,
        timeout: f64,
        index: *mut c_int,
        offset: *mut size_t,
    ) -> ssize_t;
    pub(crate) fn swoole_socket_coro_sendfile(
        socket: Socket,
        file: *const c_char,
        offset: i64,
        length: i64,
    ) -> bool;
    /// `recvfrom(buffer, length)` under a read timeout of `timeout`.
    pub(crate) fn swoole_socket_coro_recvfrom(
        socket: Socket,
        buffer: *mut c_char,
        length: size_t,
        timeout: f64,
    ) -> ssize_t;
    /// `get_addr()`, with `get_port()` in `port`.
    pub(crate) fn swoole_socket_coro_address(socket: Socket, port: *mut c_int) -> *const c_char;
    pub(crate) fn swoole_socket_coro_sendto(
        socket: Socket,
        address: *const c_char,
        length: size_t,
        port: i64,
        data: *const c_char,
        data_length: size_t,
    ) -> ssize_t;
    pub(crate) fn swoole_socket_coro_shutdown(socket: Socket, how: i64) -> bool;
    pub(crate) fn swoole_socket_coro_getsockname(socket: Socket) -> bool;
    /// `getpeername(&sa)`: the address, NUL-terminated, into `address`.
    pub(crate) fn swoole_socket_coro_getpeername(
        socket: Socket,
        address: *mut c_char,
        size: size_t,
        port: *mut c_int,
    ) -> bool;
    pub(crate) fn swoole_socket_coro_cancel(socket: Socket, event: c_int) -> bool;
    pub(crate) fn swoole_socket_coro_ssl_handshake(socket: Socket) -> bool;
    /// `php_swoole_check_reactor()`.
    pub(crate) fn swoole_rs_check_reactor();
    /// `swoole_set_last_error(code)`.
    pub(crate) fn swoole_rs_set_last_error(code: c_int);
    /// `client_coro_create_socket`: a `Coroutine\Socket` for the client's
    /// `type`, published in its `socket` and `fd` properties; null on failure,
    /// with errCode/errMsg set.
    pub(crate) fn swoole_client_coro_create_socket(object: *mut zend_object, kind: i64) -> Socket;
    /// `php_swoole_socket_set(socket, settings)`.
    pub(crate) fn swoole_client_coro_apply(socket: Socket, settings: *const zval) -> bool;
    /// Merge `settings` into the client's `setting` property.
    pub(crate) fn swoole_client_coro_merge_setting(object: *mut zend_object, settings: *const zval);
    /// The client's `setting` property.
    pub(crate) fn swoole_client_coro_setting(object: *mut zend_object) -> *mut zval;
    /// `zval_get_long` of the client's `type` property.
    pub(crate) fn swoole_client_coro_type_property(object: *mut zend_object) -> i64;
    /// `set_timeout(timeout, SW_TIMEOUT_CONNECT)`, then `connect(host, port, flags)`.
    pub(crate) fn swoole_client_coro_connect(
        socket: Socket,
        host: *const c_char,
        port: i64,
        timeout: f64,
        flags: i64,
    ) -> bool;
    /// `set_timeout(timeout, SW_TIMEOUT_RDWR)`.
    pub(crate) fn swoole_client_coro_rdwr_timeout(socket: Socket, timeout: f64);
    pub(crate) fn swoole_client_coro_close(socket: Socket) -> bool;
    pub(crate) fn swoole_client_coro_is_tcp(socket: Socket) -> bool;
    pub(crate) fn swoole_client_coro_type(socket: Socket) -> c_int;
    /// `open_length_check || open_eof_check`.
    pub(crate) fn swoole_client_coro_packet_mode(socket: Socket) -> bool;
    pub(crate) fn swoole_client_coro_is_connected(socket: Socket) -> bool;
    pub(crate) fn swoole_client_coro_has_ssl(socket: Socket) -> bool;
    /// Encrypt a plain socket, applying the `setting` SSL options: 0, or the
    /// errno to report (EISCONN).
    pub(crate) fn swoole_client_coro_enable_ssl(object: *mut zend_object, socket: Socket) -> c_int;
    /// The peer certificate as a new string, or null.
    pub(crate) fn swoole_client_coro_peer_cert(socket: Socket) -> *mut zend_string;
    pub(crate) fn swoole_client_coro_verify_peer(socket: Socket, allow_self_signed: bool) -> bool;
    /// `php_swoole_socket_set_protocol(socket, settings)`.
    pub(crate) fn swoole_socket_coro_set_protocol(socket: Socket, settings: *const zval) -> bool;
}

/// What `swoole_socket_coro_transfer` does.
#[derive(Clone, Copy)]
#[repr(i32)]
pub(crate) enum Transfer {
    Peek = 0,
    Recv = 1,
    RecvAll = 2,
    RecvLine = 3,
    RecvWithBuffer = 4,
    Send = 5,
    SendAll = 6,
}
