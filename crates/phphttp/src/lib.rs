//! PHP `Swoole\Http` classes over the zend crates and the httpbindings policy.
//! A crate of its own so the native gates that link `libswoole_rs_ffi.a` into
//! executables never pull in objects with Zend imports (docs/zend.md).
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

mod cookie;

pub use cookie::*;
