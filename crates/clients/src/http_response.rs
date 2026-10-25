//! Copied-fact HTTP receive/parse/result sequencing. No parser, socket or Zend
//! effect executes in Rust; no span survives native parser callbacks.
#[repr(C)]
pub struct HttpResponsePlan {
    pub action: u32,
    pub stage: u32,
    pub offset: usize,
}
/// Stage-local facts and sizes are sampled only at the original observation.
/// size is header length at stage5, received size at13; parsed is consumed bytes.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_clients_http_response_next(
    stage: u32,
    facts: u32,
    size: usize,
    parsed: usize,
    websocket_header: usize,
) -> HttpResponsePlan {
    let mut offset = 0;
    let (action, stage) = match stage {
        0 if facts != 0 => (0, 1),
        0 => (1, 0),
        1 if facts != 0 => (2, 0), // native failure properties + close
        1 => (3, 2),               // recv
        2 if facts == 0 => (2, 0), // recv negative
        2 if facts == 1 => (4, 3), // EOF set ECONNRESET
        2 => (0, 4),
        3 if facts != 0 => (5, 30), // finish EOF-delimited parser
        3 => (2, 0),
        4 if facts != 0 => (8, 9), // already header-complete: parse
        4 => (6, 5),               // append and find header terminator
        5 if facts & 1 != 0 => (7, 8),
        5 if facts & 2 != 0 => (9, 20), // header too large
        5 => {
            offset = size.saturating_sub(4);
            (10, 1)
        }
        8 => (8, 9),
        9 if facts != 0 => (2, 0), // callback deferred socket close
        9 => (0, 10),
        10 if facts != 0 => (0, 11),
        10 => (11, 20), // invalid protocol
        11 if facts != 0 => (5, 12),
        11 => (0, 12),
        12 if facts != 0 => (0, 13),
        12 => (0, 1),
        13 if facts != 0 && size > parsed.wrapping_add(websocket_header) => (12, 30),
        13 => (0, 30),
        20 => (2, 0),
        30 if facts != 0 => (13, 31), // configure websocket framing
        30 => (0, 31),
        31 if facts != 0 => (14, 0), // close then true, no subsequent Socket read
        31 => (15, 0),               // reset then true
        _ => (1, 0),
    };
    HttpResponsePlan {
        action,
        stage,
        offset,
    }
}
