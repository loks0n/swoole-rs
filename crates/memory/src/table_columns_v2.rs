//! Sole ordered column-token ownership for the typed TableV2 facade.
//! Native column construction/destruction and Zend effects never enter Rust.
use crate::table::{Clear, swr_v1_memory_table_column_size};
use crate::table_columns::{Columns, name};
use std::alloc::{Layout, alloc, dealloc};
use std::ffi::c_void;
use std::{mem, ptr};

pub struct OwnedColumns {
    index: Columns,
    order: Vec<*mut c_void>,
    generation: u64,
    position: usize,
    closing: bool,
}

#[repr(C)]
#[derive(Default)]
pub struct Declaration {
    owner: *mut OwnedColumns,
    item_size: *mut usize,
    created: *const u8,
    name: *const u8,
    length: usize,
    requested: usize,
    base: usize,
    next: usize,
    column: *mut c_void,
    column_index: *mut usize,
    column_width: *const u32,
    kind: u32,
    width: u32,
    phase: u32,
}

#[repr(C)]
#[derive(Default)]
pub struct Cursor {
    count: usize,
    unique_count: usize,
    position: usize,
    generation: u64,
    column: *mut c_void,
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_columns_v2_open(output: *mut *mut OwnedColumns) -> i32 {
    if output.is_null() {
        return -1;
    }
    // SAFETY: `output` is non-null (checked above), aligned and writable per the caller contract.
    unsafe { output.write(ptr::null_mut()) };
    #[expect(
        clippy::cast_ptr_alignment,
        reason = "alloc honours Layout::new::<OwnedColumns>()"
    )]
    // SAFETY: a non-zero-sized layout; null is handled below.
    let owner = unsafe { alloc(Layout::new::<OwnedColumns>()).cast::<OwnedColumns>() };
    if owner.is_null() {
        return -1;
    }
    // SAFETY: a fresh, non-null allocation with its type's layout.
    unsafe {
        owner.write(OwnedColumns {
            index: Columns::default(),
            order: Vec::new(),
            generation: 0,
            position: 0,
            closing: false,
        })
    };
    // SAFETY: `output` is non-null (checked above), aligned and writable.
    unsafe { output.write(owner) };
    0
}

/// Reserve all storage before committing the native column's sole ownership.
/// Duplicate names retain first lookup, but every declaration has an ordered
/// owner token and advances width. Native RAII stays responsible on any failure.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_columns_v2_declare_step(cursor: *mut Declaration) -> i32 {
    if cursor.is_null() {
        return -1;
    }
    // SAFETY: `cursor` is non-null (checked above), aligned and exclusive per the caller contract.
    let state = unsafe { &mut *cursor };
    if state.phase > 1 {
        return -1;
    }
    if state.owner.is_null()
        || state.item_size.is_null()
        || state.created.is_null()
        || !state
            .item_size
            .addr()
            .is_multiple_of(mem::align_of::<usize>())
        // SAFETY: `created` is non-null (checked above) and a live native flag.
        || unsafe { state.created.read() } != 0
    {
        return -1;
    }
    // SAFETY: `state.owner` is non-null (checked above): the live owner from `v2_open`,
    // exclusive for this step.
    let owner = unsafe { &mut *state.owner };
    if owner.closing || owner.generation == u64::MAX {
        return -1;
    }
    // SAFETY: the caller lends `state.length` initialized name bytes at `state.name` (null only when empty).
    let Some(bytes) = (unsafe { name(state.name, state.length) }) else {
        return -1;
    };
    if state.phase == 0 {
        if !(1..=3).contains(&state.kind) {
            return -2;
        }
        let mut width = 0;
        // SAFETY: `width` is a writable local.
        if unsafe { swr_v1_memory_table_column_size(state.kind, state.requested, &raw mut width) }
            != 0
        {
            return -1;
        }
        // SAFETY: `item_size` is non-null and aligned (checked above), live native storage.
        let base = unsafe { state.item_size.read() };
        let Some(next) = base
            .checked_add(width as usize)
            .filter(|&n| n <= isize::MAX as usize - 88)
        else {
            return -1;
        };
        state.width = width;
        state.base = base;
        state.next = next;
        state.phase = 1;
        return 1;
    }
    // A phase1 failure is terminal; no retry after native construction.
    state.phase = 2;
    let Some(column) = ptr::NonNull::new(state.column) else {
        return -1;
    };
    if state.column_index.is_null()
        || state.column_width.is_null()
        || !state
            .column_index
            .addr()
            .is_multiple_of(mem::align_of::<usize>())
        || !state
            .column_width
            .addr()
            .is_multiple_of(mem::align_of::<u32>())
        // SAFETY: `column_width` is non-null and aligned (checked above), live native storage.
        || unsafe { state.column_width.read() } != state.width
        // SAFETY: `item_size` was checked non-null and aligned in phase 0.
        || unsafe { state.item_size.read() } != state.base
    {
        return -1;
    }
    if owner.order.try_reserve(1).is_err() {
        return -1;
    }
    if !owner.index.entries.contains_key(bytes) {
        let mut owned = Vec::new();
        if owned.try_reserve_exact(bytes.len()).is_err()
            || owner.index.entries.try_reserve(1).is_err()
        {
            return -1;
        }
        owned.extend_from_slice(bytes);
        owner.index.entries.insert(owned, column);
    }
    owner.order.push(column.as_ptr());
    owner.generation += 1;
    // SAFETY: `column_index` is non-null and aligned (checked above), live native storage.
    unsafe { state.column_index.write(state.base) };
    // SAFETY: `item_size` is non-null and aligned (checked in phase 0), live native storage.
    unsafe { state.item_size.write(state.next) };
    0
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_columns_v2_get(
    owner: *const OwnedColumns,
    bytes: *const u8,
    length: usize,
) -> *mut c_void {
    if owner.is_null() {
        return ptr::null_mut();
    }
    // SAFETY: `owner` is non-null (checked above), aligned and initialized per the caller contract.
    let owner = unsafe { &*owner };
    // SAFETY: the caller lends `length` initialized name bytes at `bytes` (null only when empty).
    let Some(bytes) = (unsafe { name(bytes, length) }) else {
        return ptr::null_mut();
    };
    if owner.closing {
        return ptr::null_mut();
    }
    owner
        .index
        .entries
        .get(bytes)
        .map_or(ptr::null_mut(), |value| value.as_ptr())
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_columns_v2_cursor_open(
    owner: *const OwnedColumns,
    cursor: *mut Cursor,
) -> i32 {
    if cursor.is_null() {
        return -1;
    }
    // SAFETY: `cursor` is non-null (checked above), aligned and writable per the caller contract.
    unsafe { cursor.write(Cursor::default()) };
    if owner.is_null() {
        return -1;
    }
    // SAFETY: `owner` is non-null (checked above), aligned and initialized per the caller contract.
    let owner = unsafe { &*owner };
    if owner.closing {
        return -1;
    }
    // SAFETY: `cursor` is non-null (checked above), aligned and writable.
    unsafe {
        cursor.write(Cursor {
            count: owner.order.len(),
            unique_count: owner.index.entries.len(),
            position: 0,
            generation: owner.generation,
            column: ptr::null_mut(),
        })
    };
    0
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_columns_v2_cursor_next(
    owner: *const OwnedColumns,
    cursor: *mut Cursor,
) -> i32 {
    if owner.is_null() || cursor.is_null() {
        return -1;
    }
    // SAFETY: `owner` is non-null (checked above), aligned and initialized per the caller contract.
    let owner = unsafe { &*owner };
    // SAFETY: `cursor` is non-null (checked above), aligned and exclusive per the caller contract.
    let state = unsafe { &mut *cursor };
    state.column = ptr::null_mut();
    if owner.closing
        || state.generation != owner.generation
        || state.count != owner.order.len()
        || state.position > state.count
    {
        return -1;
    }
    let Some(&column) = owner.order.get(state.position) else {
        return 0;
    };
    state.column = column;
    state.position += 1;
    1
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_columns_v2_clear_step(
    owner: *const OwnedColumns,
    cursor: *mut Clear,
) -> i32 {
    if owner.is_null() {
        return -1;
    }
    // SAFETY: `owner` is non-null (checked above), aligned and initialized per the caller contract.
    let owner = unsafe { &*owner };
    if owner.closing {
        return -1;
    }
    // SAFETY: forwards the caller's cursor; the order is this owner's live token list.
    unsafe { crate::table::clear_owned(cursor, &owner.order) }
}

/// Remove one token from Rust custody BEFORE requesting native deletion. Final
/// completion publishes a null owner field and frees the Rust index/vector.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_columns_v2_close_step(
    owner_field: *mut *mut OwnedColumns,
    output: *mut *mut c_void,
) -> i32 {
    if owner_field.is_null() || output.is_null() {
        return -1;
    }
    // SAFETY: `output` is non-null (checked above), aligned and writable per the caller contract.
    unsafe { output.write(ptr::null_mut()) };
    // SAFETY: `owner_field` is non-null (checked above), aligned and initialized per the caller contract.
    let owner = unsafe { owner_field.read() };
    if owner.is_null() {
        return 0;
    }
    // SAFETY: `owner` is non-null (checked above), aligned and exclusive per the caller contract.
    let state = unsafe { &mut *owner };
    if !state.closing {
        state.closing = true;
        state.index.entries.clear();
    }
    if let Some(token) = state.order.get_mut(state.position) {
        let column = mem::replace(token, ptr::null_mut());
        state.position += 1;
        // SAFETY: `output` is non-null (checked above), aligned and writable per the caller contract.
        unsafe { output.write(column) };
        return 1;
    }
    // SAFETY: the owner field is the caller's live, exclusive slot.
    unsafe { owner_field.write(ptr::null_mut()) };
    // SAFETY: the owner from `v2_open`, now unpublished and fully drained, freed once.
    unsafe { ptr::drop_in_place(owner) };
    // SAFETY: allocated with this layout by `v2_open`; its value was just dropped.
    unsafe { dealloc(owner.cast(), Layout::new::<OwnedColumns>()) };
    0
}

#[cfg(test)]
#[path = "../../../tests/modules/memory/table_columns_v2.rs"]
mod tests;
