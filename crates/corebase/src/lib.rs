#![expect(
    clippy::cast_possible_truncation,
    clippy::cast_possible_wrap,
    clippy::cast_sign_loss,
    reason = "#157: casts not yet checked"
)]
// SPDX-License-Identifier: Apache-2.0
// Compatibility derived from Swoole v6.2.2 src/core/base.cc (Swoole contributors).
//! Core numeric and byte helpers; native code retains allocation and effect custody.
mod hook;
mod lifecycle;
mod random;
pub use hook::swr_v1_corebase_hook_add_action;
pub use lifecycle::{
    LifecycleState, swr_v1_corebase_init_next, swr_v1_corebase_lifecycle_next,
    swr_v1_corebase_task_tmp_next,
};
pub use random::{RandomState, swr_v1_corebase_random_next};

use std::ffi::{c_char, c_int, c_long, c_ulong};
use std::{cmp::Ordering, ptr, slice};

unsafe extern "C" {
    fn strtol(input: *const c_char, end: *mut *mut c_char, base: c_int) -> c_long;
    fn strtoul(input: *const c_char, end: *mut *mut c_char, base: c_int) -> c_ulong;
    fn strncasecmp(left: *const c_char, right: *const c_char, count: usize) -> c_int;
    fn toupper(value: c_int) -> c_int;
}

/// Parse the successful, representable portion of `std::stoi` using the host
/// decimal parser. Native code retains the throwing path and output publication.
/// # Safety
/// `input` is a valid NUL-terminated string and `output` is writable and disjoint.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_corebase_parse_stoi(
    input: *const c_char,
    output: *mut c_int,
) -> u8 {
    if input.is_null() || output.is_null() {
        return 0;
    }
    let mut end = ptr::null_mut();
    let value = unsafe { strtol(input, &mut end, 10) };
    if end.cast_const() == input || value < c_int::MIN as c_long || value > c_int::MAX as c_long {
        return 0;
    }
    unsafe { output.write(value as c_int) };
    1
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_corebase_type_size(kind: u8) -> c_int {
    match kind {
        b'c' | b'C' => 1,
        b's' | b'S' | b'n' | b'v' => 2,
        b'l' | b'L' | b'N' | b'V' => 4,
        b'q' | b'Q' | b'J' | b'P' => 8,
        _ => 0,
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_corebase_gcd(mut left: u32, mut right: u32) -> u32 {
    while right != 0 {
        (left, right) = (right, left % right);
    }
    left
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_corebase_lcm(left: u32, right: u32) -> u32 {
    let divisor = swr_v1_corebase_gcd(left, right);
    left.wrapping_mul(right).checked_div(divisor).unwrap_or(0)
}

/// Select the native warning, error, or accepted-value path for systemd fds.
/// Native environment parsing and all logging/error-state effects stay outside Rust.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_corebase_systemd_listen_fds_action(
    found: u8,
    count: i32,
    maximum: i32,
) -> u32 {
    if found == 0 {
        1 // missing LISTEN_FDS: native warning, then -1
    } else if count >= maximum {
        2 // too many: native error-log path, then -1
    } else {
        0 // native returns the original parsed signed value
    }
}

/// Write decimal native-long bytes and NUL; return the byte count before NUL.
/// # Safety
/// Output fits the value's decimal representation plus NUL and does not alias
/// this call's stack storage.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_corebase_itoa(output: *mut c_char, value: c_long) -> c_int {
    let mut buffer = itoa::Buffer::new();
    let bytes = buffer.format(value).as_bytes();
    unsafe {
        ptr::copy_nonoverlapping(bytes.as_ptr(), output.cast(), bytes.len());
        output.add(bytes.len()).write(0);
    }
    bytes.len() as c_int
}

/// Format backwards into native scratch storage; return the first digit offset.
/// SIZE_MAX rejects invalid radix, null output or insufficient maximum capacity.
/// # Safety
/// Nonnull output is writable for capacity bytes, with no overlapping live borrow.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_corebase_radix(
    mut value: c_ulong,
    radix: u32,
    output: *mut u8,
    capacity: usize,
) -> usize {
    if !(2..=36).contains(&radix) || output.is_null() || capacity < c_ulong::BITS as usize + 1 {
        return usize::MAX;
    }
    const DIGITS: &[u8; 36] = b"0123456789abcdefghijklmnopqrstuvwxyz";
    let mut index = capacity - 1;
    unsafe { output.add(index).write(0) };
    loop {
        index -= 1;
        unsafe {
            output
                .add(index)
                .write(DIGITS[(value % c_ulong::from(radix)) as usize])
        };
        value /= c_ulong::from(radix);
        if value == 0 {
            return index;
        }
    }
}

/// Target-default char mode retained for the frozen two-argument ABI.
/// # Safety
/// Same input/output requirements as swr_v1_corebase_hex_mode; native char mode
/// must match this Rust target's default c_char.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_corebase_hex(input: *const c_char, parsed: *mut usize) -> c_ulong {
    unsafe { swr_v1_corebase_hex_mode(input, parsed, u8::from(c_char::MIN != 0)) }
}

/// Preserve native prefix, locale, signed-char and size_t wrap semantics.
/// # Safety
/// Input is a valid NUL-terminated C string; parsed is writable and disjoint.
/// Bytes passed to toupper must satisfy the original host's ctype precondition.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_corebase_hex_mode(
    input: *const c_char,
    parsed: *mut usize,
    native_char_signed: u8,
) -> c_ulong {
    let mut current = input;
    let mut value = 0_usize;
    unsafe {
        parsed.write(0);
        if strncasecmp(input, c"0x".as_ptr(), 2) == 0 {
            current = current.add(2);
        }
        loop {
            let byte = current.cast::<u8>().read();
            let digit = if byte.is_ascii_digit() {
                (byte - b'0') as usize
            } else {
                let input = if native_char_signed != 0 {
                    byte as i8 as c_int
                } else {
                    byte as c_int
                };
                let upper = toupper(input);
                let byte = if native_char_signed != 0 {
                    upper as i8 as c_int
                } else {
                    upper as u8 as c_int
                };
                if !(c_int::from(b'A')..=c_int::from(b'Z')).contains(&byte) {
                    break;
                }
                (byte - c_int::from(b'A')) as usize + 10
            };
            value = value.wrapping_mul(16).wrapping_add(digit);
            current = current.add(1);
        }
        parsed.write(current.offset_from(input) as usize);
    }
    value as c_ulong
}

/// Compare components using the same host libc parser and observable errno order.
/// # Safety
/// Both inputs are valid NUL-terminated C strings for the duration of this call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_corebase_version(
    mut left: *const c_char,
    mut right: *const c_char,
) -> c_int {
    unsafe {
        loop {
            let (mut left_end, mut right_end) = (ptr::null_mut(), ptr::null_mut());
            let first = strtoul(left, &mut left_end, 10);
            let second = strtoul(right, &mut right_end, 10);
            match first.cmp(&second) {
                Ordering::Less => return -1,
                Ordering::Greater => return 1,
                Ordering::Equal => {}
            }
            match (left_end.read() == 0, right_end.read() == 0) {
                (true, true) => return 0,
                (true, false) => return -1,
                (false, true) => return 1,
                (false, false) => {
                    left = left_end.add(1);
                    right = right_end.add(1);
                }
            }
        }
    }
}

/// Return the prefix length for native std::string construction, including root.
/// # Safety
/// Nonempty input is readable for length bytes, with length at most isize::MAX.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_corebase_dirname(input: *const u8, length: usize) -> usize {
    if length == 0 {
        return 0;
    }
    unsafe { slice::from_raw_parts(input, length) }
        .iter()
        .rposition(|&byte| byte == b'/')
        .map_or(0, |index| index.max(1))
}

/// Native stack-owned iterator state; no retained pointer or allocation.
#[repr(C)]
#[derive(Default)]
pub struct MkdirState {
    pub length: usize,
    pub next: usize,
}

/// Prepare/cut the next native mkdir prefix. 0=done, 1=prefix, 2=too long,
/// 3=invalid state/storage. Native access/mkdir/logging execute after return.
/// # Safety
/// Input is readable for input_length bytes. Output is writable for capacity
/// bytes, disjoint from input and initialized state. State starts zeroed, then
/// stays unmodified between calls; output stays unchanged by native IO. Stop on
/// any result other than1. All pointers remain valid during each call only.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_corebase_mkdir_next(
    input: *const u8,
    input_length: usize,
    output: *mut u8,
    capacity: usize,
    state: *mut MkdirState,
) -> c_int {
    if output.is_null() || state.is_null() || capacity == 0 || capacity > isize::MAX as usize {
        return 3;
    }
    let state = unsafe { &mut *state };
    if state.next == 0 {
        if input_length >= capacity {
            return 2;
        }
        if input.is_null() || input_length == 0 {
            return 3;
        }
        let input = unsafe { slice::from_raw_parts(input, input_length) };
        let prefix = input
            .iter()
            .position(|&byte| byte == 0)
            .unwrap_or(input_length);
        let append = input[input_length - 1] != b'/';
        let length = prefix + usize::from(append);
        if length >= capacity {
            return 2;
        }
        unsafe {
            ptr::copy_nonoverlapping(input.as_ptr(), output, prefix);
            if append {
                output.add(prefix).write(b'/');
            }
            output.add(length).write(0);
        }
        state.length = length;
        state.next = 1;
    } else {
        if state.length >= capacity || state.next > state.length {
            return 3;
        }
        unsafe { output.add(state.next - 1).write(b'/') };
    }
    for index in state.next..state.length {
        if unsafe { output.add(index).read() } == b'/' {
            unsafe { output.add(index).write(0) };
            state.next = index + 1;
            return 1;
        }
    }
    0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn mkdir_prefixes_preserve_slashes_and_original_nul_order() {
        fn prefixes(input: &[u8]) -> Vec<Vec<u8>> {
            let mut storage = [std::mem::MaybeUninit::<u8>::uninit(); 64];
            let mut state = MkdirState::default();
            let mut prefixes = Vec::new();
            loop {
                let step = unsafe {
                    swr_v1_corebase_mkdir_next(
                        input.as_ptr(),
                        input.len(),
                        storage.as_mut_ptr().cast(),
                        storage.len(),
                        &mut state,
                    )
                };
                if step == 0 {
                    return prefixes;
                }
                assert_eq!(step, 1);
                let prefix = unsafe { std::ffi::CStr::from_ptr(storage.as_ptr().cast()) };
                prefixes.push(prefix.to_bytes().to_vec());
            }
        }
        assert_eq!(
            prefixes(b"foo//bar"),
            [b"foo".to_vec(), b"foo/".to_vec(), b"foo//bar".to_vec()]
        );
        assert_eq!(prefixes(b"a\0/b"), [b"a".to_vec()]);
        assert!(prefixes(b"a\0/b/").is_empty());
        assert!(prefixes(b"/").is_empty());
    }

    #[test]
    fn wrapped_product_precedes_division() {
        assert_eq!(swr_v1_corebase_lcm(65536, 65536), 0);
        assert_eq!(swr_v1_corebase_gcd(u32::MAX, u32::MAX - 1), 1);
    }

    #[test]
    fn systemd_listener_policy_preserves_missing_limit_and_signed_values() {
        assert_eq!(swr_v1_corebase_systemd_listen_fds_action(0, 0, 60000), 1);
        assert_eq!(
            swr_v1_corebase_systemd_listen_fds_action(1, 59999, 60000),
            0
        );
        assert_eq!(
            swr_v1_corebase_systemd_listen_fds_action(1, 60000, 60000),
            2
        );
        assert_eq!(
            swr_v1_corebase_systemd_listen_fds_action(1, 60001, 60000),
            2
        );
        assert_eq!(swr_v1_corebase_systemd_listen_fds_action(1, -1, 60000), 0);
    }

    #[test]
    fn stoi_parser_publishes_only_representable_decimal_values() {
        for (text, expected) in [
            ("0", 0),
            ("+42tail", 42),
            (" -2147483648x", i32::MIN),
            ("2147483647", i32::MAX),
        ] {
            let input = std::ffi::CString::new(text).unwrap();
            let mut output = 0x13579bdf;
            assert_eq!(
                unsafe { swr_v1_corebase_parse_stoi(input.as_ptr(), &mut output) },
                1
            );
            assert_eq!(output, expected);
        }
        for text in ["", "x", "  ", "+", "2147483648", "-2147483649"] {
            let input = std::ffi::CString::new(text).unwrap();
            let mut output = 0x13579bdf;
            assert_eq!(
                unsafe { swr_v1_corebase_parse_stoi(input.as_ptr(), &mut output) },
                0
            );
            assert_eq!(output, 0x13579bdf);
        }
    }

    #[test]
    fn native_hex_accepts_non_hex_letters_and_counts_prefix() {
        let mut parsed = 0;
        unsafe {
            assert_eq!(
                swr_v1_corebase_hex(c"FFtail".as_ptr(), &mut parsed),
                16833333
            );
            assert_eq!(parsed, 6);
            assert_eq!(swr_v1_corebase_hex(c"0x".as_ptr(), &mut parsed), 0);
            assert_eq!(parsed, 2);
        }
    }

    #[test]
    fn borrowed_binary_path_and_output_bounds() {
        assert_eq!(unsafe { swr_v1_corebase_dirname(b"a\0/b".as_ptr(), 4) }, 2);
        let mut output = [0xa5; 2];
        assert_eq!(
            unsafe { swr_v1_corebase_radix(0, 10, output.as_mut_ptr(), 2) },
            usize::MAX
        );
        assert_eq!(output, [0xa5; 2]);
        let mut decimal = [0xa5u8; 4];
        assert_eq!(
            unsafe { swr_v1_corebase_itoa(decimal.as_mut_ptr().cast(), -1) },
            2
        );
        assert_eq!(decimal, [b'-', b'1', 0, 0xa5]);
    }
}
