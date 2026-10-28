//! Throwing from a handler; the handler then returns and Zend unwinds.
use crate::{
    class_name,
    sys::{zend_class_entry, zend_long, zend_object, zend_throw_error, zend_throw_exception},
};
use std::{
    ffi::{CStr, CString},
    ptr,
};

/// `zend_throw_exception(ce, message, code)`.
/// # Safety
/// Called from a handler, with a registered exception class.
pub unsafe fn throw_exception(ce: *mut zend_class_entry, message: &CStr, code: zend_long) {
    // SAFETY: per the caller; Zend copies the message.
    unsafe { zend_throw_exception(ce, message.as_ptr(), code) };
}

/// `zend_throw_error(NULL, "%s", message)`: an `Error`.
/// # Safety
/// Called from a handler.
pub unsafe fn throw_error(message: &CStr) {
    // SAFETY: per the caller; "%s" takes the NUL-terminated message.
    unsafe { zend_throw_error(ptr::null_mut(), c"%s".as_ptr(), message.as_ptr()) };
}

/// Swoole's "Constructor of %s can only be called once" `Error`.
/// # Safety
/// Called from a handler, with a live object.
pub unsafe fn throw_constructed_twice(object: *const zend_object) {
    // SAFETY: per the caller.
    let name = unsafe { class_name(object) };
    let message = [
        b"Constructor of ",
        name.to_bytes(),
        b" can only be called once",
    ]
    .concat();
    // SAFETY: per the caller.
    unsafe { throw_error(&CString::new(message).unwrap_or_default()) };
}
