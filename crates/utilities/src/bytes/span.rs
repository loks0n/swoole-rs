//! Complete inline cursor, mutable suffix and pointer-result publication.
use std::ffi::{CStr, c_char};
unsafe extern "C" {
    fn memcmp(a: *const c_char, b: *const c_char, count: usize) -> i32;
}

fn whitespace(byte: u8, signed_char: u8) -> bool {
    let promoted = if signed_char != 0 {
        i32::from(byte as i8)
    } else {
        i32::from(byte)
    };
    unsafe { super::isspace(promoted) != 0 }
}

/// Trim and advance the caller's actual cursor, at each original publication.
/// # Safety
/// With length0 cursor need not be readable. Otherwise cursor is a writable
/// native char-pointer slot and each visited byte is readable, with defined
/// native isspace promotion. Caller owns its provenance and quiescence. No Rust
/// reference covers the slot/range or survives the host libc classification.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_utils_ltrim(
    cursor: *mut *mut c_char,
    length: usize,
    signed_char: u8,
) -> usize {
    let mut skipped = 0;
    while skipped < length {
        // Keep the original short-circuit and fresh cursor observations.
        if unsafe { cursor.read().read() } == 0
            || !whitespace(unsafe { cursor.read().cast::<u8>().read() }, signed_char)
        {
            break;
        }
        unsafe { cursor.write(cursor.read().add(1)) };
        skipped += 1;
    }
    length - skipped
}

/// Mutable suffix trim: classify and clear each byte before visiting its left.
/// # Safety
/// Visited bytes are readable/writable with original native isspace promotions;
/// length0 accesses nothing (including null). Caller owns range and quiescence.
/// No allocation, pointer retention, callback or full-range Rust borrow.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_utils_rtrim(
    data: *mut c_char,
    length: usize,
    signed_char: u8,
) -> usize {
    let mut kept = length;
    while kept != 0 {
        let byte = unsafe { data.add(kept - 1) };
        if !whitespace(unsafe { byte.cast::<u8>().read() }, signed_char) {
            break;
        }
        unsafe { byte.write(0) };
        kept -= 1;
    }
    kept
}

/// Borrowed result facts only. Pointer derives from the input allocation;
/// offset-1 and null denote a miss. needle_length records native uint32 narrowing.
#[repr(C)]
pub struct SwrUtilsSearchResult {
    pub pointer: *const c_char,
    pub offset: isize,
    pub needle_length: u32,
}

/// Complete forward binary/casefold or reverse C-needle search and projection.
/// # Safety
/// Modes0/1 obey the original visited-byte/compared-range and nonempty-needle
/// contract. Mode2 reads a valid NUL-terminated needle first, narrows its size as
/// the original uint32 assignment, then requires length>=narrowed needle size.
/// Original reverse index0 omission and casefold first-byte guard remain.
/// Native debug assertions run after return; empty/narrowed-zero needle domains
/// and their assertion ordering remain unqualified. No pointer is retained.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_utils_search(
    data: *const c_char,
    length: usize,
    needle: *const c_char,
    needle_length: u32,
    mode: u8,
) -> SwrUtilsSearchResult {
    let needle_length = if mode == 2 {
        unsafe { CStr::from_ptr(needle) }.to_bytes().len() as u32
    } else {
        needle_length
    };
    // Match only the ranges the native loop actually observes. Do not form
    // slices spanning unused haystack/needle tails before an early result.
    let count = needle_length as usize;
    let mut offset = -1;
    if count != 0 && count <= length && mode <= 2 {
        let mut position = if mode == 2 { length - count } else { 0 };
        while if mode == 2 {
            position != 0
        } else {
            position <= length - count
        } {
            let current = unsafe { data.add(position) };
            let first_matches = unsafe { current.read() == needle.read() };
            let matched = first_matches
                && unsafe {
                    if mode == 1 {
                        super::strncasecmp(current, needle, count) == 0
                    } else {
                        memcmp(current, needle, count) == 0
                    }
                };
            if matched {
                offset = position as isize;
                break;
            }
            if mode == 2 {
                position -= 1;
            } else {
                position += 1;
            }
        }
    }
    SwrUtilsSearchResult {
        pointer: if offset < 0 {
            std::ptr::null()
        } else {
            unsafe { data.add(offset as usize) }
        },
        offset,
        needle_length,
    }
}
