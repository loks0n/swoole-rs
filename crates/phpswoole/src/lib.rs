//! The swoole module host (with the `php` feature, see docs/zend.md): the global
//! constants, `Swoole\Exception` and `Swoole\Error`, and the global functions of
//! `php_swoole.cc`. C++ keeps the function table built from the stubs' arginfo,
//! the module globals and Swoole's error, logger and MIME state, which it lends
//! as a table of operations.
#![cfg(feature = "php")]
#![cfg_attr(
    not(test),
    deny(
        clippy::undocumented_unsafe_blocks,
        clippy::multiple_unsafe_ops_per_block
    )
)]

mod constants;
mod functions;
mod interfaces;

use std::{ffi::c_char, ptr, sync::OnceLock};
use swoole_rs_zend::{
    Class,
    sys::{zend_array, zend_ce_error, zend_ce_exception, zend_class_entry, zval},
};

/// What only C++ can reach (`swr_v1_phpswoole_ops`).
#[repr(C)]
pub struct Ops {
    /// `swoole_get_last_error()`.
    last_error: unsafe extern "C" fn() -> i32,
    /// `swoole_set_last_error(code)`.
    set_last_error: unsafe extern "C" fn(code: i32),
    /// `SWOOLE_G(display_errors)`.
    display_errors: unsafe extern "C" fn() -> u8,
    /// `SW_CPU_NUM`.
    cpu_num: unsafe extern "C" fn() -> u32,
    /// `sw_logger()->put(level, message, length)`.
    log_put: unsafe extern "C" fn(level: i32, message: *const c_char, length: usize),
    /// `swoole_error_log`'s tail: set the error, then put the formatted
    /// message if the level passes and the error is not ignored.
    error_log: unsafe extern "C" fn(level: i32, error: i32, message: *const c_char, length: usize),
    /// `swoole_ignore_error(code)`.
    ignore_error: unsafe extern "C" fn(code: i32),
    mime_add: unsafe extern "C" fn(suffix: *const c_char, kind: *const c_char) -> u8,
    mime_set: unsafe extern "C" fn(suffix: *const c_char, kind: *const c_char),
    mime_del: unsafe extern "C" fn(suffix: *const c_char) -> u8,
    mime_get: unsafe extern "C" fn(filename: *const c_char) -> *const c_char,
    mime_exists: unsafe extern "C" fn(filename: *const c_char) -> u8,
    /// Push every MIME type onto `array`.
    mime_list: unsafe extern "C" fn(array: *mut zval),
    /// `req_status` from `RINIT_END` to `CALL_USER_SHUTDOWNFUNC_BEGIN`; 0 if
    /// it was not `RINIT_END`.
    shutdown_begin: unsafe extern "C" fn() -> u8,
    /// `zend::unserialize`.
    unserialize: unsafe extern "C" fn(
        value: *mut zval,
        buf: *const c_char,
        length: usize,
        options: *mut zend_array,
    ),
    /// `zend::json_decode`.
    json_decode: unsafe extern "C" fn(
        value: *mut zval,
        text: *const c_char,
        length: usize,
        options: i64,
        depth: i64,
    ),
}

static OPS: OnceLock<&'static Ops> = OnceLock::new();
static EXCEPTION: Class = Class::new();
static ERROR: Class = Class::new();

fn ops() -> &'static Ops {
    // Functions run only after MINIT stored the table.
    OPS.get().copied().unwrap_or_else(|| std::process::abort())
}

/// MINIT: the global constants, then `Swoole\Exception` and `Swoole\Error`,
/// whose entries are written to `exception` and `error` for C++.
/// # Safety
/// Called once, at MINIT, with the module's number, a static operations table
/// and writable class-entry globals.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpswoole_minit(
    module_number: i32,
    flags: u32,
    ops: *const Ops,
    exception: *mut *mut zend_class_entry,
    error: *mut *mut zend_class_entry,
) {
    // SAFETY: per the caller, a static table.
    if let Some(ops) = unsafe { ops.as_ref() } {
        OPS.get_or_init(|| ops);
    }
    // SAFETY: MINIT, with the module's number.
    unsafe { constants::register(module_number, flags) };
    // SAFETY: Zend registers Exception before any extension's MINIT.
    let parent = unsafe { zend_ce_exception };
    // SAFETY: MINIT, extending Exception, with no methods.
    unsafe { EXCEPTION.register_child(c"Swoole\\Exception", ptr::null(), parent, |_, _| {}) };
    // SAFETY: Zend registers Error before any extension's MINIT.
    let parent = unsafe { zend_ce_error };
    // SAFETY: MINIT, extending Error, with no methods.
    unsafe { ERROR.register_child(c"Swoole\\Error", ptr::null(), parent, |_, _| {}) };
    // SAFETY: per the caller, writable globals.
    unsafe { exception.write(EXCEPTION.entry()) };
    // SAFETY: as above.
    unsafe { error.write(ERROR.entry()) };
}
