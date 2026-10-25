#![allow(dead_code)]

// Compile the same module used by the corebase crate; its cfg(test) suite is
// shared with Cargo rather than maintained as a duplicate test implementation.
#[path = "../../../crates/corebase/src/random.rs"]
mod random;
