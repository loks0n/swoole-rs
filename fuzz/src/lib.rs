//! Differential fuzz targets: the same bytes go to a `swr_v1_*` export and to
//! the pinned upstream C++ in `swoole-rs-oracle`; return values and every output
//! byte, red zones included, must match.

use std::ffi::{CStr, c_char};
use swoole_rs_base64::{swr_v1_base64_decode, swr_v1_base64_encode};
use swoole_rs_clients::{swr_v1_clients_cookie, swr_v1_clients_domain_decode};
use swoole_rs_framing::{swr_v1_framing_default, swr_v1_framing_unpack, swr_v1_framing_width};
use swoole_rs_http::{
    HttpCookie, swr_v1_http_cookie_next, swr_v1_http_url_capacity, swr_v1_http_url_decode,
    swr_v1_http_url_encode,
};
use swoole_rs_oracle::{
    base64 as upstream, clients, framing as upstream_framing, http as upstream_http,
    http_frame::{self, CANDIDATE, Engine, UPSTREAM},
    http_range, protocols, websocket as upstream_ws,
};
use swoole_rs_protocols as _;
use swoole_rs_websocket::{DecodedFrame, swr_v1_ws_decode, swr_v1_ws_frame_length, swr_v1_ws_mask};

const RED_ZONE: usize = 17;

pub fn base64(bytes: &[u8], encode: bool) {
    // Zero-length encode is undefined upstream.
    if encode && bytes.is_empty() {
        return;
    }
    let capacity = if encode {
        bytes.len().div_ceil(3) * 4 + 1
    } else {
        bytes.len() + 1
    };
    let mut expected = vec![0xa5; capacity + 2 * RED_ZONE];
    let mut actual = expected.clone();
    // SAFETY: both outputs have `capacity` writable bytes after the red zone.
    let (want, got) = unsafe {
        let (e, a) = (
            expected.as_mut_ptr().add(RED_ZONE),
            actual.as_mut_ptr().add(RED_ZONE),
        );
        if encode {
            (
                upstream::encode(bytes.as_ptr(), bytes.len(), e),
                swr_v1_base64_encode(bytes.as_ptr(), bytes.len(), a),
            )
        } else {
            (
                upstream::decode(bytes.as_ptr(), bytes.len(), e),
                swr_v1_base64_decode(bytes.as_ptr(), bytes.len(), a),
            )
        }
    };
    assert_eq!(got, want, "return for encode={encode} input={bytes:?}");
    assert!(
        actual == expected,
        "output for encode={encode} input={bytes:?}"
    );
}

/// Any bytes as the start of a frame: the same total and header length.
pub fn ws_frame_length(bytes: &[u8]) {
    let (mut want_header, mut got_header) = (0, 0);
    // SAFETY: both read `bytes` and write one local u32.
    let (want, got) = unsafe {
        (
            upstream_ws::frame_length(bytes.as_ptr(), bytes.len(), &mut want_header),
            swr_v1_ws_frame_length(bytes.as_ptr(), bytes.len(), &mut got_header),
        )
    };
    // Upstream's result is undefined for some lengths (private advisory);
    // Rust reports -1 there.
    assert!(
        want as i64 == got || got == -1 && want < 0,
        "total {want} vs {got} for {bytes:?}"
    );
    assert_eq!(want_header, got_header, "header length for {bytes:?}");
}

/// Any bytes as one frame: the same verdict, fields and in-place unmasking.
pub fn ws_decode(bytes: &[u8]) {
    // Upstream reads the first two bytes unconditionally; servers only decode
    // frames whose length check has passed.
    if bytes.len() < 2 {
        return;
    }
    let (mut theirs, mut ours) = (bytes.to_vec(), bytes.to_vec());
    let (mut want, mut got) = (upstream_ws::Frame::default(), DecodedFrame::default());
    // SAFETY: each side owns its copy of the frame and its output.
    let (ok, total) = unsafe {
        (
            upstream_ws::decode(theirs.as_mut_ptr(), theirs.len(), &mut want),
            swr_v1_ws_decode(ours.as_mut_ptr(), ours.len(), &mut got),
        )
    };
    assert_eq!(
        ok,
        total > 0 && bytes.len() as i64 >= total,
        "verdict ({total}) for {bytes:?}"
    );
    if ok {
        let got = upstream_ws::Frame {
            payload_length: got.payload_length as u64,
            header_length: got.header_length as u16,
            opcode: got.opcode,
            flags: got.flags,
            length_code: got.length_code,
            mask_key: got.mask_key,
        };
        assert_eq!(want, got, "frame for {bytes:?}");
    }
    assert!(theirs == ours, "payload bytes for {bytes:?}");
}

/// The first four bytes as a key: the same masking, and masking twice restores the data.
pub fn ws_mask(bytes: &[u8]) {
    let Some((key, data)) = bytes.split_first_chunk::<4>() else {
        return;
    };
    let (mut theirs, mut ours) = (data.to_vec(), data.to_vec());
    // SAFETY: each side masks its own copy with the same four-byte key.
    unsafe {
        upstream_ws::mask(theirs.as_mut_ptr(), theirs.len(), key.as_ptr());
        assert_eq!(
            swr_v1_ws_mask(ours.as_mut_ptr(), ours.len(), key.as_ptr()),
            0
        );
    }
    assert_eq!(theirs, ours, "mask for {bytes:?}");
    // SAFETY: as above.
    unsafe { swr_v1_ws_mask(ours.as_mut_ptr(), ours.len(), key.as_ptr()) };
    assert_eq!(ours, data, "unmask for {bytes:?}");
}

/// Any bytes as a URL component: the same decoded bytes, terminator and length.
pub fn http_url_decode(bytes: &[u8]) {
    let mut theirs = [bytes, &[0xa5]].concat();
    let mut ours = theirs.clone();
    let mut written = 0;
    // SAFETY: each side owns `length + 1` bytes; `written` is a local.
    let (want, status) = unsafe {
        (
            upstream_http::url_decode(theirs.as_mut_ptr(), bytes.len()),
            swr_v1_http_url_decode(ours.as_mut_ptr(), bytes.len(), &mut written),
        )
    };
    assert_eq!((status, written), (0, want), "length for {bytes:?}");
    assert!(theirs == ours, "decoded bytes for {bytes:?}");
}

/// Any bytes: the same percent-encoding, terminated.
pub fn http_url_encode(bytes: &[u8]) {
    let mut theirs = vec![0xa5; 3 * bytes.len() + 1];
    let (mut capacity, mut written) = (0, 0);
    // SAFETY: `theirs` has upstream's capacity; ours is sized by the capacity query.
    let want =
        unsafe { upstream_http::url_encode(bytes.as_ptr(), bytes.len(), theirs.as_mut_ptr()) };
    assert_eq!(
        unsafe { swr_v1_http_url_capacity(bytes.as_ptr(), bytes.len(), &mut capacity) },
        0
    );
    let mut ours = vec![0xa5; capacity];
    let status = unsafe {
        swr_v1_http_url_encode(
            bytes.as_ptr(),
            bytes.len(),
            ours.as_mut_ptr(),
            capacity,
            &mut written,
        )
    };
    assert_eq!(
        (status, written, capacity),
        (0, want, want + 1),
        "length for {bytes:?}"
    );
    assert_eq!(ours, theirs[..=want], "encoding for {bytes:?}");
}

/// Any bytes as a Cookie header: the same keys and values, in order.
pub fn http_cookies(bytes: &[u8]) {
    let mut theirs = vec![0; 8 * bytes.len() + 16];
    // SAFETY: `theirs` has the documented capacity.
    let size = unsafe { upstream_http::cookies(bytes.as_ptr(), bytes.len(), theirs.as_mut_ptr()) };
    theirs.truncate(size);
    // Like parse_cookie, tokenize a NUL-terminated copy in place.
    let mut buffer = [bytes, &[0]].concat();
    let (mut cursor, mut ours) = (0, Vec::new());
    loop {
        let mut cookie = HttpCookie::default();
        // SAFETY: the buffer is writable and NUL-terminated; cursor and cookie are locals.
        let status = unsafe {
            swr_v1_http_cookie_next(buffer.as_mut_ptr(), buffer.len(), &mut cursor, &mut cookie)
        };
        assert!(status >= 0, "status {status} for {bytes:?}");
        if status == 0 {
            break;
        }
        for (offset, length) in [
            (cookie.key_offset, cookie.key_length),
            (cookie.value_offset, cookie.value_length),
        ] {
            ours.extend_from_slice(&(length as u32).to_ne_bytes());
            ours.extend_from_slice(&buffer[offset..offset + length]);
        }
    }
    assert_eq!(ours, theirs, "cookies for {bytes:?}");
}

/// Length types a server accepts for `package_length_type`.
const FORMATS: &[u8] = b"cCsSnvIiLlNVqQJP";

/// The first byte picks a length type, the rest is the field: the same value.
pub fn framing_unpack(bytes: &[u8]) {
    let Some((&pick, data)) = bytes.split_first() else {
        return;
    };
    let format = FORMATS[usize::from(pick) % FORMATS.len()];
    if data.len() < swr_v1_framing_width(format) {
        return;
    }
    let mut got = 0;
    // SAFETY: both read the format's width, which `data` covers.
    let want = unsafe { upstream_framing::unpack(format, data.as_ptr()) };
    assert_eq!(
        unsafe { swr_v1_framing_unpack(format, data.as_ptr(), data.len(), &mut got) },
        0
    );
    assert_eq!(want, got, "unpack {} of {data:?}", format as char);
}

/// A length type, field offset and body offset, then any received bytes: the same
/// total length, "need more" header length, or error. Field size is the type's
/// width, as the server configures it.
pub fn framing_length(bytes: &[u8]) {
    let Some((&[pick, offset_low, offset_high, body_low, body_high], data)) =
        bytes.split_first_chunk::<5>()
    else {
        return;
    };
    let format = FORMATS[usize::from(pick) % FORMATS.len()];
    let size = swr_v1_framing_width(format) as u8;
    let (offset, body_offset) = (
        u16::from_le_bytes([offset_low, offset_high]) % 64,
        u16::from_le_bytes([body_low, body_high]),
    );
    let mut header = 0;
    // SAFETY: both read at most `data.len()` bytes; outputs are locals.
    let want = unsafe {
        upstream_framing::length(
            format,
            size,
            offset,
            body_offset,
            data.as_ptr(),
            data.len() as u32,
            &mut header,
        )
    };
    let mut got = 0;
    let status = unsafe {
        swr_v1_framing_default(
            format,
            data.as_ptr(),
            data.len(),
            offset.into(),
            size.into(),
            body_offset.into(),
            &mut got,
        )
    };
    match status {
        0 => assert_eq!((want, header as i64), (0, got), "need more for {bytes:?}"),
        1 => assert_eq!(want as i64, got, "total for {bytes:?}"),
        // Upstream is undefined for some lengths (private advisory); only an error must match.
        _ => assert!(want < 0, "error {status} vs {want} for {bytes:?}"),
    }
}

/// `data` and a NUL, as both engines read it: get_header may look one byte past
/// the header end, and strtoul stops at the NUL.
fn terminated(data: &[u8]) -> Vec<c_char> {
    data.iter()
        .chain(&[0])
        .map(|&byte| byte as c_char)
        .collect()
}

/// Whether upstream's result is undefined for this chunk length (private
/// advisory), so it isn't compared.
fn huge_chunk(data: &[u8]) -> bool {
    let mut at = 0;
    while at < data.len() {
        let length = data[at..]
            .iter()
            .take_while(|byte| byte.is_ascii_hexdigit())
            .count();
        if length == 0 {
            at += 1;
            continue;
        }
        let digits = &data[at..at + length];
        let nonzero = digits.iter().position(|&byte| byte != b'0');
        let sign = at.checked_sub(1).map(|before| data[before]);
        let prefixed = at >= 3 && matches!(data[at - 1], b'x' | b'X') && data[at - 2] == b'0';
        let negated = sign == Some(b'-') || prefixed && data[at - 3] == b'-';
        if nonzero.is_some_and(|first| length - first > 12 || negated) {
            return true;
        }
        at += length;
    }
    false
}

fn frame(
    engine: &Engine,
    operation: u32,
    data: &[u8],
    state: http_frame::State,
) -> (i32, http_frame::State) {
    let (mut buffer, mut state) = (terminated(data), state);
    // SAFETY: the buffer holds data.len() bytes and a NUL; state is a local.
    let status = unsafe { (engine.frame)(operation, buffer.as_mut_ptr(), data.len(), &mut state) };
    (status, state)
}

/// get_protocol, get_header_length or get_chunked_body_length on both engines
/// from the same offset, header length and request state.
pub fn http_frame(bytes: &[u8]) {
    let Some((&[control, offset_low, offset_high, header_low, header_high], data)) =
        bytes.split_first_chunk::<5>()
    else {
        return;
    };
    let operation = u32::from(control % 3);
    let bound = |low, high| u16::from_le_bytes([low, high]) as usize % (data.len() + 1);
    let mut state = http_frame::State {
        offset: bound(offset_low, offset_high),
        header_length: bound(header_low, header_high) as u32,
        ..Default::default()
    };
    if control & 0x80 != 0 {
        state = http_frame::State {
            method: 19,
            version: 3,
            known_length: 1,
            content_length: 123,
            url_offset: 3,
            url_length: 7,
            line_length: 9,
            ..state
        };
    }
    let got = frame(&CANDIDATE, operation, data, state);
    // Not comparable: upstream is undefined here (private advisory).
    if operation == 2 && huge_chunk(&data[state.offset..]) {
        return;
    }
    let want = frame(&UPSTREAM, operation, data, state);
    // Upstream is undefined for these inputs (private advisory); the candidate
    // must wait for more data.
    if operation == 0 && want.0 == 0 && want.1.offset > data.len() {
        assert_eq!(
            (got.0, got.1.offset),
            (-1, state.offset),
            "partial request line {bytes:?}"
        );
        return;
    }
    assert_eq!(got, want, "operation {operation} for {bytes:?}");
}

fn method(engine: &Engine, method: i32) -> Option<&'static CStr> {
    // SAFETY: the result is null or one of the engine's static strings.
    let string = unsafe { (engine.method)(method) };
    (!string.is_null()).then(|| unsafe { CStr::from_ptr(string) })
}

/// has_expect_header, get_header(name) and get_method_string on both engines.
pub fn http_header(bytes: &[u8]) {
    let Some((
        &[
            name_length,
            url_offset,
            url_length,
            header_low,
            header_high,
            code,
        ],
        rest,
    )) = bytes.split_first_chunk::<6>()
    else {
        return;
    };
    assert_eq!(
        method(&CANDIDATE, (code as i8).into()),
        method(&UPSTREAM, (code as i8).into()),
        "method {code}"
    );
    let (name, data) = rest.split_at(usize::from(name_length % 16).min(rest.len()));
    let name: Vec<c_char> = name
        .iter()
        .take_while(|&&byte| byte != 0)
        .chain(&[0])
        .map(|&byte| byte as c_char)
        .collect();
    let header_length = u16::from_le_bytes([header_low, header_high]) as usize % (data.len() + 1);
    let [want, got] = [&UPSTREAM, &CANDIDATE].map(|engine| {
        let (mut buffer, mut output) = (terminated(data), vec![0 as c_char; data.len()]);
        // SAFETY: the buffer holds data.len() bytes and a NUL; output has data.len() bytes.
        unsafe {
            let expect = (engine.expect)(buffer.as_mut_ptr(), data.len());
            let size = (engine.header)(
                buffer.as_mut_ptr(),
                data.len(),
                url_offset.into(),
                url_length.into(),
                header_length as u32,
                name.as_ptr(),
                output.as_mut_ptr(),
            );
            output.truncate(size);
            (expect, output)
        }
    });
    assert_eq!(got, want, "expect/header for {bytes:?}");
}

/// Upstream `mqtt::get_package_length` and the candidate over the same received
/// bytes. With nothing received upstream is undefined (private advisory), so
/// only the candidate runs there.
pub fn mqtt_length(bytes: &[u8]) {
    let data: Vec<c_char> = bytes.iter().map(|&byte| byte as c_char).collect();
    let size = data.len().min(u32::MAX as usize) as u32;
    // SAFETY: both read at most `size` bytes of `data`.
    let got = unsafe { (protocols::CANDIDATE.mqtt_length)(data.as_ptr(), size) };
    if size == 0 {
        return;
    }
    let want = unsafe { (protocols::UPSTREAM.mqtt_length)(data.as_ptr(), size) };
    assert_eq!(got, want, "mqtt length for {bytes:?}");
}

/// Walks upstream `redis::parse` over `data` (and the NUL after it) without
/// reading it: false where upstream is undefined (private advisory) or where it
/// meets input `recv_packet` never passes it. Those inputs are not compared.
fn resp_parse_in_bounds(data: &[u8]) -> bool {
    let at = |index: usize| data.get(index).copied().unwrap_or(0);
    // get_number: strtol after the type byte, then CRLF; Some((ret, next)).
    let number = |p: usize| {
        let start = p + 1;
        let mut q = start;
        while matches!(at(q), b' ' | b'\t' | b'\n' | 0x0b | 0x0c | b'\r') {
            q += 1;
        }
        let negative = at(q) == b'-';
        if matches!(at(q), b'+' | b'-') {
            q += 1;
        }
        let digits = q;
        let mut value: i128 = 0;
        while at(q).is_ascii_digit() {
            value = (value * 10 + i128::from(at(q) - b'0')).min(1 << 70);
            q += 1;
        }
        let end = if q == digits { start } else { q };
        let value = if negative { -value } else { value };
        // strtol clamps to long; the int conversion keeps the low 32 bits.
        let value = value.clamp(i64::MIN.into(), i64::MAX.into()) as i64 as i32;
        (at(end) == b'\r' && at(end + 1) == b'\n').then_some((value, end + 2))
    };
    // One pass is one run of upstream's switch: `case` is where it enters, and a
    // case that doesn't break falls through to the next.
    let (mut state, mut p, mut length) = (0, 0usize, 0i32);
    loop {
        let mut case = state;
        if case == 0 {
            if at(p) == b'*' {
                let Some((_, next)) = number(p) else {
                    return false;
                };
                (p, state) = (next, 1);
            } else {
                case = 1;
            }
        }
        if case == 1 {
            if at(p) == b'$' {
                let Some((ret, next)) = number(p) else {
                    return false;
                };
                p = next;
                if ret != -1 {
                    (length, state) = (ret, 2);
                }
            } else if at(p) == b':' {
                let Some((_, next)) = number(p) else {
                    return false;
                };
                p = next;
            } else {
                return false;
            }
        }
        if case == 2 {
            if length < 0 || p + length as usize > data.len() {
                return false;
            }
            (p, state) = (p + length as usize + 2, 1);
        }
        if p >= data.len() {
            return true;
        }
    }
}

/// The strings and, on glibc, whether errno is ERANGE. macOS strtol also sets
/// EINVAL when it converts nothing, which can overwrite an earlier ERANGE; glibc
/// leaves errno alone there, and callers only test ERANGE.
fn resp_parse_on(engine: &protocols::Engine, data: &[u8]) -> (Vec<u8>, bool) {
    let buffer = terminated(data);
    let (mut size, mut error) = (0, 0);
    // SAFETY: the buffer holds data.len() bytes and a NUL; the result is malloc'd.
    unsafe {
        let output = (engine.resp_parse)(buffer.as_ptr(), data.len(), &mut size, &mut error);
        let items = std::slice::from_raw_parts(output as *const u8, size).to_vec();
        protocols::free(output);
        (items, cfg!(target_os = "linux") && error == 34)
    }
}

/// Upstream `redis::parse` and the candidate over the same bytes: every string,
/// in order, and ERANGE. The candidate runs on every input.
pub fn resp_parse(bytes: &[u8]) {
    let got = resp_parse_on(&protocols::CANDIDATE, bytes);
    if !resp_parse_in_bounds(bytes) {
        return;
    }
    assert_eq!(
        got,
        resp_parse_on(&protocols::UPSTREAM, bytes),
        "resp parse for {bytes:?}"
    );
}

/// Longest URL compared: libstdc++'s std::regex recurses once per character.
const URL_LIMIT: usize = 256;

fn client_url(engine: clients::Url, data: &[u8]) -> (i32, i32, i32, Vec<u8>) {
    let (mut kind, mut port, mut host, mut host_length) = (0, 0, vec![0; data.len()], 0);
    // SAFETY: `data` is readable for its length; `host` has room for any substring of it.
    let status = unsafe {
        engine(
            data.as_ptr().cast(),
            data.len(),
            &mut kind,
            &mut port,
            host.as_mut_ptr().cast(),
            &mut host_length,
        )
    };
    host.truncate(host_length);
    (status, kind, port, host)
}

/// Any bytes as a client URL: `Address::assign(url)` from the pinned address.cc
/// and with the clients patch assign the same type, host and port, or both reject.
pub fn clients_url(bytes: &[u8]) {
    let got = client_url(clients::CANDIDATE_URL, bytes);
    if bytes.len() > URL_LIMIT {
        return;
    }
    assert_eq!(
        got,
        client_url(clients::UPSTREAM_URL, bytes),
        "url {bytes:?}"
    );
}

/// Any bytes as one Set-Cookie header: the same key, value offset and value.
pub fn clients_cookie(bytes: &[u8]) {
    let mut want = (0, 0, 0);
    // SAFETY: both read `bytes`; outputs are locals.
    let got = unsafe {
        clients::cookie(
            bytes.as_ptr().cast(),
            bytes.len(),
            &mut want.0,
            &mut want.1,
            &mut want.2,
        );
        swr_v1_clients_cookie(bytes.as_ptr(), bytes.len())
    };
    assert_eq!(
        (got.key_length, got.value_offset, got.value_length),
        want,
        "cookie {bytes:?}"
    );
}

/// Any bytes as a received DNS name buffer: where Rust decodes in bounds, upstream
/// decodes to the same bytes. Elsewhere upstream is undefined (private advisory)
/// and Rust reports 0, so upstream isn't run.
pub fn clients_domain_decode(bytes: &[u8]) {
    let (mut theirs, mut ours) = (bytes.to_vec(), bytes.to_vec());
    // SAFETY: Rust stays within `ours`.
    let decoded = unsafe {
        swr_v1_clients_domain_decode(ours.as_mut_ptr(), ours.len(), u8::from(c_char::MIN != 0))
    };
    if decoded == 0 {
        return;
    }
    // SAFETY: Rust decoded the same bytes in bounds, so upstream's identical walk does too.
    unsafe { clients::domain_decode(theirs.as_mut_ptr().cast()) };
    assert_eq!(theirs, ours, "domain {bytes:?}");
}

/// Any bytes up to the first blank line as a request head: `parse_header_info` on both
/// engines gives the same lengths, flags, errno and multipart boundary.
pub fn http_header_info(bytes: &[u8]) {
    let Some(end) = bytes.windows(4).position(|w| w == b"\r\n\r\n") else {
        return;
    };
    let line = bytes.windows(2).position(|w| w == b"\r\n").unwrap_or(0);
    let header_length = (end + 4) as u32;
    let info = |engine: &Engine| {
        let (mut buffer, mut info) = (terminated(bytes), http_frame::HeaderInfo::default());
        // SAFETY: the buffer holds bytes.len() bytes and a NUL; the head ends in a blank
        // line before header_length; info is a local.
        unsafe {
            (engine.header_info)(
                buffer.as_mut_ptr(),
                bytes.len(),
                line as u32,
                header_length,
                &mut info,
            )
        };
        info
    };
    let got = info(&CANDIDATE);
    // Upstream is undefined here (private advisory); the candidate rejects the request.
    if multipart_nul(bytes, line + 2, end) {
        assert_eq!(got.flags & 32, 32, "excepted for {bytes:?}");
        return;
    }
    assert_eq!(got, info(&UPSTREAM), "header info for {bytes:?}");
}

/// Whether a multipart/form-data Content-Type line in the head, as parse_header_info
/// finds it, meets a NUL before its CR.
fn multipart_nul(bytes: &[u8], start: usize, end: usize) -> bool {
    let starts = |at: usize, prefix: &[u8]| {
        bytes.get(at..end).is_some_and(|rest| {
            rest.len() >= prefix.len() && rest[..prefix.len()].eq_ignore_ascii_case(prefix)
        })
    };
    (start.max(2)..end).any(|at| {
        if &bytes[at - 2..at] != b"\r\n" || !starts(at, b"Content-Type:") {
            return false;
        }
        let mut value = at + 13;
        while bytes.get(value) == Some(&b' ') {
            value += 1;
        }
        starts(value, b"multipart/form-data")
            && bytes[value..]
                .iter()
                .find(|&&byte| matches!(byte, b'\r' | 0))
                != Some(&b'\r')
    })
}

const RANGE_BOUNDARY: &[u8] = b"SwooleRangeBoundary0123\0";

fn range_on(
    engine: http_range::ParseRange,
    range: &[c_char],
    filesize: u64,
    mime: &[c_char],
    flags: u8,
    capacity: usize,
) -> (http_range::Outcome, Vec<u8>) {
    let (mut outcome, mut tasks) = (
        http_range::Outcome::default(),
        vec![0; capacity * http_range::TASK_SIZE],
    );
    // SAFETY: range, mime and the boundary are NUL-terminated; tasks has room for
    // capacity tasks; outcome is a local.
    unsafe {
        engine(
            range.as_ptr(),
            filesize,
            mime.as_ptr(),
            RANGE_BOUNDARY.as_ptr().cast(),
            i32::from(flags & 1),
            i32::from(flags & 2 != 0),
            &mut outcome,
            tasks.as_mut_ptr(),
            capacity,
        )
    };
    tasks.truncate(outcome.tasks.min(capacity) * http_range::TASK_SIZE);
    (outcome, tasks)
}

/// A flags byte (If-Range sent, file modified), a MIME type length, a file size and a
/// Range header: `StaticHandler::parse_range` on both engines gives the same status,
/// content length, tasks, part headers and closing boundary.
pub fn http_range(bytes: &[u8]) {
    let Some((&[flags, mime_length, size @ ..], range)) = bytes.split_first_chunk::<10>() else {
        return;
    };
    let filesize = u64::from_le_bytes(size);
    let mime: Vec<c_char> = b"application/octet-stream"
        .iter()
        .cycle()
        .take(usize::from(mime_length))
        .chain(&[0])
        .map(|&byte| byte as c_char)
        .collect();
    let range: Vec<c_char> = range
        .iter()
        .take_while(|&&byte| byte != 0)
        .chain(&[0])
        .map(|&byte| byte as c_char)
        .collect();
    let capacity = range.len() + 2;
    let want = range_on(
        http_range::UPSTREAM,
        &range,
        filesize,
        &mime,
        flags,
        capacity,
    );
    let got = range_on(
        http_range::CANDIDATE,
        &range,
        filesize,
        &mime,
        flags,
        capacity,
    );
    assert_eq!(got, want, "range for {bytes:?}");
}
