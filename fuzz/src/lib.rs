//! Differential fuzz targets: the same bytes go to a `swr_v1_*` export and to
//! the pinned upstream C++ in `swoole-rs-oracle`; return values and every output
//! byte, red zones included, must match.

use swoole_rs_base64::{swr_v1_base64_decode, swr_v1_base64_encode};
use swoole_rs_oracle::base64 as upstream;

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
