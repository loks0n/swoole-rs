//! TableV2's authoritative metadata and name storage. Views contain no borrowed
//! Rust pointers; native scratch allocation and Zend effects happen after return.
use crate::table::{Row, swr_v1_memory_table_clear_value, swr_v1_memory_table_column_size};
use crate::table_columns::name;
use std::alloc::{Layout, alloc, dealloc};
use std::collections::{HashMap, hash_map::DefaultHasher};
use std::hash::BuildHasherDefault;
use std::ptr;

struct Record {
    name: Vec<u8>,
    index: usize,
    width: u32,
    kind: u32,
}
#[derive(Default)]
pub struct Records {
    order: Vec<Record>,
    first: HashMap<Vec<u8>, usize, BuildHasherDefault<DefaultHasher>>,
    generation: u64,
}
#[repr(C)]
#[derive(Default, Clone, Copy, Debug, PartialEq, Eq)]
pub struct View {
    ordinal: usize,
    generation: u64,
    index: usize,
    name_length: usize,
    width: u32,
    kind: u32,
}
#[repr(C)]
#[derive(Default)]
pub struct Cursor {
    count: usize,
    unique_count: usize,
    position: usize,
    generation: u64,
}
impl Records {
    fn view(&self, ordinal: usize) -> Option<View> {
        self.order.get(ordinal).map(|record| View {
            ordinal,
            generation: self.generation,
            index: record.index,
            name_length: record.name.len(),
            width: record.width,
            kind: record.kind,
        })
    }
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_records_open(output: *mut *mut Records) -> i32 {
    if output.is_null() {
        return -1;
    }
    // SAFETY: `output` is non-null (checked above), aligned and writable per the caller contract.
    unsafe { output.write(ptr::null_mut()) };
    #[expect(
        clippy::cast_ptr_alignment,
        reason = "alloc honours Layout::new::<Records>()"
    )]
    // SAFETY: a non-zero-sized layout; null is handled below.
    let owner = unsafe { alloc(Layout::new::<Records>()).cast::<Records>() };
    if owner.is_null() {
        return -1;
    }
    // SAFETY: a fresh, non-null allocation with its type's layout.
    unsafe { owner.write(Records::default()) };
    // SAFETY: `output` is non-null (checked above), aligned and writable.
    unsafe { output.write(owner) };
    0
}
/// No native column construction, callbacks or partial logical publication.
/// Caller owns exclusive schema access; item_size is the actual core field.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_records_declare(
    owner: *mut Records,
    item_size: *mut usize,
    created: *const u8,
    bytes: *const u8,
    length: usize,
    kind: u32,
    requested: usize,
) -> i32 {
    if owner.is_null()
        || item_size.is_null()
        || created.is_null()
        || !item_size
            .addr()
            .is_multiple_of(std::mem::align_of::<usize>())
        // SAFETY: `created` is non-null (checked above), aligned and initialized per the caller contract.
        || unsafe { created.read() } != 0
    {
        return -1;
    }
    // SAFETY: `owner` is non-null (checked above), aligned and exclusive per the caller contract.
    let owner = unsafe { &mut *owner };
    if owner.generation == u64::MAX {
        return -1;
    }
    // SAFETY: the caller lends `length` initialized name bytes at `bytes` (null only when empty).
    let Some(bytes) = (unsafe { name(bytes, length) }) else {
        return -1;
    };
    if !(1..=3).contains(&kind) {
        return -2;
    }
    let mut width = 0;
    // SAFETY: `width` is a writable local.
    if unsafe { swr_v1_memory_table_column_size(kind, requested, &raw mut width) } != 0 {
        return -1;
    }
    // SAFETY: `item_size` is non-null (checked above), aligned and initialized per the caller contract.
    let index = unsafe { item_size.read() };
    let Some(next) = index
        .checked_add(width as usize)
        .filter(|&n| n <= isize::MAX as usize - 88)
    else {
        return -1;
    };
    let mut owned = Vec::new();
    if owned.try_reserve_exact(length).is_err() || owner.order.try_reserve(1).is_err() {
        return -1;
    }
    owned.extend_from_slice(bytes);
    if !owner.first.contains_key(bytes) {
        let mut key = Vec::new();
        if key.try_reserve_exact(length).is_err() || owner.first.try_reserve(1).is_err() {
            return -1;
        }
        key.extend_from_slice(bytes);
        owner.first.insert(key, owner.order.len());
    }
    owner.order.push(Record {
        name: owned,
        index,
        width,
        kind,
    });
    owner.generation += 1;
    // SAFETY: `item_size` is non-null (checked above), aligned and writable per the caller contract.
    unsafe { item_size.write(next) };
    0
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_records_get(
    owner: *const Records,
    bytes: *const u8,
    length: usize,
    output: *mut View,
) -> i32 {
    if output.is_null() {
        return -1;
    }
    // SAFETY: `output` is non-null (checked above), aligned and writable per the caller contract.
    unsafe { output.write(View::default()) };
    if owner.is_null() {
        return -1;
    }
    // SAFETY: the caller lends `length` initialized name bytes at `bytes` (null only when empty).
    let Some(bytes) = (unsafe { name(bytes, length) }) else {
        return -1;
    };
    // SAFETY: `owner` is non-null (checked above), aligned and initialized per the caller contract.
    let owner = unsafe { &*owner };
    let Some(&ordinal) = owner.first.get(bytes) else {
        return 0;
    };
    let Some(view) = owner.view(ordinal) else {
        return 0;
    };
    // SAFETY: `output` is non-null (checked above), aligned and writable per the caller contract.
    unsafe { output.write(view) };
    1
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_records_cursor_open(
    owner: *const Records,
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
    // SAFETY: `cursor` is non-null (checked above), aligned and writable.
    unsafe {
        cursor.write(Cursor {
            count: owner.order.len(),
            unique_count: owner.first.len(),
            position: 0,
            generation: owner.generation,
        });
    };
    0
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_records_cursor_next(
    owner: *const Records,
    cursor: *mut Cursor,
    output: *mut View,
) -> i32 {
    if output.is_null() {
        return -1;
    }
    // SAFETY: `output` is non-null (checked above), aligned and writable per the caller contract.
    unsafe { output.write(View::default()) };
    if owner.is_null() || cursor.is_null() {
        return -1;
    }
    // SAFETY: `owner` is non-null (checked above), aligned and initialized per the caller contract.
    let owner = unsafe { &*owner };
    // SAFETY: `cursor` is non-null (checked above), aligned and exclusive per the caller contract.
    let cursor = unsafe { &mut *cursor };
    if cursor.generation != owner.generation
        || cursor.count != owner.order.len()
        || cursor.unique_count != owner.first.len()
        || cursor.position > cursor.count
    {
        return -1;
    }
    let Some(view) = owner.view(cursor.position) else {
        return 0;
    };
    cursor.position += 1;
    // SAFETY: `output` is non-null (checked above), aligned and writable per the caller contract.
    unsafe { output.write(view) };
    1
}
/// Exact snapshot validation precedes any destination write. Caller allocates
/// and owns the scratch buffer; capacity may exceed the copied name length.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_records_copy_name(
    owner: *const Records,
    view: *const View,
    output: *mut u8,
    capacity: usize,
) -> i32 {
    if owner.is_null() || view.is_null() {
        return -1;
    }
    // SAFETY: `owner` is non-null (checked above), aligned and initialized per the caller contract.
    let owner = unsafe { &*owner };
    // SAFETY: `view` is non-null (checked above), aligned and initialized per the caller contract.
    let view = unsafe { view.read() };
    if owner.view(view.ordinal) != Some(view)
        || capacity < view.name_length
        || (output.is_null() && view.name_length != 0)
    {
        return -1;
    }
    if view.name_length != 0 {
        // SAFETY: the validated view's name has `name_length <= capacity` bytes; `output` is
        // non-null here and disjoint from the owner.
        unsafe {
            ptr::copy_nonoverlapping(
                owner.order[view.ordinal].name.as_ptr(),
                output,
                view.name_length,
            );
        };
    }
    0
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_records_clear(owner: *const Records, row: *mut Row) -> i32 {
    if owner.is_null() {
        return -1;
    }
    // SAFETY: `owner` is non-null (checked above), aligned and initialized per the caller contract.
    let owner = unsafe { &*owner };
    // Metadata can only be published through checked declaration. No native
    // metadata loads or effects are needed while Rust clears the row fields.
    for record in &owner.order {
        // SAFETY: `row` is the caller's live row; each record's span was checked at declaration.
        if unsafe { swr_v1_memory_table_clear_value(row, record.index, record.width, record.kind) }
            != 0
        {
            return -1;
        }
    }
    0
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_records_close(field: *mut *mut Records) -> i32 {
    if field.is_null() {
        return -1;
    }
    // SAFETY: `field` is non-null (checked above), aligned and initialized per the caller contract.
    let owner = unsafe { field.read() };
    if !owner.is_null() {
        // SAFETY: `field` is non-null (checked above), the caller's live slot.
        unsafe { field.write(ptr::null_mut()) };
        // SAFETY: the owner from this module's create, unpublished above, freed once.
        unsafe { ptr::drop_in_place(owner) };
        // SAFETY: allocated with this layout by create; its value was just dropped.
        unsafe { dealloc(owner.cast(), Layout::new::<Records>()) };
    }
    0
}

#[cfg(test)]
#[path = "../../../tests/modules/memory/table_records.rs"]
mod tests;
