//! Throwing from a handler; the handler then returns and Zend unwinds.
use crate::sys::{zend_class_entry, zend_long, zend_throw_error, zend_throw_exception};
use std::{ffi::CStr, ptr};

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
