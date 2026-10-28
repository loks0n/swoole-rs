//! Internal classes registered at MINIT, with their object handlers.
use crate::sys::{
    std_object_handlers, swr_zend_register_class, zend_class_entry, zend_function_entry,
    zend_hash_find, zend_object, zend_object_handlers, zend_string, zend_throw_error,
};
use std::{
    ffi::{CStr, c_char, c_void},
    mem::offset_of,
    ptr,
    sync::{
        OnceLock,
        atomic::{AtomicPtr, Ordering},
    },
};

/// A class entry and the object handlers its objects share: process-global,
/// written once at MINIT and read-only afterwards.
pub struct Class {
    entry: AtomicPtr<zend_class_entry>,
    handlers: OnceLock<zend_object_handlers>,
}

impl Default for Class {
    fn default() -> Self {
        Self::new()
    }
}

impl Class {
    #[must_use]
    pub const fn new() -> Self {
        Self {
            entry: AtomicPtr::new(ptr::null_mut()),
            handlers: OnceLock::new(),
        }
    }

    /// Register `name` with `methods`, then let `configure` adjust the entry and a
    /// copy of the standard handlers (Swoole's `SW_INIT_CLASS_ENTRY` followed by
    /// its `SW_SET_CLASS_*` macros).
    /// # Safety
    /// Called once, at MINIT. `methods` is a static, `PHP_FE_END`-terminated
    /// table, such as one built from a stub's generated arginfo.
    pub unsafe fn register(
        &self,
        name: &CStr,
        methods: *const zend_function_entry,
        configure: impl FnOnce(&mut zend_class_entry, &mut zend_object_handlers),
    ) {
        // SAFETY: MINIT, with a NUL-terminated name and the caller's static table.
        let entry = unsafe {
            swr_zend_register_class(name.as_ptr(), name.count_bytes(), methods, ptr::null_mut())
        };
        // SAFETY: the standard handlers are initialised before any extension's MINIT.
        let mut handlers = unsafe { std_object_handlers };
        // SAFETY: Zend returned the registered entry, which nothing else uses yet.
        configure(unsafe { &mut *entry }, &mut handlers);
        self.handlers.get_or_init(|| handlers);
        self.entry.store(entry, Ordering::Release);
    }

    /// The registered class entry (null before MINIT).
    #[must_use]
    pub fn entry(&self) -> *mut zend_class_entry {
        self.entry.load(Ordering::Acquire)
    }

    /// The handlers this class's objects use (null before MINIT).
    #[must_use]
    pub fn handlers(&self) -> *const zend_object_handlers {
        self.handlers.get().map_or(ptr::null(), ptr::from_ref)
    }
}

/// Swoole's `sw_zend_class_unset_property_deny`: declared properties of an
/// internal class cannot be unset; anything else unsets as usual.
/// # Safety
/// Installed as `unset_property`, so Zend passes a live object and member name.
pub unsafe extern "C" fn unset_property_deny(
    object: *mut zend_object,
    member: *mut zend_string,
    cache_slot: *mut *mut c_void,
) {
    // SAFETY: a live object.
    let class = unsafe { (*object).ce };
    // SAFETY: class entries live for the process.
    let mut root = unsafe { &*class };
    loop {
        // SAFETY: an internal class's union holds its parent entry.
        let parent = unsafe { root.__bindgen_anon_1.parent };
        if parent.is_null() {
            break;
        }
        // SAFETY: as above.
        root = unsafe { &*parent };
    }
    // SAFETY: a live hash table and member name.
    if !unsafe { zend_hash_find(&raw const root.properties_info, member) }.is_null() {
        // SAFETY: the class name of a live object.
        let name = unsafe { (*class).name };
        // SAFETY: a printf format whose two `%s` take the NUL-terminated member
        // and class names.
        unsafe {
            zend_throw_error(
                ptr::null_mut(),
                c"Property %s of class %s cannot be unset".as_ptr(),
                text(member),
                text(name),
            );
        }
        return;
    }
    // SAFETY: the standard handlers are initialised and immutable.
    if let Some(unset) = unsafe { std_object_handlers.unset_property } {
        // SAFETY: forwarding Zend's own arguments.
        unsafe { unset(object, member, cache_slot) };
    }
}

/// `ZSTR_VAL(Z_OBJCE_P(object)->name)`.
/// # Safety
/// `object` is live; the name lives as long as its class.
#[must_use]
pub unsafe fn class_name<'a>(object: *const zend_object) -> &'a CStr {
    // SAFETY: a live object.
    let class = unsafe { (*object).ce };
    // SAFETY: class entries live for the process.
    let name = unsafe { (*class).name };
    // SAFETY: a class name is a NUL-terminated zend_string.
    unsafe { CStr::from_ptr(text(name)) }
}

/// `ZSTR_VAL`: a `zend_string`'s NUL-terminated bytes.
fn text(string: *const zend_string) -> *const c_char {
    string
        .wrapping_byte_add(offset_of!(zend_string, val))
        .cast()
}
