//! Fallible opaque metadata allocation. Native code decides its own exception.
use std::alloc::{Layout, alloc};
use std::ptr::NonNull;

pub(crate) fn try_owned<T>(value: T) -> *mut T {
    let layout = Layout::new::<T>();
    let ptr = if layout.size() == 0 {
        NonNull::<T>::dangling().as_ptr()
    } else {
        unsafe { alloc(layout) }.cast::<T>()
    };
    if !ptr.is_null() {
        unsafe { ptr.write(value) };
    }
    ptr
}
