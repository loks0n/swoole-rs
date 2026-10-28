//! Objects that embed their `zend_object` after Rust data, as Swoole's C++
//! structs do (`struct { T data; zend_object std; }`).
use crate::{
    Class,
    sys::{
        object_properties_init, swr_zend_object_alloc, zend_class_entry, zend_object,
        zend_object_std_dtor, zend_object_std_init,
    },
};
use std::mem::offset_of;

/// `data` followed by the object Zend sees; `std` must stay last, since Zend
/// allocates the class's property slots after it.
#[repr(C)]
pub struct Object<T> {
    pub data: T,
    pub std: zend_object,
}

impl<T> Object<T> {
    /// Where `std` sits: the handlers' `offset`.
    pub const OFFSET: usize = offset_of!(Self, std);

    /// The body of a `create_object` handler: allocate, zero `data`, initialise
    /// the standard object and its properties, and install `class`'s handlers.
    /// # Safety
    /// `ce` is `class`'s entry or a subclass of it, `class` is registered, and
    /// all-zero bytes are a valid `T`.
    #[must_use]
    pub unsafe fn create(class: &Class, ce: *mut zend_class_entry) -> *mut zend_object {
        // SAFETY: Zend's allocator; it zeroes everything before `std`.
        let this = unsafe { swr_zend_object_alloc(size_of::<Self>(), ce) }.cast::<Self>();
        let std = Self::std(this);
        // SAFETY: `std` is freshly allocated storage for an object of class `ce`.
        unsafe { zend_object_std_init(std, ce) };
        // SAFETY: as above; the property slots follow `std`.
        unsafe { object_properties_init(std, ce) };
        // SAFETY: `std` is initialised and not yet shared.
        unsafe { (*std).handlers = class.handlers() };
        std
    }

    /// The object around `std` (`fetch_object`).
    /// # Safety
    /// `std` is the `std` of a live `Object<T>`.
    #[must_use]
    pub unsafe fn from_std(std: *mut zend_object) -> *mut Self {
        // SAFETY: `std` sits `OFFSET` bytes into its `Object<T>`.
        unsafe { std.byte_sub(Self::OFFSET) }.cast()
    }

    #[must_use]
    pub fn std(this: *mut Self) -> *mut zend_object {
        this.wrapping_byte_add(Self::OFFSET).cast()
    }

    /// The last step of a `free_obj` handler.
    /// # Safety
    /// `std` is a live object Zend is freeing.
    pub unsafe fn dtor(std: *mut zend_object) {
        // SAFETY: per the caller.
        unsafe { zend_object_std_dtor(std) };
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn std_follows_the_data_as_in_swoole_structs() {
        // `struct { sw_atomic_t *ptr; zend_object std; }`
        assert_eq!(
            Object::<*mut u32>::OFFSET,
            size_of::<*mut u32>(),
            "pointer-sized data puts std right after it"
        );
        let this = std::ptr::without_provenance_mut::<Object<u64>>(4096);
        assert_eq!(
            Object::std(this).addr() - this.addr(),
            Object::<u64>::OFFSET,
            "std() and from_std() agree on the offset"
        );
    }
}
