//! `ListenPort`'s readable callbacks (raw, length, EOF, Redis and HTTP) as whole
//! operations. Native code keeps the socket, connection, receive buffer, request
//! object, logs and dispatch; Rust decides every step and asks native code for each
//! fact or effect through one `call(context, op, arg)`, reading facts afresh.
use core::ffi::c_void;

/// One native fact or effect on the connection in `context`.
pub type PortsCall = unsafe extern "C" fn(context: *mut c_void, op: u32, arg: u64) -> u64;

/// Which readable callback runs.
pub const ON_READ_RAW: u32 = 0;
pub const ON_READ_LENGTH: u32 = 1;
pub const ON_READ_EOF: u32 = 2;
pub const ON_READ_REDIS: u32 = 3;
pub const ON_READ_HTTP: u32 = 4;

// Socket and connection.
/// `recv` into the buffer: arg 0 its free tail, 1 the whole buffer. Returns the `ssize_t`.
pub const OP_RECV: u32 = 0;
/// `catch_read_error(errno)`, the raw `swReturnCode`.
pub const OP_CATCH: u32 = 1;
pub const OP_WARN_RECV: u32 = 2;
/// `conn->close_errno = errno`.
pub const OP_CLOSE_ERRNO: u32 = 3;
/// `reactor->trigger_close_event(event)`.
pub const OP_CLOSE: u32 = 4;
/// Sends a canned packet: `SEND_*`.
pub const OP_SEND: u32 = 5;
/// `serv->get_recv_buffer(socket)` becomes the current buffer; returns non-null.
pub const OP_RECV_BUFFER: u32 = 6;
/// Frees the socket's receive buffer when larger than twice `SW_BUFFER_SIZE_BIG`
/// (arg 1: and empty). Returns whether it did.
pub const OP_RELEASE: u32 = 7;
/// `protocol.recv_with_length_protocol`, `recv_with_eof_protocol`, `redis::recv_packet`.
pub const OP_RECV_LENGTH: u32 = 8;
pub const OP_RECV_EOF: u32 = 9;
pub const OP_RECV_REDIS: u32 = 10;
/// `Server::dispatch_task` of arg bytes from the buffer start.
pub const OP_DISPATCH_TASK: u32 = 11;
/// `http_server::dispatch_request` of arg bytes from the buffer start.
pub const OP_DISPATCH_REQUEST: u32 = 12;
/// `conn->active && !socket->removed`.
pub const OP_ACTIVE: u32 = 13;
/// `websocket_status >= STATUS_HANDSHAKE`, `http_upgrade`, `http2_stream`.
pub const OP_WEBSOCKET: u32 = 14;
pub const OP_UPGRADED: u32 = 15;
pub const OP_HTTP2_STREAM: u32 = 16;
/// Sets `websocket_status = STATUS_ACTIVE` and `http_upgrade = 1`.
pub const OP_WEBSOCKET_ACTIVATE: u32 = 17;
/// `open_http2_protocol`.
pub const OP_HTTP2_ENABLED: u32 = 18;
/// Sets `http2_stream` and sends the settings frame.
pub const OP_HTTP2_START: u32 = 19;
/// `socket->skip_recv = 1`.
pub const OP_SKIP_RECV: u32 = 20;
/// `protocol.package_max_length`, `serv->upload_max_filesize > 0`.
pub const OP_MAX_LENGTH: u32 = 21;
pub const OP_UPLOADS: u32 = 22;
/// `enable_static_handler` and the static handler served the request.
pub const OP_STATIC: u32 = 23;

// The current buffer.
pub const OP_BUF_LENGTH: u32 = 30;
pub const OP_BUF_SIZE: u32 = 31;
pub const OP_BUF_OFFSET: u32 = 32;
pub const OP_BUF_ADD_LENGTH: u32 = 33;
pub const OP_BUF_SET_LENGTH: u32 = 34;
pub const OP_BUF_SET_OFFSET: u32 = 35;
pub const OP_BUF_REDUCE: u32 = 36;
pub const OP_BUF_CLEAR: u32 = 37;
pub const OP_BUF_EXTEND: u32 = 38;
/// The buffer holds `\r\n\r\n`.
pub const OP_BUF_HEADER_END: u32 = 39;

// The connection's HTTP request.
/// Creates the request when missing, gives it the receive buffer when it has none,
/// and makes its buffer current.
pub const OP_REQ_INIT: u32 = 50;
/// `port->destroy_http_request(conn)`.
pub const OP_REQ_DESTROY: u32 = 51;
pub const OP_REQ_METHOD: u32 = 52;
/// `get_protocol()`, `get_header_length()`, `get_chunked_body_length()`: `int`s.
pub const OP_REQ_PROTOCOL: u32 = 53;
pub const OP_REQ_FIND_HEADER: u32 = 54;
pub const OP_REQ_FIND_CHUNKED: u32 = 55;
pub const OP_REQ_EXCEPTED: u32 = 56;
pub const OP_REQ_HEADER_LENGTH: u32 = 57;
pub const OP_REQ_HEADER_PARSED: u32 = 58;
/// `parse_header_info()`, then `set_max_length(package_max_length)`.
pub const OP_REQ_PARSE_HEADER: u32 = 59;
pub const OP_REQ_CONTENT_LENGTH: u32 = 60;
pub const OP_REQ_MAX_LENGTH: u32 = 61;
pub const OP_REQ_HAS_FORM: u32 = 62;
/// `init_multipart_parser(serv)`, then its buffer becomes current.
pub const OP_REQ_MULTIPART_INIT: u32 = 63;
pub const OP_REQ_DISCARD_FORM: u32 = 64;
pub const OP_REQ_MULTIPART_HEADER: u32 = 65;
pub const OP_REQ_MULTIPART_PARSE: u32 = 66;
pub const OP_REQ_TOO_LARGE: u32 = 67;
pub const OP_REQ_UNAVAILABLE: u32 = 68;
pub const OP_REQ_TRIED: u32 = 69;
/// `destroy_multipart_parser()`, then the request's buffer becomes current.
pub const OP_REQ_MULTIPART_DESTROY: u32 = 70;
pub const OP_REQ_NOBODY_CHUNKED: u32 = 71;
pub const OP_REQ_ADVANCE_HEADER: u32 = 72;
pub const OP_REQ_MARK_DISPATCHED: u32 = 73;
pub const OP_REQ_KNOWN_LENGTH: u32 = 74;
pub const OP_REQ_CHUNKED: u32 = 75;
pub const OP_REQ_CLEAN: u32 = 76;
pub const OP_REQ_EXPECT: u32 = 77;

// Logs, in upstream's wording; arg is the one number a log needs beyond native state.
pub const LOG_UNKNOWN_PROTOCOL: u32 = 90;
pub const LOG_UNKNOWN_METHOD: u32 = 91;
pub const LOG_NO_HTTP2: u32 = 92;
pub const LOG_HEADER_TOO_LARGE: u32 = 93;
pub const LOG_CHUNKED_ERROR: u32 = 94;
pub const LOG_CHUNKED_TOO_LARGE: u32 = 95;
pub const LOG_TOO_LARGE: u32 = 96;
pub const LOG_DISCARD: u32 = 97;
pub const TRACE_HEADER: u32 = 98;
pub const TRACE_CHUNKED: u32 = 99;
pub const TRACE_POST_WAIT: u32 = 100;
pub const TRACE_CLOSE: u32 = 101;

/// Canned responses for `OP_SEND`.
pub const SEND_BAD_REQUEST: u64 = 0;
pub const SEND_TOO_LARGE: u64 = 1;
pub const SEND_UNAVAILABLE: u64 = 2;
pub const SEND_CONTINUE: u64 = 3;

/// `swReturnCode` values `catch_read_error` returns.
const SW_CLOSE: u64 = 3;
const SW_ERROR: u64 = 4;
const SW_OK: i32 = 0;
const SW_ERR: i32 = -1;
/// `SW_HTTP_PRI`, `SW_HTTP_HEADER_MAX_SIZE`, `sizeof(SW_HTTP2_PRI_STRING) - 1`,
/// `sizeof(SW_HTTP_CHUNK_EOF) - 1`, `SW_BUFFER_SIZE_BIG`; native asserts each.
const HTTP_PRI: u64 = 27;
const HEADER_MAX_SIZE: u64 = 65536;
const HTTP2_PREFACE: u64 = 24;
const CHUNK_EOF: u64 = 5;
const BUFFER_SIZE_BIG: u64 = 65536;

struct Native {
    context: *mut c_void,
    call: PortsCall,
}

impl Native {
    fn op(&self, op: u32, arg: u64) -> u64 {
        // SAFETY: a native fact or effect on the live connection in `context`.
        unsafe { (self.call)(self.context, op, arg) }
    }
    fn get(&self, op: u32) -> u64 {
        self.op(op, 0)
    }
    fn is(&self, op: u32) -> bool {
        self.get(op) != 0
    }
    fn signed(&self, op: u32, arg: u64) -> i64 {
        self.op(op, arg).cast_signed()
    }
}

/// `ListenPort::readable_callback_*`: `SW_OK`, or `SW_ERR` when an EOF port has no buffer.
///
/// # Safety
/// `call` acts on the connection in `context`, live for the call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_ports_on_read(
    kind: u32,
    context: *mut c_void,
    call: PortsCall,
) -> i32 {
    let native = Native { context, call };
    match kind {
        ON_READ_RAW => raw(&native),
        ON_READ_LENGTH => framed(&native, OP_RECV_LENGTH, true),
        ON_READ_EOF => eof(&native),
        ON_READ_REDIS => framed(&native, OP_RECV_REDIS, false),
        ON_READ_HTTP => http(&native),
        _ => SW_ERR,
    }
}

/// A failed `recv`: warn and wait, or record errno and close.
enum Failure {
    Wait,
    Close,
}

fn read_error(n: &Native) -> Failure {
    match n.get(OP_CATCH) {
        SW_ERROR => {
            n.get(OP_WARN_RECV);
            Failure::Wait
        }
        SW_CLOSE => {
            n.get(OP_CLOSE_ERRNO);
            Failure::Close
        }
        _ => Failure::Wait,
    }
}

fn raw(n: &Native) -> i32 {
    n.get(OP_RECV_BUFFER);
    let received = n.signed(OP_RECV, 1);
    if received < 0 {
        if let Failure::Close = read_error(n) {
            n.get(OP_CLOSE);
        }
        return SW_OK;
    }
    if received == 0 {
        n.get(OP_CLOSE);
        return SW_OK;
    }
    let length = received.cast_unsigned();
    n.op(OP_BUF_SET_OFFSET, length);
    n.op(OP_BUF_SET_LENGTH, length);
    i32::try_from(n.signed(OP_DISPATCH_TASK, length)).unwrap_or(SW_ERR)
}

/// Length and Redis framing; length (and EOF) ports free a large drained buffer.
fn framed(n: &Native, receive: u32, release: bool) -> i32 {
    n.get(OP_RECV_BUFFER);
    if n.signed(receive, 0) < 0 {
        if receive == OP_RECV_LENGTH {
            n.get(TRACE_CLOSE);
        }
        n.get(OP_CLOSE_ERRNO);
        n.get(OP_CLOSE);
    }
    if release {
        n.op(OP_RELEASE, 1);
    }
    SW_OK
}

fn eof(n: &Native) -> i32 {
    if !n.is(OP_RECV_BUFFER) {
        n.get(OP_CLOSE);
        return SW_ERR;
    }
    if n.signed(OP_RECV_EOF, 0) < 0 {
        n.get(OP_CLOSE_ERRNO);
        n.get(OP_CLOSE);
    }
    n.op(OP_RELEASE, 1);
    SW_OK
}

/// Where the HTTP reader goes next; upstream's labels.
enum Step {
    Receive,
    Parse,
    Reply(u64),
    Close,
    Length,
    Done,
}

fn http(n: &Native) -> i32 {
    if n.is(OP_WEBSOCKET) {
        if !n.is(OP_UPGRADED) {
            n.get(OP_REQ_DESTROY);
            n.get(OP_WEBSOCKET_ACTIVATE);
        }
        return framed(n, OP_RECV_LENGTH, true);
    }
    if n.is(OP_HTTP2_STREAM) {
        return framed(n, OP_RECV_LENGTH, true);
    }
    n.get(OP_REQ_INIT);
    let mut step = Step::Receive;
    loop {
        step = match step {
            Step::Receive => receive(n),
            Step::Parse => parse(n),
            Step::Reply(packet) => {
                n.op(OP_SEND, packet);
                Step::Close
            }
            Step::Close => {
                n.get(OP_REQ_DESTROY);
                n.get(OP_CLOSE);
                return SW_OK;
            }
            Step::Length => return framed(n, OP_RECV_LENGTH, true),
            Step::Done => return SW_OK,
        }
    }
}

fn receive(n: &Native) -> Step {
    let received = n.signed(OP_RECV, 0);
    if received < 0 {
        return match read_error(n) {
            Failure::Wait => Step::Done,
            Failure::Close => Step::Close,
        };
    }
    if received == 0 {
        return Step::Close;
    }
    n.op(OP_BUF_ADD_LENGTH, received.cast_unsigned());
    Step::Parse
}

fn bad(n: &Native, log: u32) -> Step {
    n.get(log);
    Step::Reply(SEND_BAD_REQUEST)
}

fn parse(n: &Native) -> Step {
    if let Some(step) = head(n) {
        return step;
    }
    if !n.is(OP_REQ_TRIED)
        && let Some(step) = bodyless(n)
    {
        return step;
    }
    body(n)
}

/// The request line, an HTTP/2 preface, the header block and form setup.
fn head(n: &Native) -> Option<Step> {
    if n.get(OP_REQ_METHOD) == 0 && n.signed(OP_REQ_PROTOCOL, 0) < 0 {
        if !n.is(OP_REQ_EXCEPTED) && n.get(OP_BUF_LENGTH) < HEADER_MAX_SIZE {
            return Some(Step::Done);
        }
        return Some(bad(n, LOG_UNKNOWN_PROTOCOL));
    }
    let method = n.get(OP_REQ_METHOD);
    if method > HTTP_PRI {
        return Some(bad(n, LOG_UNKNOWN_METHOD));
    }
    if method == HTTP_PRI {
        return Some(preface(n));
    }
    if n.get(OP_REQ_HEADER_LENGTH) == 0 && n.signed(OP_REQ_FIND_HEADER, 0) < 0 {
        if n.get(OP_BUF_SIZE) == n.get(OP_BUF_LENGTH) {
            return Some(bad(n, LOG_HEADER_TOO_LARGE));
        }
        return Some(Step::Receive);
    }
    if !n.is(OP_REQ_HEADER_PARSED) {
        n.get(OP_REQ_PARSE_HEADER);
        n.get(TRACE_HEADER);
        if n.is(OP_REQ_HAS_FORM) {
            if n.is(OP_UPLOADS)
                && n.get(OP_REQ_HEADER_LENGTH)
                    .wrapping_add(n.get(OP_REQ_CONTENT_LENGTH))
                    > n.get(OP_REQ_MAX_LENGTH)
            {
                n.get(OP_REQ_MULTIPART_INIT);
            } else {
                n.get(OP_REQ_DISCARD_FORM);
            }
        }
    }
    if n.is(OP_REQ_HAS_FORM) {
        return form(n);
    }
    None
}

fn preface(n: &Native) -> Step {
    if !n.is(OP_HTTP2_ENABLED) {
        return bad(n, LOG_NO_HTTP2);
    }
    n.get(OP_HTTP2_START);
    if n.get(OP_BUF_LENGTH) == HTTP2_PREFACE {
        n.get(OP_REQ_DESTROY);
        n.get(OP_BUF_CLEAR);
        return Step::Done;
    }
    n.op(OP_BUF_REDUCE, n.get(OP_BUF_OFFSET));
    n.get(OP_REQ_DESTROY);
    n.get(OP_SKIP_RECV);
    Step::Length
}

/// A multipart upload streamed to disk.
fn form(n: &Native) -> Option<Step> {
    if !n.is(OP_REQ_MULTIPART_HEADER) && !n.is(OP_BUF_HEADER_END) {
        return Some(Step::Done);
    }
    if !n.is(OP_REQ_MULTIPART_PARSE) {
        return Some(Step::Reply(SEND_BAD_REQUEST));
    }
    if n.is(OP_REQ_TOO_LARGE) {
        return Some(Step::Reply(SEND_TOO_LARGE));
    }
    if n.is(OP_REQ_UNAVAILABLE) {
        return Some(Step::Reply(SEND_UNAVAILABLE));
    }
    if !n.is(OP_REQ_TRIED) {
        return Some(Step::Done);
    }
    n.get(OP_REQ_MULTIPART_DESTROY);
    None
}

/// The first look at a request: one without a body is served here, pipelined
/// requests behind it parsed next.
fn bodyless(n: &Native) -> Option<Step> {
    if n.is(OP_REQ_NOBODY_CHUNKED) {
        if n.get(OP_BUF_LENGTH) < n.get(OP_REQ_HEADER_LENGTH).wrapping_add(CHUNK_EOF) {
            return Some(Step::Receive);
        }
        n.op(OP_REQ_ADVANCE_HEADER, CHUNK_EOF);
    }
    n.get(OP_REQ_MARK_DISPATCHED);
    let bodyless =
        n.get(OP_REQ_CONTENT_LENGTH) == 0 && (n.is(OP_REQ_KNOWN_LENGTH) || !n.is(OP_REQ_CHUNKED));
    if !bodyless {
        return None;
    }
    let header_length = n.get(OP_REQ_HEADER_LENGTH);
    n.op(OP_BUF_SET_OFFSET, header_length);
    if !n.is(OP_STATIC) && n.signed(OP_DISPATCH_REQUEST, n.get(OP_REQ_HEADER_LENGTH)) < 0 {
        return Some(Step::Close);
    }
    if !n.is(OP_ACTIVE) {
        return Some(Step::Done);
    }
    let header_length = n.get(OP_REQ_HEADER_LENGTH);
    if n.get(OP_BUF_LENGTH) > header_length {
        n.op(OP_BUF_REDUCE, header_length);
        n.get(OP_REQ_CLEAN);
        return Some(Step::Parse);
    }
    n.get(OP_REQ_DESTROY);
    n.get(OP_BUF_CLEAR);
    Some(Step::Done)
}

/// A request with a body: wait for all of it, then dispatch.
fn body(n: &Native) -> Step {
    let max = n.get(OP_MAX_LENGTH);
    let request_length;
    if n.is(OP_REQ_CHUNKED) {
        if n.signed(OP_REQ_FIND_CHUNKED, 0) < 0 {
            if n.is(OP_REQ_EXCEPTED) {
                return bad(n, LOG_CHUNKED_ERROR);
            }
            let wanted = n.get(OP_BUF_SIZE).wrapping_add(BUFFER_SIZE_BIG);
            if wanted > max {
                n.get(LOG_CHUNKED_TOO_LARGE);
                return Step::Reply(SEND_TOO_LARGE);
            }
            if n.get(OP_BUF_LENGTH) == n.get(OP_BUF_SIZE) {
                n.op(OP_BUF_EXTEND, wanted);
            }
            return Step::Receive;
        }
        request_length = n
            .get(OP_REQ_HEADER_LENGTH)
            .wrapping_add(n.get(OP_REQ_CONTENT_LENGTH));
        n.get(TRACE_CHUNKED);
    } else {
        request_length = n
            .get(OP_REQ_HEADER_LENGTH)
            .wrapping_add(n.get(OP_REQ_CONTENT_LENGTH));
        if request_length > max {
            n.get(LOG_TOO_LARGE);
            return Step::Reply(SEND_TOO_LARGE);
        }
        if request_length > n.get(OP_BUF_SIZE) {
            n.op(OP_BUF_EXTEND, request_length);
        }
        if n.get(OP_BUF_LENGTH) < request_length {
            if n.is(OP_REQ_EXPECT) {
                n.op(OP_SEND, SEND_CONTINUE);
            } else {
                n.get(TRACE_POST_WAIT);
            }
            return Step::Receive;
        }
    }
    let length = n.get(OP_BUF_LENGTH);
    if length > request_length {
        n.op(LOG_DISCARD, length - request_length);
        n.op(OP_BUF_SET_LENGTH, request_length);
    }
    n.op(OP_BUF_SET_OFFSET, request_length);
    if n.signed(OP_DISPATCH_REQUEST, n.get(OP_BUF_LENGTH)) < 0 {
        return Step::Close;
    }
    if n.is(OP_ACTIVE) {
        n.get(OP_REQ_DESTROY);
        if !n.is(OP_RELEASE) {
            n.get(OP_BUF_CLEAR);
        }
    }
    Step::Done
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::VecDeque;

    /// A scripted connection: chunks to receive (empty: peer closed; none left:
    /// would block), a receive buffer and a tiny HTTP request parser.
    #[derive(Default)]
    struct Fake {
        incoming: VecDeque<Vec<u8>>,
        bytes: Vec<u8>,
        length: u64,
        size: u64,
        offset: u64,
        method: u64,
        header_length: u64,
        content_length: u64,
        parsed: bool,
        tried: bool,
        request: bool,
        max: u64,
        http2: bool,
        dispatched: Vec<Vec<u8>>,
        effects: Vec<u32>,
        sent: Vec<u64>,
    }

    fn fake(chunks: &[&[u8]]) -> Fake {
        Fake {
            incoming: chunks.iter().map(|c| c.to_vec()).collect(),
            size: 64,
            max: 1024,
            ..Fake::default()
        }
    }

    fn at(n: u64) -> usize {
        usize::try_from(n).unwrap()
    }

    impl Fake {
        fn head(&self) -> &[u8] {
            &self.bytes[..at(self.length)]
        }
        fn find(&self, needle: &[u8]) -> Option<usize> {
            self.head().windows(needle.len()).position(|w| w == needle)
        }
        fn receive(&mut self, whole: bool) -> u64 {
            let Some(chunk) = self.incoming.pop_front() else {
                return u64::MAX;
            };
            let start = if whole { 0 } else { at(self.length) };
            let n = chunk.len().min(at(self.size) - start);
            self.bytes.resize(start + n, 0);
            self.bytes[start..].copy_from_slice(&chunk[..n]);
            n as u64
        }
        fn protocol(&mut self) -> u64 {
            let line = self.head();
            let Some(space) = line.iter().position(|&b| b == b' ') else {
                return u64::MAX;
            };
            self.method = match &line[..space] {
                b"GET" => 2,
                b"POST" => 4,
                b"PRI" => HTTP_PRI,
                _ => 99,
            };
            0
        }
        fn parse_header(&mut self) {
            self.parsed = true;
            let text = String::from_utf8_lossy(self.head()).to_string();
            if let Some(value) = text.split("Content-Length: ").nth(1) {
                self.content_length = value.split("\r\n").next().unwrap().parse().unwrap();
            }
        }
        fn clean(&mut self) {
            (self.method, self.header_length, self.content_length) = (0, 0, 0);
            (self.parsed, self.tried) = (false, false);
        }
        fn reduce(&mut self, n: u64) {
            self.bytes.drain(..at(n));
            self.length -= n;
            self.offset = 0;
        }
        fn call(&mut self, op: u32, arg: u64) -> u64 {
            let flag = u64::from;
            match op {
                OP_RECV => self.receive(arg == 1),
                OP_CATCH => 2,
                OP_RECV_BUFFER => 1,
                OP_DISPATCH_TASK | OP_DISPATCH_REQUEST => {
                    self.dispatched.push(self.bytes[..at(arg)].to_vec());
                    0
                }
                OP_ACTIVE => 1,
                OP_HTTP2_ENABLED => flag(self.http2),
                OP_MAX_LENGTH => self.max,
                OP_BUF_LENGTH => self.length,
                OP_BUF_SIZE => self.size,
                OP_BUF_OFFSET => self.offset,
                OP_BUF_ADD_LENGTH => {
                    self.length += arg;
                    0
                }
                OP_BUF_SET_LENGTH => {
                    self.length = arg;
                    0
                }
                OP_BUF_SET_OFFSET => {
                    self.offset = arg;
                    0
                }
                OP_BUF_REDUCE => {
                    self.reduce(arg);
                    0
                }
                OP_BUF_CLEAR => {
                    (self.length, self.offset) = (0, 0);
                    0
                }
                OP_BUF_EXTEND => {
                    self.size = arg;
                    0
                }
                OP_REQ_INIT => {
                    self.request = true;
                    0
                }
                OP_REQ_DESTROY => {
                    self.request = false;
                    self.clean();
                    0
                }
                OP_REQ_METHOD => self.method,
                OP_REQ_PROTOCOL => self.protocol(),
                OP_REQ_FIND_HEADER => match self.find(b"\r\n\r\n") {
                    Some(end) => {
                        self.header_length = end as u64 + 4;
                        0
                    }
                    None => u64::MAX,
                },
                OP_REQ_HEADER_LENGTH => self.header_length,
                OP_REQ_HEADER_PARSED => flag(self.parsed),
                OP_REQ_PARSE_HEADER => {
                    self.parse_header();
                    0
                }
                OP_REQ_CONTENT_LENGTH => self.content_length,
                OP_REQ_TRIED => flag(self.tried),
                OP_REQ_MARK_DISPATCHED => {
                    self.tried = true;
                    0
                }
                OP_REQ_KNOWN_LENGTH => 1,
                OP_REQ_CLEAN => {
                    self.clean();
                    0
                }
                OP_SEND => {
                    self.sent.push(arg);
                    0
                }
                _ => {
                    self.effects.push(op);
                    0
                }
            }
        }
    }

    unsafe extern "C" fn call(context: *mut c_void, op: u32, arg: u64) -> u64 {
        // SAFETY: tests pass their live `Fake`.
        unsafe { &mut *context.cast::<Fake>() }.call(op, arg)
    }

    fn run(kind: u32, fake: &mut Fake) -> i32 {
        // SAFETY: `fake` is live for the call.
        unsafe { swr_v1_ports_on_read(kind, (&raw mut *fake).cast(), call) }
    }

    const GET: &[u8] = b"GET / HTTP/1.1\r\n\r\n";

    #[test]
    fn get_is_dispatched_and_the_request_released() {
        let mut f = fake(&[GET]);
        assert_eq!(run(ON_READ_HTTP, &mut f), SW_OK, "status");
        assert_eq!(f.dispatched, [GET.to_vec()], "one dispatch of the header");
        assert!(
            !f.request && f.length == 0,
            "request destroyed, buffer cleared"
        );
        assert!(
            f.effects.contains(&OP_STATIC),
            "static handler consulted first"
        );
    }

    #[test]
    fn pipelined_requests_are_parsed_in_turn() {
        let mut f = fake(&[&[GET, GET].concat()]);
        run(ON_READ_HTTP, &mut f);
        assert_eq!(f.dispatched, [GET.to_vec(), GET.to_vec()], "two dispatches");
    }

    #[test]
    fn a_body_is_awaited_then_dispatched_whole() {
        let head = b"POST / HTTP/1.1\r\nContent-Length: 4\r\n\r\n";
        let mut f = fake(&[head, b"ab"]);
        run(ON_READ_HTTP, &mut f);
        assert!(
            f.dispatched.is_empty() && f.effects.contains(&TRACE_POST_WAIT),
            "waits for the body"
        );
        f.incoming.push_back(b"cd".to_vec());
        run(ON_READ_HTTP, &mut f);
        assert_eq!(
            f.dispatched,
            [[&head[..], b"abcd"].concat()],
            "body dispatched with its header"
        );
        assert!(
            f.effects.contains(&OP_RELEASE),
            "large buffers released after dispatch"
        );
    }

    #[test]
    fn oversize_unknown_and_closed_requests_close() {
        let mut f = fake(&[b"POST / HTTP/1.1\r\nContent-Length: 2000\r\n\r\n"]);
        run(ON_READ_HTTP, &mut f);
        assert_eq!(f.sent, [SEND_TOO_LARGE], "413");
        assert!(
            f.effects.ends_with(&[LOG_TOO_LARGE, OP_CLOSE]),
            "logged, then closed"
        );

        let mut f = fake(&[b"BREW / HTTP/1.1\r\n\r\n"]);
        run(ON_READ_HTTP, &mut f);
        assert_eq!(f.sent, [SEND_BAD_REQUEST], "400 for an unknown method");
        assert!(
            f.effects.ends_with(&[LOG_UNKNOWN_METHOD, OP_CLOSE]),
            "logged, then closed"
        );

        let mut f = fake(&[b""]);
        run(ON_READ_HTTP, &mut f);
        assert!(
            f.sent.is_empty() && f.effects.ends_with(&[OP_CLOSE]),
            "peer close"
        );
    }

    #[test]
    fn http2_preface_switches_to_frames() {
        let preface = b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n";
        let mut f = fake(&[preface]);
        run(ON_READ_HTTP, &mut f);
        assert_eq!(f.sent, [SEND_BAD_REQUEST], "refused without http2");
        let mut f = fake(&[preface]);
        f.http2 = true;
        run(ON_READ_HTTP, &mut f);
        assert!(
            f.effects.contains(&OP_HTTP2_START) && f.length == 0,
            "preface consumed"
        );
        let mut f = fake(&[&[&preface[..], b"frame"].concat()]);
        f.http2 = true;
        run(ON_READ_HTTP, &mut f);
        assert!(
            f.effects
                .ends_with(&[OP_SKIP_RECV, OP_RECV_LENGTH, OP_RELEASE]),
            "frames follow"
        );
    }

    #[test]
    fn raw_and_framed_ports() {
        let mut f = fake(&[b"ping"]);
        assert_eq!(run(ON_READ_RAW, &mut f), 0, "dispatch_task's status");
        assert_eq!(
            (f.dispatched.len(), f.length, f.offset),
            (1, 4, 4),
            "whole read dispatched"
        );
        let mut f = fake(&[]);
        run(ON_READ_REDIS, &mut f);
        assert_eq!(f.effects, [OP_RECV_REDIS], "redis keeps its buffer");
        run(ON_READ_EOF, &mut f);
        assert_eq!(
            f.effects[1..],
            [OP_RECV_EOF, OP_RELEASE],
            "eof releases its buffer"
        );
        assert_eq!(run(99, &mut f), SW_ERR, "unknown kind");
    }
}
