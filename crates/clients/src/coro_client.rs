//! PHP coroutine Client decisions over copied facts/results. Native Socket,
//! Zend parsing/bailouts, strings and timeout RAII remain outside Rust frames.
#[repr(C)]
pub struct ClientsCoroPlan {
    pub action: u32,
    pub stage: u32,
}
/// Operation0 setup helper;1 connect;2 send;3 recv;4 sendfile. Facts are
/// Operations5..10 cover datagram/peek/connected/endpoint/close bindings. Facts
/// are stage-local, result is native ssize_t, length is a native initialized size.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_clients_coro_next(
    operation: u32,
    stage: u32,
    facts: u32,
    result: isize,
    length: usize,
) -> ClientsCoroPlan {
    let (action, stage) = match (operation, stage) {
        (0, 0) if facts != 0 => (14, 0), // existing Socket -> EISCONN
        (0, 0) => (15, 1),
        (0, 1) if facts != 0 => (16, 2), // TCP port check
        (0, 1) => (17, 3),
        (0, 2) if facts != 0 => (17, 3),
        (0, 2) => (21, 0),
        (0, 3) if facts != 0 => (18, 4),
        (0, 3) => (2, 0),
        (0, 4) if facts != 0 => (19, 5),
        (0, 4) | (0, 5) => (20, 0),
        (1, 0) if length == 0 => (22, 0),
        (1, 0) => (25, 1), // get Socket
        (1, 1) if facts != 0 => (26, 2),
        (1, 1) => (2, 0),
        (1, 2) => (27, 3),
        (1, 3) if facts != 0 => (28, 4),
        (1, 3) => (29, 0),
        (1, 4) => (30, 5),
        (1, 5) => (1, 0),
        (2, 0) if length == 0 => (23, 0),
        (2, 0) => (0, 0),
        (2, 1) if result < 0 => (3, 0),
        (2, 1) if (result as usize) < length && facts != 0 => (4, 0),
        (2, 1) => (5, 0),
        (3, 0) if facts != 0 => (8, 0), // framed receive
        (3, 0) => (9, 0),
        (3, 1) if result > 0 => (10, 0),
        (3, 1) => (0, 0),
        (3, 2) if facts == 0 => (11, 0),
        (3, 2) => (12, 0),
        (3, 3) if result <= 0 => (13, 0), // free raw result inside TimeoutSetter scope
        (3, 3) => (0, 0),
        (3, 4) if result < 0 => (3, 0),
        (3, 4) if result == 0 => (6, 0),
        (3, 4) => (7, 0),
        (4, 0) if length == 0 => (24, 0),
        (4, 0) => (0, 0),
        (4, 1) if facts == 0 => (31, 0), // datagram cannot sendfile
        (4, 1) => (0, 0),
        (4, 2) if facts == 0 => (3, 0),
        (4, 2) => (1, 0),
        (5, 0) if length == 0 => (2, 0),
        (5, 0) => (0, 0),
        (5, 1) if facts != 0 => (20, 0), // existing native Socket
        (5, 1) => (17, 0),
        (5, 2) if facts != 0 => (16, 0), // stream sendto port validation
        (5, 2) => (0, 0),
        (5, 3) if facts == 0 => (21, 0),
        (5, 3) => (0, 0),
        (5, 4) if result < 0 => (3, 0),
        (5, 4) => (1, 0),
        (6, 0) if result <= 0 => (2, 0),
        (6, 0) => (0, 0),
        (6, 1) if result < 0 => (13, 0), // recvfrom frees before error publication
        (6, 1) => (7, 0),
        (6, 2) if facts != 0 => (1, 0),
        (6, 2) => (0, 0),
        (7, 0) if result < 0 => (3, 0), // peek publishes error before free
        (7, 0) => (7, 0),
        (8, 0) if facts == 0 => (2, 0),
        (8, 0) => (25, 0),
        (8, 1) | (9, 0) | (10, 0) if facts != 0 => (1, 0),
        (8, 1) => (2, 0),
        (9, 0) | (10, 0) => (3, 0),
        _ => (2, 0),
    };
    ClientsCoroPlan { action, stage }
}
