//! PHP `Swoole\Http\Request` and `Swoole\Http\Response`: class registration,
//! objects and every method. C++ keeps the method tables built from the stubs'
//! arginfo and, until it moves to Rust, the `swoole::http::Context` the objects
//! point at; `host` declares what the methods ask of it. See docs/zend.md.
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

mod context;
mod host;
mod request;
mod response;

pub use context::{swr_v1_phphttp_context, swr_v1_phphttp_set_context};
pub use request::*;
pub use response::*;
