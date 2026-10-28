//! Object properties and arrays, through Zend's own update and add functions.
use crate::sys::{
    HashTable, add_assoc_long_ex, add_assoc_string_ex, add_next_index_str, swr_zend_array_init,
    zend_array_count, zend_class_entry, zend_long, zend_object, zend_string,
    zend_update_property_long, zend_update_property_string, zval,
};
use std::ffi::CStr;

/// `Z_ARRVAL_P`.
/// # Safety
/// `array` is a live array zval.
#[must_use]
#[inline]
pub unsafe fn table(array: *const zval) -> *mut HashTable {
    // SAFETY: per the caller.
    let value = unsafe { (*array).value };
    // SAFETY: an array zval holds `arr`.
    unsafe { value.arr }
}

/// `Z_STR_P`.
/// # Safety
/// `string` is a live string zval.
#[must_use]
#[inline]
pub unsafe fn str_of(string: *const zval) -> *mut zend_string {
    // SAFETY: per the caller.
    let value = unsafe { (*string).value };
    // SAFETY: a string zval holds `str`.
    unsafe { value.str_ }
}

/// `Z_LVAL_P`.
/// # Safety
/// `long` is a live int zval.
#[must_use]
#[inline]
pub unsafe fn long_of(long: *const zval) -> zend_long {
    // SAFETY: per the caller.
    let value = unsafe { (*long).value };
    // SAFETY: an int zval holds `lval`.
    unsafe { value.lval }
}

/// `zend_array_count(Z_ARRVAL_P(array))`.
/// # Safety
/// `array` is a live array zval.
#[must_use]
#[inline]
pub unsafe fn count(array: *const zval) -> u32 {
    // SAFETY: per the caller.
    let table = unsafe { table(array) };
    // SAFETY: a live table.
    unsafe { zend_array_count(table) }
}

/// `zend_update_property_long(ce, object, name, value)`.
/// # Safety
/// `ce` is a registered class and `object` a live instance of it.
#[inline]
pub unsafe fn update_long(
    ce: *mut zend_class_entry,
    object: *mut zend_object,
    name: &CStr,
    value: zend_long,
) {
    // SAFETY: per the caller; Zend copies the name.
    unsafe { zend_update_property_long(ce, object, name.as_ptr(), name.count_bytes(), value) };
}

/// `zend_update_property_string(ce, object, name, value)`.
/// # Safety
/// As `update_long`.
#[inline]
pub unsafe fn update_string(
    ce: *mut zend_class_entry,
    object: *mut zend_object,
    name: &CStr,
    value: &CStr,
) {
    // SAFETY: per the caller; Zend copies both strings.
    unsafe {
        zend_update_property_string(
            ce,
            object,
            name.as_ptr(),
            name.count_bytes(),
            value.as_ptr(),
        );
    }
}

/// `array_init(target)`.
/// # Safety
/// `target` is a writable zval holding nothing that needs releasing.
#[inline]
pub unsafe fn array_init(target: *mut zval) {
    // SAFETY: per the caller.
    unsafe { swr_zend_array_init(target) };
}

/// `add_assoc_long(array, key, value)`.
/// # Safety
/// `array` is a live array zval.
#[inline]
pub unsafe fn add_long(array: *mut zval, key: &CStr, value: zend_long) {
    // SAFETY: per the caller.
    unsafe { add_assoc_long_ex(array, key.as_ptr(), key.count_bytes(), value) };
}

/// `add_assoc_string(array, key, value)`: Zend copies the value.
/// # Safety
/// `array` is a live array zval.
#[inline]
pub unsafe fn add_string(array: *mut zval, key: &CStr, value: &CStr) {
    // SAFETY: per the caller.
    unsafe { add_assoc_string_ex(array, key.as_ptr(), key.count_bytes(), value.as_ptr()) };
}

/// `add_next_index_str(array, string)`: the array takes over the reference.
/// # Safety
/// `array` is a live array zval and the caller owns a reference to `string`.
#[inline]
pub unsafe fn push_str(array: *mut zval, string: *mut zend_string) {
    // SAFETY: per the caller.
    unsafe { add_next_index_str(array, string) };
}
