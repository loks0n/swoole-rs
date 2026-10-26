//! Differential fuzz targets: the same bytes go to a `swr_v1_*` export and to
//! the pinned upstream C++ in `swoole-rs-oracle`; return values and every output
//! byte, red zones included, must match.

use swoole_rs_base64::{swr_v1_base64_decode, swr_v1_base64_encode};
use swoole_rs_oracle::{base64 as upstream, websocket as upstream_ws};
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
