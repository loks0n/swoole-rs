//! Differential fuzz targets: the same bytes go to a `swr_v1_*` export and to
//! the pinned upstream C++ in `swoole-rs-oracle`; return values and every output
//! byte, red zones included, must match.

use swoole_rs_base64::{swr_v1_base64_decode, swr_v1_base64_encode};
use swoole_rs_framing::{swr_v1_framing_default, swr_v1_framing_unpack, swr_v1_framing_width};
use swoole_rs_http::{
    HttpCookie, swr_v1_http_cookie_next, swr_v1_http_url_capacity, swr_v1_http_url_decode,
    swr_v1_http_url_encode,
};
use swoole_rs_oracle::{
    base64 as upstream, framing as upstream_framing, http as upstream_http,
    websocket as upstream_ws,
};
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
    // A payload within a header of isize::MAX overflows upstream's signed sum
    // (undefined); Rust reports -1 there.
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
        // Upstream adds the body offset to a body length near i64::MAX as a signed sum (undefined).
        _ => assert!(want < 0, "error {status} vs {want} for {bytes:?}"),
    }
}
