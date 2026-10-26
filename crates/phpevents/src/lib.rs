//! PHP Event frontend decisions over copied scalars and immutable metadata.
//! Zend, callback/GC/bailout, registry, descriptor and reactor effects stay native.
#![cfg_attr(
    not(test),
    deny(
        clippy::undocumented_unsafe_blocks,
        clippy::multiple_unsafe_ops_per_block
    )
)]
mod admission;
mod aliases;
mod callback_slots;
mod descriptors;
mod dispatch;
mod event_loop;
mod operations;
mod query;
mod registration;
mod registry;
mod streams;
mod updates;
pub use admission::*;
pub use aliases::*;
pub use callback_slots::*;
pub use descriptors::*;
pub use dispatch::*;
pub use event_loop::*;
pub use operations::*;
pub use query::*;
pub use registration::*;
pub use registry::*;
pub use streams::*;
pub use updates::*;
