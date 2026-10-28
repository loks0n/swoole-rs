//! Non-persistent `zend_string`s: allocated here, handed to Zend by a return
//! value or an array, or freed.
use crate::sys::{
    swr_zend_string_alloc, swr_zend_string_free, swr_zend_string_realloc, zend_string,
};
use std::mem::offset_of;

/// `ZSTR_VAL`/`ZSTR_LEN` as bytes (without the terminating NUL, which follows).
/// # Safety
/// `string` is live for `'a`.
#[must_use]
#[inline]
pub unsafe fn bytes<'a>(string: *const zend_string) -> &'a [u8] {
    // SAFETY: a live string.
    let length = unsafe { (*string).len };
    // SAFETY: a live string holds `len` bytes at `val`.
    unsafe { std::slice::from_raw_parts(val(string.cast_mut()), length) }
}

/// `ZSTR_VAL`: the first byte.
#[must_use]
#[inline]
pub fn val(string: *mut zend_string) -> *mut u8 {
    string
        .wrapping_byte_add(offset_of!(zend_string, val))
        .cast()
}

/// `zend::fetch_zend_string_by_val`: the string whose `ZSTR_VAL` is `val`.
#[must_use]
#[inline]
pub fn from_val(val: *mut u8) -> *mut zend_string {
    val.wrapping_byte_sub(offset_of!(zend_string, val)).cast()
}

/// `zend_string_alloc(length, 0)`: room for `length` bytes and a NUL.
#[must_use]
#[inline]
pub fn alloc(length: usize) -> *mut zend_string {
    // SAFETY: Zend's request allocator; it bails out rather than return null.
    unsafe { swr_zend_string_alloc(length) }
}

/// `zend_string_realloc(string, length, 0)`.
/// # Safety
/// `string` is a live, unshared, non-interned string.
#[must_use]
#[inline]
pub unsafe fn realloc(string: *mut zend_string, length: usize) -> *mut zend_string {
    // SAFETY: per the caller.
    unsafe { swr_zend_string_realloc(string, length) }
}

/// `zend_string_free`.
/// # Safety
/// `string` is a live, unshared, non-interned string nothing else references.
#[inline]
pub unsafe fn free(string: *mut zend_string) {
    // SAFETY: per the caller.
    unsafe { swr_zend_string_free(string) };
}

/// `ZSTR_LEN(string) = length; ZSTR_VAL(string)[length] = '\0'`.
/// # Safety
/// `string` is live, unshared and holds at least `length` bytes.
#[inline]
pub unsafe fn truncate(string: *mut zend_string, length: usize) {
    // SAFETY: per the caller.
    unsafe { (*string).len = length };
    // SAFETY: an allocation of at least `length` bytes has room for the NUL.
    let end = unsafe { val(string).add(length) };
    // SAFETY: as above.
    unsafe { *end = 0 };
}
