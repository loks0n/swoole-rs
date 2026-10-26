//! Column-name index. Native column objects are opaque tokens, never dereferenced.
use std::alloc::{Layout, alloc, dealloc};
use std::collections::{HashMap, hash_map::DefaultHasher};
use std::ffi::c_void;
use std::hash::BuildHasherDefault;
use std::{ptr, slice};

#[derive(Default)]
pub struct Columns {
    pub(super) entries: HashMap<Vec<u8>, ptr::NonNull<c_void>, BuildHasherDefault<DefaultHasher>>,
}
pub(super) unsafe fn name<'a>(bytes: *const u8, length: usize) -> Option<&'a [u8]> {
    if length > isize::MAX as usize || bytes.is_null() && length != 0 {
        return None;
    }
    Some(if length == 0 {
        &[]
    } else {
        // SAFETY: non-null, `length <= isize::MAX` (checked above); callers lend those bytes.
        unsafe { slice::from_raw_parts(bytes, length) }
    })
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_columns_create(output: *mut *mut Columns) -> i32 {
    if output.is_null() {
        return -1;
    }
    // SAFETY: `output` is non-null (checked above), aligned and writable.
    // SAFETY: a fresh, non-null allocation with its type's layout.
    unsafe {
        output.write(ptr::null_mut());
    }
    // SAFETY: a non-zero-sized layout; null is handled below.
    let columns = unsafe { alloc(Layout::new::<Columns>()).cast::<Columns>() };
    if columns.is_null() {
        return -1;
    }
    // SAFETY: a fresh, non-null allocation with `Columns`' layout.
    unsafe {
        columns.write(Columns {
            entries: HashMap::default(),
        })
    };
    // SAFETY: `output` is non-null (checked above), aligned and writable.
    unsafe { output.write(columns) };
    0
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_columns_insert(
    columns: *mut Columns,
    bytes: *const u8,
    length: usize,
    value: *mut c_void,
) -> i32 {
    if columns.is_null() {
        return -1;
    }
    let Some(value) = ptr::NonNull::new(value) else {
        return -1;
    };
    // SAFETY: the caller lends `length` initialized name bytes at `bytes` (null only when empty).
    let Some(name) = (unsafe { name(bytes, length) }) else {
        return -1;
    };
    // SAFETY: `columns` is non-null (checked above), aligned and exclusive per the caller contract.
    let columns = unsafe { &mut *columns };
    if columns.entries.contains_key(name) {
        return 1;
    }
    let mut owned = Vec::new();
    if owned.try_reserve_exact(name.len()).is_err() || columns.entries.try_reserve(1).is_err() {
        return -1;
    }
    owned.extend_from_slice(name);
    columns.entries.insert(owned, value);
    0
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_columns_get(
    columns: *const Columns,
    bytes: *const u8,
    length: usize,
) -> *mut c_void {
    if columns.is_null() {
        return ptr::null_mut();
    }
    // SAFETY: the caller lends `length` initialized name bytes at `bytes` (null only when empty).
    let Some(name) = (unsafe { name(bytes, length) }) else {
        return ptr::null_mut();
    };
    // SAFETY: `columns` is non-null (checked above), aligned and initialized per the caller contract.
    unsafe { &*columns }
        .entries
        .get(name)
        .map_or(ptr::null_mut(), |value| value.as_ptr())
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_columns_count(columns: *const Columns) -> usize {
    if columns.is_null() {
        return 0;
    }
    // SAFETY: `columns` is non-null (checked above), aligned and initialized per the caller contract.
    unsafe { &*columns }.entries.len()
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_columns_pop(columns: *mut Columns) -> *mut c_void {
    if columns.is_null() {
        return ptr::null_mut();
    }
    // The iterator is consumed and dropped before the token returns to native disposal.
    // SAFETY: `columns` is non-null (checked above), aligned and exclusive per the caller contract.
    unsafe { &mut *columns }
        .entries
        .extract_if(|_, _| true)
        .next()
        .map_or(ptr::null_mut(), |(_, value)| value.as_ptr())
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_columns_release(columns: *mut Columns) -> i32 {
    // SAFETY: non-null by the short-circuit; callers pass this module's live columns owner.
    if columns.is_null() || !unsafe { &*columns }.entries.is_empty() {
        return -1;
    }
    // SAFETY: the same live, empty owner, discarded once.
    unsafe { swr_v1_memory_table_columns_discard(columns) }
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_columns_discard(columns: *mut Columns) -> i32 {
    if columns.is_null() {
        return -1;
    }
    // The native column vector owns every token. Drop the borrowed name index
    // in one pass; do not invoke token destructors or rescan it via extract_if.
    // SAFETY: a live, exclusively owned `Columns` from this module's create, released once.
    unsafe { ptr::drop_in_place(columns) };
    // SAFETY: allocated with this layout by create; its value was just dropped.
    unsafe { dealloc(columns.cast(), Layout::new::<Columns>()) };
    0
}
#[cfg(test)]
#[path = "../../../tests/modules/memory/table_columns.rs"]
mod tests;
