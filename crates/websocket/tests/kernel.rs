use std::ptr::{null, null_mut};
use swoole_rs_websocket::*;

fn parse(bytes: &[u8], header: &mut u32) -> i64 {
    unsafe { swr_v1_ws_frame_length(bytes.as_ptr(), bytes.len(), header) }
}

#[test]
fn incremental_headers_preserve_upstream_progress() {
    for (wire, progress) in [
        (vec![0x82, 0x83, 1, 2, 3, 4], vec![99, 99, 6, 6, 6, 6, 6]),
        (
            vec![0x82, 0xfe, 0, 126, 1, 2, 3, 4],
            vec![99, 99, 4, 4, 8, 8, 8, 8, 8],
        ),
        (
            vec![0x82, 0xff, 0, 0, 0, 0, 0, 1, 0, 0, 1, 2, 3, 4],
            vec![99, 99, 10, 10, 10, 10, 10, 10, 10, 10, 14, 14, 14, 14, 14],
        ),
    ] {
        for (length, expected) in progress.into_iter().enumerate() {
            let mut header = 99;
            let total = parse(&wire[..length], &mut header);
            assert_eq!(header, expected, "input length {length}");
            assert_eq!(total == 0, length < wire.len());
        }
    }
}

#[test]
fn header_boundaries_and_flags_roundtrip_without_payload() {
    for length in [0, 1, 125, 126, 127, 65535, 65536, 1 << 32] {
        for opcode in 0..=255 {
            for flags in [0, 1, 4, 32, 255] {
                let mut output = [0xa5; 15];
                let size = unsafe {
                    swr_v1_ws_write_header(length, opcode, flags, output[1..].as_mut_ptr(), 10)
                };
                assert_eq!(output[0], 0xa5);
                assert_eq!(output[size + 1], 0xa5);
                assert_eq!(
                    output[1],
                    (opcode & 15)
                        | if flags & 1 != 0 { 128 } else { 0 }
                        | if flags & 4 != 0 { 64 } else { 0 }
                );
                let mut header = 0;
                let mask_bytes = if flags & 32 != 0 { 4 } else { 0 };
                assert_eq!(
                    parse(&output[1..1 + size + mask_bytes], &mut header),
                    i64::try_from(length + (size + mask_bytes) as u64).unwrap()
                );
                assert_eq!(header as usize, size + mask_bytes);
            }
        }
    }
}

#[test]
fn signed_total_overflow_is_rejected() {
    let mut wire = [0; 14];
    for masked in [false, true] {
        let size = if masked { 14 } else { 10 };
        for (payload, expected) in [
            (isize::MAX as u64 - size as u64, isize::MAX as i64),
            (isize::MAX as u64 - size as u64 + 1, -1),
            (u64::MAX, -1),
        ] {
            unsafe {
                swr_v1_ws_write_header(
                    payload,
                    2,
                    if masked { 32 } else { 0 },
                    wire.as_mut_ptr(),
                    wire.len(),
                )
            };
            let mut header = 0;
            assert_eq!(parse(&wire, &mut header), expected);
            assert_eq!(header as usize, size);
        }
    }
}

#[test]
fn invalid_pointers_lengths_and_short_outputs_do_not_write() {
    let mut header = 99;
    let mut output = [0xa5; 10];
    unsafe {
        assert_eq!(swr_v1_ws_frame_length(null(), 0, &mut header), 0);
        assert_eq!(swr_v1_ws_frame_length(null(), 1, &mut header), -1);
        assert_eq!(
            swr_v1_ws_frame_length(output.as_ptr(), usize::MAX, &mut header),
            -1
        );
        assert_eq!(swr_v1_ws_frame_length(output.as_ptr(), 2, null_mut()), -1);
        assert_eq!(header, 99);
        for (length, required) in [(0, 2), (126, 4), (65536, 10)] {
            for capacity in 0..required {
                assert_eq!(
                    swr_v1_ws_write_header(length, 2, 255, output.as_mut_ptr(), capacity),
                    0
                );
                assert_eq!(output, [0xa5; 10]);
            }
        }
        assert_eq!(swr_v1_ws_write_header(0, 2, 0, null_mut(), 10), 0);
        assert_eq!(
            swr_v1_ws_write_header(0, 2, 0, output.as_mut_ptr(), usize::MAX),
            0
        );
        assert_eq!(swr_v1_ws_mask(null_mut(), 0, null()), 0);
        assert_eq!(swr_v1_ws_mask(null_mut(), 1, output.as_ptr()), -1);
        assert_eq!(swr_v1_ws_mask(output.as_mut_ptr(), 1, null()), -1);
        assert_eq!(
            swr_v1_ws_mask(output.as_mut_ptr(), usize::MAX, output.as_ptr()),
            -1
        );
        assert_eq!(output, [0xa5; 10]);
    }
}

#[test]
fn binary_mask_matches_known_vector_and_is_an_involution() {
    // RFC 6455 section 5.7's masked Hello frame.
    let key = [0x37, 0xfa, 0x21, 0x3d];
    let mut hello = *b"Hello";
    unsafe { swr_v1_ws_mask(hello.as_mut_ptr(), hello.len(), key.as_ptr()) };
    assert_eq!(hello, [0x7f, 0x9f, 0x4d, 0x51, 0x58]);
    for length in [1, 3, 4, 7, 8, 9, 255, 1024] {
        let mut bytes: Vec<_> = (0..length + 2).map(|x: usize| x.to_le_bytes()[0]).collect();
        let original = bytes.clone();
        for _ in 0..2 {
            assert_eq!(
                unsafe { swr_v1_ws_mask(bytes[1..].as_mut_ptr(), length, key.as_ptr()) },
                0
            );
            assert_eq!(bytes[0], original[0]);
            assert_eq!(bytes[length + 1], original[length + 1]);
        }
        assert_eq!(bytes, original);
    }
}

#[test]
fn masking_copies_overlapping_key_before_writing() {
    for offset in 0..8 {
        let mut data: Vec<_> = (0..32).collect();
        let original = data.clone();
        let key = &original[offset..offset + 4];
        unsafe { swr_v1_ws_mask(data.as_mut_ptr(), data.len(), data.as_ptr().add(offset)) };
        for (index, value) in data.iter().enumerate() {
            assert_eq!(*value, original[index] ^ key[index % 4]);
        }
    }
}
