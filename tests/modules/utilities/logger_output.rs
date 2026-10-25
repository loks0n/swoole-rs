//! Corrected implementation only: initialize exactly the output prefix before reading it.
use std::mem::MaybeUninit;
use swoole_rs_utilities::{swr_v1_utils_log_line, swr_v1_utils_log_micros};

unsafe fn prefix(bytes: &[MaybeUninit<u8>], count: usize) -> Vec<u8> {
    bytes[..count]
        .iter()
        .map(|byte| unsafe { byte.assume_init() })
        .collect()
}
fn main() {
    let mut checks = 0;
    for capacity in 0..=128 {
        for micros in [i64::MIN, -1, 0, 123456, i64::MAX] {
            let expected = format!("<.{micros}>");
            let mut output = [MaybeUninit::<u8>::uninit(); 128];
            let n =
                unsafe { swr_v1_utils_log_micros(output.as_mut_ptr().cast(), capacity, micros) };
            if capacity == 0 {
                assert_eq!(n, expected.len());
            } else {
                assert_eq!(n, expected.len().min(capacity - 1));
                assert_eq!(unsafe { prefix(&output, n) }, expected.as_bytes()[..n]);
                assert_eq!(unsafe { output[n].assume_init() }, 0);
            }
            checks += 1;
        }
        let expected = b"[date *-2147483648.2147483647]\tWARNING\tmessage\n";
        let mut output = [MaybeUninit::<u8>::uninit(); 128];
        let n = unsafe {
            swr_v1_utils_log_line(
                output.as_mut_ptr().cast(),
                capacity,
                c"date".as_ptr().cast(),
                -1,
                b'*',
                i32::MIN,
                i32::MAX,
                4,
                c"message".as_ptr().cast(),
                -1,
            )
        };
        if capacity == 0 {
            assert_eq!(n, expected.len());
        } else {
            assert_eq!(n, expected.len().min(capacity - 1));
            assert_eq!(unsafe { prefix(&output, n) }, expected[..n]);
            assert_eq!(unsafe { output[n].assume_init() }, 0);
        }
        checks += 1;
    }
    // The zero-capacity query also accepts an actual null destination.
    assert_eq!(
        unsafe { swr_v1_utils_log_micros(std::ptr::null_mut(), 0, 0) },
        4
    );
    println!(
        "{{\"uninitialized_output_checks\":{},\"null_query_checks\":1}}",
        checks
    );
}
