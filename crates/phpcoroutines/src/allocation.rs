//! Fallible opaque metadata allocation. Native code decides its own exception.
use std::alloc::{Layout, alloc};
use std::ptr::NonNull;

pub(crate) fn try_owned<T>(value: T) -> *mut T {
    let layout = Layout::new::<T>();
    let ptr = if layout.size() == 0 {
        NonNull::<T>::dangling().as_ptr()
    } else {
        // SAFETY: `layout` is non-zero-sized here; null is handled below.
        unsafe { alloc(layout) }.cast::<T>()
    };
    if !ptr.is_null() {
        // SAFETY: a fresh, non-null allocation with `T`'s layout (or dangling for a ZST).
        unsafe { ptr.write(value) };
    }
    ptr
}
