//! PHP client classes in Rust over the zend crate: `Swoole\Coroutine\Socket`
//! (registration, constants, objects and methods). C++ keeps the method table
//! built from the stub's arginfo and the coroutine socket itself, which the
//! methods reach through `native`. See docs/zend.md.
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

mod constants;
mod native;
mod socket;

pub use socket::*;
