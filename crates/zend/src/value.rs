//! Reading zvals and strings, and filling arrays and properties.
use crate::sys::{
    add_assoc_null_ex, add_assoc_stringl_ex, add_next_index_str, swr_zval_get_long,
    zend_class_entry, zend_declare_property_long, zend_declare_property_null, zend_long,
    zend_object, zend_string, zend_update_property_long, zend_value, zval,
};
use std::{ffi::CStr, mem::offset_of, slice};

/// `Z_TYPE_P`.
/// # Safety
/// `value` is a live zval.
#[must_use]
#[inline]
pub unsafe fn type_of(value: *const zval) -> u32 {
    // SAFETY: per the caller.
    let u1 = unsafe { (*value).u1 };
    // SAFETY: every zval sets `u1.type_info`.
    unsafe { u1.type_info & 0xff }
}

/// `Z_STR_P`, `Z_LVAL_P`, ...: the value union, read by its type's field.
/// # Safety
/// `value` is a live zval.
#[must_use]
#[inline]
pub unsafe fn value_of(value: *const zval) -> zend_value {
    // SAFETY: per the caller.
    unsafe { (*value).value }
}

/// `ZSTR_VAL`/`ZSTR_LEN` as a slice.
/// # Safety
/// `string` is a live `zend_string` that outlives the slice.
#[must_use]
#[inline]
pub unsafe fn bytes<'a>(string: *const zend_string) -> &'a [u8] {
    let data = string
        .wrapping_byte_add(offset_of!(zend_string, val))
        .cast();
    // SAFETY: per the caller.
    let length = unsafe { (*string).len };
    // SAFETY: a zend_string holds `len` bytes at `val`.
    unsafe { slice::from_raw_parts(data, length) }
}

/// `Z_STR_P`'s bytes when `value` is a string.
/// # Safety
/// `value` is a live zval that outlives the slice.
#[must_use]
#[inline]
pub unsafe fn string_of<'a>(value: *const zval) -> Option<&'a [u8]> {
    // SAFETY: per the caller.
    if unsafe { type_of(value) } != crate::sys::IS_STRING {
        return None;
    }
    // SAFETY: per the caller.
    let value = unsafe { value_of(value) };
    // SAFETY: an IS_STRING zval holds `str_`.
    let string = unsafe { value.str_ };
    // SAFETY: the string lives as long as the zval.
    Some(unsafe { bytes(string) })
}

/// `zval_get_long`.
/// # Safety
/// `value` is a live zval.
#[must_use]
pub unsafe fn long_of(value: *const zval) -> i64 {
    // SAFETY: per the caller.
    unsafe { swr_zval_get_long(value) }
}

/// `zend_declare_property_long(ce, name, value, ZEND_ACC_PUBLIC)`.
/// # Safety
/// MINIT, with a registered class.
pub unsafe fn declare_long(ce: *mut zend_class_entry, name: &CStr, value: zend_long) {
    #[expect(clippy::cast_possible_wrap, reason = "ZEND_ACC_PUBLIC is 1")]
    // SAFETY: per the caller; Zend copies the name.
    unsafe {
        zend_declare_property_long(
            ce,
            name.as_ptr(),
            name.count_bytes(),
            value,
            crate::sys::ZEND_ACC_PUBLIC as i32,
        );
    }
}

/// `zend_declare_property_null(ce, name, ZEND_ACC_PUBLIC)`.
/// # Safety
/// MINIT, with a registered class.
pub unsafe fn declare_null(ce: *mut zend_class_entry, name: &CStr) {
    #[expect(clippy::cast_possible_wrap, reason = "ZEND_ACC_PUBLIC is 1")]
    // SAFETY: per the caller; Zend copies the name.
    unsafe {
        zend_declare_property_null(
            ce,
            name.as_ptr(),
            name.count_bytes(),
            crate::sys::ZEND_ACC_PUBLIC as i32,
        );
    }
}

/// `zend_update_property_long(scope, object, name, value)`.
/// # Safety
/// A live object of `scope` or a subclass.
pub unsafe fn update_long(
    scope: *mut zend_class_entry,
    object: *mut zend_object,
    name: &CStr,
    value: zend_long,
) {
    // SAFETY: per the caller.
    unsafe { zend_update_property_long(scope, object, name.as_ptr(), name.count_bytes(), value) };
}

/// `add_next_index_str`: the array takes over `string`'s reference.
/// # Safety
/// `array` is a live array zval and `string` a live string.
pub unsafe fn push_string(array: *mut zval, string: *mut zend_string) {
    // SAFETY: per the caller.
    unsafe { add_next_index_str(array, string) };
}

/// `add_assoc_stringl_ex`, or `add_assoc_null_ex` when `value` is `None`.
/// # Safety
/// `array` is a live array zval.
pub unsafe fn set_key(array: *mut zval, key: &[u8], value: Option<&[u8]>) {
    match value {
        // SAFETY: per the caller; Zend copies key and value.
        Some(v) => unsafe {
            add_assoc_stringl_ex(
                array,
                key.as_ptr().cast(),
                key.len(),
                v.as_ptr().cast(),
                v.len(),
            );
        },
        // SAFETY: per the caller; Zend copies the key.
        None => unsafe { add_assoc_null_ex(array, key.as_ptr().cast(), key.len()) },
    }
}
