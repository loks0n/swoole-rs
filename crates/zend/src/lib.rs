//! Thin safe layer over `swoole-rs-zend-sys` for PHP classes written in Rust:
//! call frames (arguments, `$this`, return values), objects that embed their
//! `zend_object`, class registration and errors. It grows as callers need it.
//! See docs/zend.md.
//!
//! Without the `php` feature the crate is empty.
#![cfg(feature = "php")]
#![cfg_attr(
    not(test),
    deny(
        clippy::undocumented_unsafe_blocks,
        clippy::multiple_unsafe_ops_per_block
    )
)]

pub mod bailout;
mod call;
mod class;
mod error;
mod object;
mod value;

pub use call::{Call, Invalid};
pub use class::{Class, class_name, unset_property_deny};
pub use class::{register_double_constant, register_long_constant};
pub use error::{throw_constructed_twice, throw_error, throw_exception};
pub use object::{Object, init_object, set_object};
pub use swoole_rs_zend_sys as sys;
pub use value::{
    bytes, declare_long, declare_null, long_of, push_string, set_key, string_of, type_of,
    update_long, value_of,
};

/// Export Zend handlers under Zend's own names (`zim_<class>_<method>` for
/// methods, `zif_<function>` for functions) so upstream's tables name them
/// unchanged; each runs `body(&Call)`.
#[macro_export]
macro_rules! handlers {
    ($($name:ident => $body:path;)*) => {$(
        /// A Zend handler.
        /// # Safety
        /// Called by Zend with a live frame and return slot.
        #[unsafe(no_mangle)]
        pub unsafe extern "C" fn $name(
            frame: *mut $crate::sys::zend_execute_data,
            value: *mut $crate::sys::zval,
        ) {
            // SAFETY: per Zend's handler contract.
            $body(&unsafe { $crate::Call::new(frame, value) });
        }
    )*};
}
