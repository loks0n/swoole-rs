//! HTTP client connection/keepalive/close sequencing; native effects stay native.
#[repr(C)]
pub struct HttpConnectionPlan {
    pub action: u32,
    pub stage: u32,
    pub iteration: u32,
}
/// Kind0 connect,1 keepalive,2 close. Facts describe only the current stage's
/// original native observation. No pointers, callbacks, allocation or state store.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_clients_http_connection_next(
    kind: u32,
    stage: u32,
    facts: u32,
    iteration: u32,
    retries: u8,
) -> HttpConnectionPlan {
    let mut next_iteration = iteration;
    let (action, stage) = match (kind, stage) {
        (0, 0) if facts != 0 => (1, 0), // already connected
        (0, 0) => (0, 1),
        (0, 1) if facts != 0 => (4, 3), // reactor/create socket
        (0, 1) => (3, 2),               // allocate body
        (0, 2) if facts != 0 => (4, 3),
        (0, 2) => (5, 0), // ENOMEM + false
        (0, 3) if facts != 0 => (7, 4),
        (0, 3) => (6, 0), // errno + false
        (0, 4) if facts != 0 => (8, 5),
        (0, 4) => (10, 7),
        (0, 5) if facts != 0 => (10, 7),
        (0, 5) => (9, 0), // socket error, close, false
        (0, 7) => (11, 8),
        (0, 8) => (12, 9),
        (0, 9) => (13, 10),
        (0, 10) if facts != 0 => (14, 11),
        (0, 10) => (9, 0),
        (0, 11) => (1, 0),
        (1, 0) if facts != 0 => (15, 1), // check liveness
        (1, 0) => (0, 2),
        (1, 1) if facts != 0 => (1, 0),
        (1, 1) => (0, 2),
        (1, 2) if facts != 0 => (16, 3), // bound check,error,close(false)
        (1, 2) => (0, 3),
        (1, 3) if iteration < u32::from(retries) + 1 => (17, 4),
        (1, 3) => (2, 0),
        (1, 4) if facts != 0 => (1, 0),
        (1, 4) => {
            next_iteration = iteration.saturating_add(1);
            (0, 3)
        }
        (2, 0) if facts & 1 == 0 => (2, 0),
        (2, 0) if facts & 2 != 0 => (18, 0), // defer close + true
        (2, 0) => (19, 1),
        (2, 1) => (20, 2),
        (2, 2) if facts == 0 => (21, 0), // saved socket error + false
        (2, 2) => (0, 3),
        (2, 3) if facts != 0 => (22, 4),
        (2, 3 | 4) => (1, 0),
        _ => (2, 0),
    };
    HttpConnectionPlan {
        action,
        stage,
        iteration: next_iteration,
    }
}
