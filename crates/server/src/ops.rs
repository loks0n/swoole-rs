//! Operation and op numbers shared with `native/include/swoole_rs.h` (`SWR_SERVER_*`).
//! The native context carries the server and, per operation, the reactor, port,
//! socket and connection an op acts on.

// Operations `swr_v1_server_run` runs.
/// `Server::accept_connection`: context reactor and event.
pub const RUN_ACCEPT: u32 = 0;
/// `Server::add_connection`: context port and socket, arg the server fd. 1 when the
/// connection was added (and is now the context's), else 0.
pub const RUN_ADD_CONNECTION: u32 = 1;
/// `Server::connection_incoming`: context reactor, port and connection.
pub const RUN_INCOMING: u32 = 2;
/// The idle-timeout timer of a connection: context reactor, port and connection.
pub const RUN_IDLE_TIMEOUT: u32 = 3;
pub const RUN_DISABLE_ACCEPT: u32 = 4;
/// The retry timer `disable_accept` armed.
pub const RUN_ENABLE_ACCEPT: u32 = 5;
/// `Server::set_max_connection(arg)`.
pub const RUN_SET_MAX_CONNECTION: u32 = 6;
/// `Server::is_healthy_connection`: arg the `double` now, context port and connection.
pub const RUN_HEALTHY: u32 = 7;
pub const RUN_SHUTDOWN: u32 = 8;
/// `Server::master_signal_handler(arg)`.
pub const RUN_SIGNAL: u32 = 9;
pub const RUN_SIGNAL_SHUTDOWN: u32 = 10;
pub const RUN_CHILD_EXIT: u32 = 11;
pub const RUN_STOP_MASTER_THREAD: u32 = 12;
/// `Server::timer_callback`, once a second in the master.
pub const RUN_MASTER_TIMER: u32 = 13;
pub const RUN_INIT_SIGNALS: u32 = 14;

// Server facts.
pub const OP_MODE: u32 = 0;
pub const OP_SINGLE_THREAD: u32 = 1;
pub const OP_MAX_CONNECTION: u32 = 2;
/// `errno`.
pub const OP_ERRNO: u32 = 3;
/// `connection_list != nullptr`.
pub const OP_CONNECTION_LIST: u32 = 4;
/// `SwooleG.max_sockets`.
pub const OP_MAX_SOCKETS: u32 = 5;
pub const OP_SET_MAX_CONNECTION: u32 = 6;
pub const OP_DELAY_RECEIVE: u32 = 7;
/// `onConnect` is set.
pub const OP_HAS_ON_CONNECT: u32 = 8;
pub const OP_DISABLE_NOTIFY: u32 = 9;
pub const OP_IS_STARTED: u32 = 10;
/// `is_running()`.
pub const OP_RUNNING: u32 = 11;
pub const OP_SET_RUNNING: u32 = 12;
pub const OP_MASTER_PID: u32 = 13;
pub const OP_MANAGER_PID: u32 = 14;
pub const OP_IS_MASTER_THREAD: u32 = 15;
/// `SwooleG.running && serv && serv->is_running()`.
pub const OP_SIGNAL_ACTIVE: u32 = 16;
/// `max_wait_time`.
pub const OP_MAX_WAIT_TIME: u32 = 17;
/// `SIGRTMIN`, or 0 where it is not defined.
pub const OP_SIGRTMIN: u32 = 18;
/// `SwooleG.signal_fd`.
pub const OP_SIGNAL_FD: u32 = 19;
pub const OP_MAXFD: u32 = 20;
pub const OP_MINFD: u32 = 21;
pub const OP_SET_MAXFD: u32 = 22;
pub const OP_SET_MINFD: u32 = 23;
/// `swoole_set_last_error(SW_ERROR_WRONG_OPERATION)`.
pub const OP_WRONG_OPERATION: u32 = 24;
/// The scheduler warning of the server (arg 0) or the task pool (arg 1) is set.
pub const OP_WARNING: u32 = 25;
pub const OP_WARNING_TIME: u32 = 26;
/// Clears the warning of pool `arg & 1` and stamps its time with `arg >> 1`.
pub const OP_WARNING_RESET: u32 = 27;

// Listen ports, by index in `ports`.
pub const OP_PORT_COUNT: u32 = 30;
pub const OP_PORT_DGRAM: u32 = 31;
/// `swoole_event_add(port->socket, SW_EVENT_READ)`, `swoole_event_del(port->socket)`.
pub const OP_PORT_EVENT_ADD: u32 = 32;
pub const OP_PORT_EVENT_DEL: u32 = 33;
pub const OP_PORT_REMOVED: u32 = 34;
/// `SwooleTG.reactor->del(port->socket)`.
pub const OP_PORT_REACTOR_DEL: u32 = 35;

// The context's listen port.
pub const OP_PORT_SSL: u32 = 40;
/// `max_idle_time`, a `double`.
pub const OP_PORT_IDLE_TIME: u32 = 41;
/// `open_tcp_nodelay && socket->is_tcp()`.
pub const OP_PORT_NODELAY: u32 = 42;
pub const OP_PORT_RCVBUF: u32 = 43;
pub const OP_PORT_SNDBUF: u32 = 44;
/// The context has a port (`get_port_by_session_id` found one).
pub const OP_HAS_PORT: u32 = 45;
/// `heartbeat_idle_time`, a `double`.
pub const OP_PORT_HEARTBEAT: u32 = 46;

// The context's socket and connection.
/// `event->socket->accept()` becomes the context's socket; whether there was one.
pub const OP_ACCEPT: u32 = 50;
pub const OP_SOCK_FD: u32 = 51;
/// `port->ssl_create(socket)`.
pub const OP_SSL_CREATE: u32 = 52;
/// `socket->ssl = nullptr`.
pub const OP_SSL_CLEAR: u32 = 53;
/// `abort_connection(reactor, port, socket)`.
pub const OP_ABORT: u32 = 54;
/// `socket->chunk_size = SW_SEND_BUFFER_SIZE`.
pub const OP_CHUNK_SIZE: u32 = 55;
/// Sends `SW_SERVER_EVENT_INCOMING` to the reactor thread; the `send_to_reactor_thread` result.
pub const OP_SEND_INCOMING: u32 = 56;
/// The event's fd (the listening socket).
pub const OP_EVENT_FD: u32 = 57;
/// Picks `connection_list[fd]`, zeroes it up to `closed` and returns its reactor id.
pub const OP_CONN_RESET: u32 = 58;
pub const OP_SPIN_LOCK: u32 = 59;
pub const OP_SPIN_UNLOCK: u32 = 60;
/// `gs->session_round`.
pub const OP_SESSION_ROUND: u32 = 61;
/// Takes session `arg` when its slot is free; whether it did.
pub const OP_SESSION_CLAIM: u32 = 62;
/// `gs->session_round = arg`, the connection's session id, and the socket's
/// object, `removed`, buffer size and timeouts.
pub const OP_SESSION_BIND: u32 = 63;
/// `set_tcp_nodelay()`, then `enable_tcp_nodelay`.
pub const OP_SET_NODELAY: u32 = 64;
pub const OP_NODELAY_ENABLED: u32 = 65;
/// `port->socket->set_option(SOL_SOCKET, SO_RCVBUF/SO_SNDBUF, ...)`.
pub const OP_SET_RCVBUF: u32 = 66;
pub const OP_SET_SNDBUF: u32 = 67;
/// The connection's fields, peer and local address; arg the server fd.
pub const OP_CONN_INIT: u32 = 68;
pub const OP_DIRECT_SEND: u32 = 69;
/// `lock()`, `unlock()`.
pub const OP_LOCK: u32 = 70;
pub const OP_UNLOCK: u32 = 71;
/// The accept and connection counters of the server and port.
pub const OP_COUNT_ACCEPT: u32 = 72;
/// Arms the receive idle timer.
pub const OP_ADD_RECV_TIMER: u32 = 73;
pub const OP_SOCK_SSL: u32 = 74;
/// `reactor->add(socket, SW_EVENT_READ)`.
pub const OP_REACTOR_ADD_READ: u32 = 75;
/// `notify(conn, SW_SERVER_EVENT_CONNECT)`.
pub const OP_NOTIFY_CONNECT: u32 = 76;
pub const OP_CONN_PROTECT: u32 = 77;
/// `time<std::chrono::milliseconds>(true)`, a `double`.
pub const OP_NOW_MS: u32 = 78;
/// The socket's `last_received_time` and `last_sent_time`, `double`s.
pub const OP_LAST_RECEIVED: u32 = 79;
pub const OP_LAST_SENT: u32 = 80;
/// `conn->closed || conn->close_force`.
pub const OP_CONN_CLOSING: u32 = 81;
/// `close_connection(reactor, socket)`.
pub const OP_CLOSE_CONNECTION: u32 = 82;
/// `close_force = 1` and the reactor's close event.
pub const OP_FORCE_CLOSE: u32 = 83;
/// `conn->last_recv_time`, a `double`.
pub const OP_CONN_LAST_RECV: u32 = 84;

// Timers, signals and shutdown.
/// Arms the accept retry timer; whether it was armed.
pub const OP_ACCEPT_TIMER: u32 = 90;
pub const OP_ACCEPT_TIMER_CLEAR: u32 = 91;
/// Sends `SW_SERVER_EVENT_SHUTDOWN_SIGNAL` to reactor 0; whether it was sent.
pub const OP_SEND_SHUTDOWN: u32 = 92;
/// `swoole_kill(arg, SIGTERM)`.
pub const OP_KILL_TERM: u32 = 93;
/// `SwooleTG.reactor->set_wait_exit(true)`.
pub const OP_REACTOR_WAIT_EXIT: u32 = 94;
/// Deletes the command pipe from the reactor when there is one.
pub const OP_PIPE_COMMAND_DEL: u32 = 95;
pub const OP_CLEAR_TIMER: u32 = 96;
/// The forced-termination exit condition after `max_wait_time`.
pub const OP_FORCED_EXIT: u32 = 97;
pub const OP_STOP_WORKER_THREADS: u32 = 98;
/// `get_thread(0)->shutdown(reactor)`.
pub const OP_THREAD0_SHUTDOWN: u32 = 99;
/// The event pool stops and the async worker exits (single-process base mode).
pub const OP_STOP_SINGLE_WORKER: u32 = 100;
/// `SW_GLOBAL_HOOK_BEFORE_SERVER_SHUTDOWN` then `onBeforeShutdown`, each when set.
pub const OP_BEFORE_SHUTDOWN: u32 = 101;
pub const OP_SIGNAL_RELOAD: u32 = 102;
pub const OP_SIGNAL_READ_MESSAGE: u32 = 103;
pub const OP_SIGNAL_REOPEN: u32 = 104;
/// `swoole_signal_set(arg, nullptr)` and `swoole_signal_set(arg, master_signal_handler)`.
pub const OP_SIGNAL_IGNORE: u32 = 105;
pub const OP_SIGNAL_HANDLE: u32 = 106;
/// `HOOK_MASTER_TIMER`, when set.
pub const OP_MASTER_TIMER_HOOK: u32 = 107;
/// `sw_reactor()->running = false`.
pub const OP_REACTOR_STOP: u32 = 108;

// Logs, in upstream's wording; arg is the one number a log needs beyond native state.
pub const LOG_ACCEPT_FAILED: u32 = 120;
pub const LOG_TOO_MANY_CONNECTIONS: u32 = 121;
pub const LOG_NO_SESSION_SLOT: u32 = 122;
pub const LOG_NODELAY: u32 = 123;
pub const LOG_RCVBUF: u32 = 124;
pub const LOG_SNDBUF: u32 = 125;
pub const LOG_MAX_CONNECTION_CREATED: u32 = 126;
pub const LOG_MAX_CONNECTION_SESSIONS: u32 = 127;
pub const LOG_MAX_CONNECTION_SOCKETS: u32 = 128;
pub const LOG_SHUTDOWN_FAILED: u32 = 129;
/// arg the `waitpid` status.
pub const LOG_MANAGER_EXIT: u32 = 130;
/// arg 0 the server, 1 the task pool.
pub const LOG_NO_IDLE_WORKER: u32 = 131;
pub const TRACE_ACCEPT: u32 = 140;
pub const TRACE_TIMEOUT: u32 = 141;
/// arg the signal.
pub const TRACE_SIGNAL: u32 = 142;
pub const TRACE_SHUTDOWN_BEGIN: u32 = 143;
pub const TRACE_SHUTDOWN_END: u32 = 144;

#[cfg(test)]
mod tests {
    use std::collections::HashMap;

    /// `NAME = value` of the header's `SWR_SERVER_*` enumerators, counting on from the last value.
    fn header() -> HashMap<String, u32> {
        let text = include_str!("../../../native/include/swoole_rs.h");
        let mut out = HashMap::new();
        for block in text.split("enum {").skip(1) {
            let body = block.split("};").next().unwrap_or_default();
            let mut next = 0;
            for item in body
                .split(',')
                .map(str::trim)
                .filter(|item| !item.is_empty())
            {
                let (name, value) = match item.split_once('=') {
                    Some((name, value)) => (name.trim(), value.trim().parse().unwrap()),
                    None => (item, next),
                };
                out.insert(name.to_owned(), value);
                next = value + 1;
            }
        }
        out
    }

    #[test]
    fn numbers_match_the_header() {
        let header = header();
        let mut checked = 0;
        for line in include_str!("ops.rs").lines() {
            let Some(rest) = line.strip_prefix("pub const ") else {
                continue;
            };
            let (name, value) = rest.split_once(": u32 = ").unwrap();
            let value: u32 = value.trim_end_matches(';').parse().unwrap();
            let native = format!("SWR_SERVER_{name}");
            assert_eq!(header.get(&native), Some(&value), "{native}");
            checked += 1;
        }
        assert_eq!(checked, header.len(), "every enumerator has a Rust number");
    }
}
