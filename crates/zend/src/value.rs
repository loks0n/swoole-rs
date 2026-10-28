//! Zvals, arrays, properties and constants: the Zend API calls Swoole's classes
//! make outside argument parsing.
use crate::sys::{
    CONST_CS, CONST_PERSISTENT, ZEND_ACC_PUBLIC, add_assoc_long_ex, swr_zend_hash_foreach,
    zend_array, zend_class_entry, zend_declare_class_constant_long, zend_declare_property_null,
    zend_object, zend_register_long_constant, zend_string, zend_update_property,
    zend_update_property_long, zval,
};
use std::{
    ffi::{CStr, c_int, c_void},
    mem::offset_of,
};

/// `Z_TYPE_P`.
/// # Safety
/// `value` is a live zval.
#[must_use]
#[inline]
pub unsafe fn type_of(value: *const zval) -> u32 {
    // SAFETY: per the caller.
    let u1 = unsafe { (*value).u1 };
    // SAFETY: every zval sets `type_info`.
    unsafe { u1.type_info & 0xff }
}

/// `ZSTR_VAL`/`ZSTR_LEN` of a live string, borrowed for as long as the caller
/// keeps the string alive.
/// # Safety
/// `string` is a live `zend_string`.
#[must_use]
#[inline]
pub unsafe fn bytes<'a>(string: *const zend_string) -> &'a [u8] {
    let start = string
        .wrapping_byte_add(offset_of!(zend_string, val))
        .cast::<u8>();
    // SAFETY: a live string.
    let length = unsafe { (*string).len };
    // SAFETY: a zend_string's `len` bytes follow its header.
    unsafe { std::slice::from_raw_parts(start, length) }
}

/// `add_assoc_long_ex(array, key, value)`.
/// # Safety
/// `array` is a live array zval.
pub unsafe fn add_assoc_long(array: *mut zval, key: &CStr, value: i64) {
    // SAFETY: per the caller; Zend copies the key.
    unsafe { add_assoc_long_ex(array, key.as_ptr(), key.count_bytes(), value) };
}

/// `add_next_index_long(array, value)`.
/// # Safety
/// `array` is a live array zval.
pub unsafe fn add_next_index_long(array: *mut zval, value: i64) {
    // SAFETY: per the caller.
    unsafe { crate::sys::add_next_index_long(array, value) };
}

/// `ZEND_HASH_FOREACH_VAL`: `each` returns false to stop early.
/// # Safety
/// `table` is a live array that `each` does not modify, and `each` does not
/// unwind.
pub unsafe fn each_value<F: FnMut(*mut zval) -> bool>(table: *const zend_array, mut each: F) {
    unsafe extern "C" fn trampoline<F: FnMut(*mut zval) -> bool>(
        value: *mut zval,
        context: *mut c_void,
    ) -> bool {
        // SAFETY: `context` is the closure `each_value` passed, live for the loop.
        let each = unsafe { &mut *context.cast::<F>() };
        each(value)
    }
    let context = (&raw mut each).cast::<c_void>();
    // SAFETY: per the caller; the closure outlives the loop.
    unsafe { swr_zend_hash_foreach(table, Some(trampoline::<F>), context) };
}

/// `zend_update_property_long(scope, object, name, value)`.
/// # Safety
/// `scope` is a registered class and `object` a live object.
pub unsafe fn update_property_long(
    scope: *mut zend_class_entry,
    object: *mut zend_object,
    name: &CStr,
    value: i64,
) {
    // SAFETY: per the caller.
    unsafe { zend_update_property_long(scope, object, name.as_ptr(), name.count_bytes(), value) };
}

/// `zend_update_property(scope, object, name, value)`: the property takes a copy.
/// # Safety
/// As [`update_property_long`], with a live `value`.
pub unsafe fn update_property(
    scope: *mut zend_class_entry,
    object: *mut zend_object,
    name: &CStr,
    value: *mut zval,
) {
    // SAFETY: per the caller.
    unsafe { zend_update_property(scope, object, name.as_ptr(), name.count_bytes(), value) };
}

/// `zend_declare_class_constant_long(class, name, value)`, at MINIT.
/// # Safety
/// `class` is a class being registered.
pub unsafe fn declare_class_long(class: *mut zend_class_entry, name: &CStr, value: i64) {
    // SAFETY: per the caller.
    unsafe { zend_declare_class_constant_long(class, name.as_ptr(), name.count_bytes(), value) };
}

/// `zend_declare_property_null(class, name, access)`, at MINIT; `access` is a
/// `ZEND_ACC_*` visibility.
/// # Safety
/// `class` is a class being registered.
pub unsafe fn declare_property_null(class: *mut zend_class_entry, name: &CStr, access: u32) {
    #[expect(
        clippy::cast_possible_wrap,
        reason = "ZEND_ACC_* visibilities are small"
    )]
    let access = access as c_int;
    // SAFETY: per the caller.
    unsafe { zend_declare_property_null(class, name.as_ptr(), name.count_bytes(), access) };
}

/// `ZEND_ACC_PUBLIC`, for [`declare_property_null`].
pub const PUBLIC: u32 = ZEND_ACC_PUBLIC;

/// `REGISTER_LONG_CONSTANT(name, value, CONST_CS | CONST_PERSISTENT)`, at MINIT.
/// # Safety
/// MINIT of the module `module`.
pub unsafe fn register_long_constant(name: &CStr, value: i64, module: c_int) {
    #[expect(clippy::cast_possible_wrap, reason = "constant flags are small")]
    let flags = (CONST_CS | CONST_PERSISTENT) as c_int;
    // SAFETY: per the caller; Zend copies the name.
    unsafe { zend_register_long_constant(name.as_ptr(), name.count_bytes(), value, flags, module) };
}

/// `ZVAL_LONG`: a zval holding `value`.
#[must_use]
pub fn long_zval(value: i64) -> zval {
    // SAFETY: a zval is plain data; all-zero bytes are `IS_UNDEF`.
    let mut zv: zval = unsafe { std::mem::zeroed() };
    zv.value = crate::sys::zend_value { lval: value };
    zv.u1 = crate::sys::_zval_struct__bindgen_ty_1 {
        type_info: crate::sys::IS_LONG,
    };
    zv
}

/// `Z_OBJ_P`.
/// # Safety
/// `value` is a live object zval.
#[must_use]
#[inline]
pub unsafe fn object_of(value: *const zval) -> *mut zend_object {
    // SAFETY: per the caller.
    let value = unsafe { (*value).value };
    // SAFETY: an object zval holds its object.
    unsafe { value.obj }
}
