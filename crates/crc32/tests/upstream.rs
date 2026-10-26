//! Differential tests against the pinned upstream C++ (`swoole-rs-oracle`).

use proptest::prelude::*;
use swoole_rs_crc32::swr_v1_crc32;
use swoole_rs_oracle::crc32 as upstream;

/// Compare on input read one byte past an allocation start, so neither side
/// sees an aligned buffer, and at every offset into an 8-byte window, which
/// exercises the Rust word-at-a-time path and its tail.
fn compare(bytes: &[u8]) {
    let mut shifted = vec![0xa5; 8];
    shifted.extend_from_slice(bytes);
    for offset in 1..8 {
        let mut buffer = vec![0xa5; offset];
        buffer.extend_from_slice(bytes);
        let input = buffer[offset..].as_ptr();
        // SAFETY: `input` points into `buffer`, which holds `bytes.len()` readable bytes after it.
        let want = unsafe { upstream::crc32(input, bytes.len()) };
        // SAFETY: as above.
        let got = unsafe { swr_v1_crc32(input, bytes.len()) };
        assert_eq!(got, want, "crc32 at offset {offset} of {bytes:?}");
    }
}

#[test]
fn original_core_test_assertion() {
    // SAFETY: this binary links the Rust export the adapter forwards to.
    assert_eq!(unsafe { upstream::original_test_failures() }, 0);
}

#[test]
fn empty_and_every_one_and_two_byte_input() {
    compare(&[]);
    for a in 0..=255u8 {
        compare(&[a]);
        for b in 0..=255u8 {
            compare(&[a, b]);
        }
    }
}

#[test]
fn every_length_up_to_sixty_four() {
    let bytes: Vec<u8> = (0..64u32).map(|i| (i * 37 + 19) as u8).collect();
    for length in 0..=bytes.len() {
        compare(&bytes[..length]);
    }
}

proptest! {
    #[test]
    fn arbitrary_input(bytes in proptest::collection::vec(any::<u8>(), 0..4096)) {
        compare(&bytes);
    }
}
