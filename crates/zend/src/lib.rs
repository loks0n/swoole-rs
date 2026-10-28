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

mod call;
mod class;
mod error;
mod object;
mod value;

pub use call::{Call, Invalid};
pub use class::{Class, class_name, unset_property_deny};
pub use error::{E_ERROR, E_WARNING, Message, php_error, throw_error, throw_exception};
pub use object::{Object, set_object};
pub use swoole_rs_zend_sys as sys;
pub use value::{
    PUBLIC, add_assoc_long, add_next_index_long, bytes, declare_class_long, declare_property_null,
    each_value, long_zval, object_of, register_long_constant, type_of, update_property,
    update_property_long,
};
