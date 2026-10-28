//! PHP `Swoole\Coroutine\Channel` and `Swoole\Table` (with the `php` feature,
//! see docs/zend.md).
#![cfg(feature = "php")]
#![cfg_attr(
    not(test),
    deny(
        clippy::undocumented_unsafe_blocks,
        clippy::multiple_unsafe_ops_per_block
    )
)]

mod channel;
mod table;
pub use channel::*;
pub use table::*;
