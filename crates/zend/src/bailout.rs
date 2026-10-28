//! Zend bailouts (`zend_bailout`, a `longjmp` to the nearest `zend_try`) around
//! code Rust calls. A bailout must never jump over a Rust frame, so Rust traps
//! it in C, returns normally, and hands a [`Bailout`] back to the C or C++ that
//! called it, which re-raises it with `zend_bailout()`. See docs/zend.md.
use crate::{
    Invalid,
    sys::{
        swr_zend_parse_func, swr_zend_try, swr_zend_try_call, zend_fcall_info,
        zend_fcall_info_cache, zval,
    },
};
use std::ffi::c_void;

/// A trapped bailout. Its owner finishes its Rust work, then reports it to
/// the C/C++ caller (for example as a flag), which calls `zend_bailout()`.
#[must_use = "a trapped bailout must be re-raised by the C/C++ caller"]
#[derive(Debug)]
pub struct Bailout;

/// Run `body(arg)` inside `zend_try`.
/// # Errors
/// `body` bailed out; Zend's state is as `zend_catch` leaves it.
/// # Safety
/// `body` is C or C++, not Rust (a bailout inside it would jump over its
/// frame), and may be called with `arg`.
pub unsafe fn trap(
    body: unsafe extern "C" fn(*mut c_void),
    arg: *mut c_void,
) -> Result<(), Bailout> {
    // SAFETY: per the caller; the shim's setjmp sits in C, between this frame
    // and `body`.
    if unsafe { swr_zend_try(Some(body), arg) } != 0 {
        return Err(Bailout);
    }
    Ok(())
}

/// `zend_call_function(fci, fcc)` inside `zend_try`: whether the call
/// succeeded.
/// # Errors
/// The callable bailed out (`exit()`, a fatal error).
/// # Safety
/// `fci` and `fcc` describe a live callable, as `zend_call_function` requires.
pub unsafe fn call(
    fci: *mut zend_fcall_info,
    fcc: *mut zend_fcall_info_cache,
) -> Result<bool, Bailout> {
    let mut result = 0;
    // SAFETY: per the caller; Zend runs in the C shim's frame.
    if unsafe { swr_zend_try_call(fci, fcc, &raw mut result) } != 0 {
        return Err(Bailout);
    }
    Ok(result != 0)
}

/// `Z_PARAM_FUNC` of a passed argument (1-based).
/// # Errors
/// Not a callable; Zend has raised its parameter error.
/// # Safety
/// `arg` is the live zval of argument `number`; `fci` and `fcc` are writable.
pub unsafe fn parse_func(
    arg: *mut zval,
    number: u32,
    fci: *mut zend_fcall_info,
    fcc: *mut zend_fcall_info_cache,
) -> Result<(), Invalid> {
    // SAFETY: per the caller.
    if unsafe { swr_zend_parse_func(arg, number, fci, fcc) } != 0 {
        Ok(())
    } else {
        Err(Invalid)
    }
}
