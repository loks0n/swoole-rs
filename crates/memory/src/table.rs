//! Shared-table row storage and collision policy. Hash callbacks and locks are native.
use std::ffi::c_void;
use std::sync::atomic::{AtomicI64, AtomicU32, AtomicUsize, Ordering};
use std::{mem, ptr, slice};

#[repr(C)]
pub struct Row {
    lock: u32,
    lock_pid: i32,
    active: u8,
    key_len: u8,
    next: *mut Row,
    key: [u8; 64],
}
#[repr(C)]
#[derive(Default, Clone, Copy)]
pub struct Plan {
    row: *mut c_void,
    parent: *mut c_void,
    level: u32,
    flags: u32,
    initialize: u32,
}
#[repr(C)]
#[derive(Default, Clone, Copy, PartialEq, Eq)]
pub struct Layout {
    total: usize,
    row_size: usize,
    pool_offset: usize,
    pool_size: usize,
    rows: u32,
}
unsafe fn next(row: *mut Row) -> *mut Row {
    unsafe { ptr::addr_of!((*row).next).read_unaligned() }
}
unsafe fn active(row: *mut Row) -> bool {
    unsafe { ptr::addr_of!((*row).active).read_unaligned() != 0 }
}
unsafe fn matches(row: *mut Row, key: &[u8]) -> bool {
    let length = unsafe { ptr::addr_of!((*row).key_len).read_unaligned() } as usize;
    if length != key.len() {
        return false;
    }
    let stored = unsafe { ptr::addr_of!((*row).key).cast::<u8>() };
    // Compare fixed-width endpoints for short keys. They can overlap each
    // other, but neither load extends beyond either borrowed key span.
    unsafe fn endpoints<T: Copy + Eq>(left: *const u8, right: *const u8, length: usize) -> bool {
        let end = length - mem::size_of::<T>();
        unsafe {
            (left.cast::<T>().read_unaligned() == right.cast::<T>().read_unaligned())
                & (left.add(end).cast::<T>().read_unaligned()
                    == right.add(end).cast::<T>().read_unaligned())
        }
    }
    unsafe {
        match length {
            0 => true,
            1 => stored.read() == key.as_ptr().read(),
            2..=3 => endpoints::<u16>(stored, key.as_ptr(), length),
            4..=7 => endpoints::<u32>(stored, key.as_ptr(), length),
            8..=16 => endpoints::<u64>(stored, key.as_ptr(), length),
            _ => slice::from_raw_parts(stored, length) == key,
        }
    }
}
unsafe fn key<'a>(bytes: *const u8, length: u16) -> Option<&'a [u8]> {
    if length > 63 || bytes.is_null() && length != 0 {
        return None;
    }
    Some(if length == 0 {
        &[]
    } else {
        unsafe { slice::from_raw_parts(bytes, length as usize) }
    })
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_config(
    requested: u32,
    proportion: f32,
    rows: *mut u32,
    conflict: *mut f32,
) -> i32 {
    if rows.is_null() || conflict.is_null() {
        return -1;
    }
    unsafe {
        rows.write(0);
        conflict.write(0.0);
    }
    if !proportion.is_finite() {
        return -1;
    }
    let count = if requested >= 0x8000_0000 {
        0x8000_0000
    } else {
        requested.max(64).next_power_of_two()
    };
    unsafe {
        rows.write(count);
        conflict.write(proportion.clamp(0.2, 1.0));
    }
    0
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_layout(
    rows: u32,
    item: usize,
    conflict: f32,
    output: *mut Layout,
) -> i32 {
    if output.is_null() {
        return -1;
    }
    unsafe {
        output.write(Layout::default());
    }
    if rows < 64 || !rows.is_power_of_two() || !(0.2..=1.0).contains(&conflict) {
        return -1;
    }
    let all_rows = (rows as f32 * (1.0 + conflict)) as usize;
    let Some(row_size) = mem::size_of::<Row>().checked_add(item) else {
        return -1;
    };
    let Some(base) = (rows as usize).checked_mul(mem::size_of::<*mut Row>()) else {
        return -1;
    };
    let Some(pool_offset) = row_size
        .checked_mul(rows as usize)
        .and_then(|n| base.checked_add(n))
    else {
        return -1;
    };
    let Some(pool_size) = row_size
        .checked_add(mem::size_of::<crate::fixed::Slice>())
        .and_then(|n| n.checked_mul(all_rows - rows as usize))
        .and_then(|n| n.checked_add(mem::size_of::<crate::fixed::Fixed>()))
    else {
        return -1;
    };
    let Some(total) = pool_offset
        .checked_add(pool_size)
        .filter(|&n| n <= isize::MAX as usize)
    else {
        return -1;
    };
    unsafe {
        output.write(Layout {
            total,
            row_size,
            pool_offset,
            pool_size,
            rows,
        });
    }
    0
}
/// Physical storage plan for naturally aligned native row objects. The frozen
/// layout function continues to report its exact original logical byte counts.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_storage_layout(
    rows: u32,
    item: usize,
    conflict: f32,
    output: *mut Layout,
) -> i32 {
    if output.is_null() {
        return -1;
    }
    unsafe {
        output.write(Layout::default());
    }
    let Some(stride) = mem::size_of::<Row>()
        .checked_add(item)
        .and_then(|n| n.checked_add(mem::align_of::<Row>() - 1))
        .map(|n| n & !(mem::align_of::<Row>() - 1))
    else {
        return -1;
    };
    unsafe { swr_v1_memory_table_layout(rows, stride - mem::size_of::<Row>(), conflict, output) }
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_arena(
    memory: *mut c_void,
    layout: *const Layout,
) -> i32 {
    if memory.is_null() || layout.is_null() || !memory.addr().is_multiple_of(8) {
        return -1;
    }
    let l = unsafe { &*layout };
    let expected = (l.rows as usize)
        .checked_mul(mem::size_of::<*mut Row>())
        .and_then(|base| {
            (l.rows as usize)
                .checked_mul(l.row_size)
                .and_then(|n| base.checked_add(n))
        });
    if l.rows < 64
        || !l.rows.is_power_of_two()
        || l.row_size < mem::size_of::<Row>()
        || expected != Some(l.pool_offset)
        || l.total > isize::MAX as usize
        || l.pool_offset.checked_add(l.pool_size) != Some(l.total)
    {
        return -1;
    }
    let table = memory.cast::<*mut Row>();
    let base = unsafe {
        memory
            .cast::<u8>()
            .add(l.rows as usize * mem::size_of::<*mut Row>())
    };
    for i in 0..l.rows as usize {
        let row = unsafe { base.add(i * l.row_size).cast::<Row>() };
        unsafe {
            table.add(i).write(row);
            ptr::write_bytes(row.cast::<u8>(), 0, mem::size_of::<Row>());
        }
    }
    0
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_clear(row: *mut Row, keep_lock: u32) -> i32 {
    if row.is_null() || keep_lock > 1 {
        return -1;
    }
    let begin = if keep_lock == 1 {
        mem::offset_of!(Row, lock_pid)
    } else {
        0
    };
    unsafe {
        ptr::write_bytes(
            row.cast::<u8>().add(begin),
            0,
            mem::size_of::<Row>() - begin,
        );
    }
    0
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_init(
    row: *mut Row,
    bytes: *const u8,
    length: u16,
) -> i32 {
    if row.is_null() {
        return -1;
    }
    let Some(key) = (unsafe { key(bytes, length) }) else {
        return -1;
    };
    unsafe {
        let begin = mem::offset_of!(Row, active);
        ptr::write_bytes(
            row.cast::<u8>().add(begin),
            0,
            mem::size_of::<Row>() - begin,
        );
        if !key.is_empty() {
            ptr::copy_nonoverlapping(
                key.as_ptr(),
                ptr::addr_of_mut!((*row).key).cast(),
                key.len(),
            );
        }
        ptr::addr_of_mut!((*row).key_len).write_unaligned(length as u8);
        ptr::addr_of_mut!((*row).active).write_unaligned(1);
    }
    0
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_get(
    root: *mut Row,
    bytes: *const u8,
    length: u16,
) -> *mut Row {
    let Some(key) = (unsafe { key(bytes, length) }) else {
        return ptr::null_mut();
    };
    let mut row = root;
    while !row.is_null() {
        if unsafe { matches(row, key) } {
            return if unsafe { active(row) } {
                row
            } else {
                ptr::null_mut()
            };
        }
        row = unsafe { next(row) };
    }
    ptr::null_mut()
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_set_plan(
    root: *mut Row,
    bytes: *const u8,
    length: u16,
    output: *mut Plan,
) -> i32 {
    if output.is_null() {
        return -1;
    }
    unsafe {
        output.write(Plan::default());
    }
    if root.is_null() {
        return -1;
    }
    let Some(key) = (unsafe { key(bytes, length) }) else {
        return -1;
    };
    if !unsafe { active(root) } {
        unsafe {
            output.write(Plan {
                row: root.cast(),
                flags: 1,
                initialize: 1,
                ..Plan::default()
            });
        }
        return 0;
    }
    let (mut row, mut flags, mut level) = (root, 0, 1u32);
    loop {
        if unsafe { matches(row, key) } {
            unsafe {
                output.write(Plan {
                    row: row.cast(),
                    flags,
                    level,
                    ..Plan::default()
                });
            }
            return 0;
        }
        let following = unsafe { next(row) };
        if following.is_null() {
            unsafe {
                output.write(Plan {
                    parent: row.cast(),
                    level,
                    flags: flags | 1,
                    initialize: 1,
                    ..Plan::default()
                });
            }
            return 1;
        }
        row = following;
        flags |= 2;
        let Some(next_level) = level.checked_add(1) else {
            return -1;
        };
        level = next_level;
    }
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_delete(
    root: *mut Row,
    bytes: *const u8,
    length: u16,
    item_size: usize,
    removed: *mut *mut c_void,
) -> i32 {
    if removed.is_null() {
        return -1;
    }
    unsafe {
        removed.write(ptr::null_mut());
    }
    if root.is_null() || item_size > isize::MAX as usize - mem::size_of::<Row>() {
        return -1;
    }
    let Some(key) = (unsafe { key(bytes, length) }) else {
        return -1;
    };
    let (mut row, mut previous) = (root, ptr::null_mut::<Row>());
    while !row.is_null() && !unsafe { matches(row, key) } {
        previous = row;
        row = unsafe { next(row) };
    }
    if row.is_null() {
        return 1;
    }
    if row == root {
        let replacement = unsafe { next(root) };
        if replacement.is_null() {
            return unsafe { swr_v1_memory_table_clear(root, 1) };
        }
        unsafe {
            let length = ptr::addr_of!((*replacement).key_len).read_unaligned() as usize;
            if length > 63 {
                return -1;
            }
            ptr::addr_of_mut!((*root).next).write_unaligned(next(replacement));
            ptr::copy_nonoverlapping(
                ptr::addr_of!((*replacement).key).cast::<u8>(),
                ptr::addr_of_mut!((*root).key).cast::<u8>(),
                length + 1,
            );
            ptr::addr_of_mut!((*root).key_len).write_unaligned(length as u8);
            if item_size != 0 {
                ptr::copy_nonoverlapping(
                    replacement.cast::<u8>().add(mem::size_of::<Row>()),
                    root.cast::<u8>().add(mem::size_of::<Row>()),
                    item_size,
                );
            }
            removed.write(replacement.cast());
        }
    } else {
        unsafe {
            ptr::addr_of_mut!((*previous).next).write_unaligned(next(row));
            removed.write(row.cast());
        }
    }
    0
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_next(
    root: *mut Row,
    index: u32,
    current: *mut Row,
    row_size: usize,
    next_index: *mut u32,
    advance: *mut u32,
) -> i32 {
    if next_index.is_null() || advance.is_null() {
        return -1;
    }
    unsafe {
        next_index.write(0);
        advance.write(0);
    }
    if root.is_null()
        || current.is_null()
        || row_size < mem::size_of::<Row>()
        || row_size > isize::MAX as usize
    {
        return -1;
    }
    let mut row = root;
    if unsafe { next(root) }.is_null() {
        unsafe {
            advance.write(1);
            next_index.write(index);
        }
    } else {
        for _ in 0..index {
            row = unsafe { next(row) };
            if row.is_null() {
                return 1;
            }
        }
        let Some(following) = index.checked_add(1) else {
            return -1;
        };
        unsafe {
            next_index.write(following);
        }
    }
    unsafe {
        ptr::copy_nonoverlapping(row.cast::<u8>(), current.cast::<u8>(), row_size);
    }
    0
}
/// Typed addresses of the actual native counters, never a native class borrow.
#[repr(C)]
#[derive(Default, Clone, Copy)]
pub struct CounterFields {
    rows: *mut u32,
    inserted: *mut i64,
    deleted: *mut i64,
    updated: *mut i64,
    conflicts: *mut usize,
    max_conflict: *mut u32,
}
impl CounterFields {
    fn valid(&self) -> bool {
        fn aligned<T, A>(p: *mut T) -> bool {
            !p.is_null() && p.addr().is_multiple_of(mem::align_of::<A>())
        }
        aligned::<_, AtomicU32>(self.rows)
            && aligned::<_, AtomicI64>(self.inserted)
            && aligned::<_, AtomicI64>(self.deleted)
            && aligned::<_, AtomicI64>(self.updated)
            && aligned::<_, AtomicUsize>(self.conflicts)
            && aligned::<_, AtomicU32>(self.max_conflict)
    }
    unsafe fn deleted(&self) {
        unsafe {
            AtomicI64::from_ptr(self.deleted).fetch_add(1, Ordering::SeqCst);
            AtomicU32::from_ptr(self.rows).fetch_sub(1, Ordering::SeqCst);
        }
    }
}
/// Independent native stack state. Only raw tokens survive native effect steps.
#[repr(C)]
#[derive(Default)]
pub struct Mutation {
    counters: CounterFields,
    root: *mut Row,
    row: *mut Row,
    removed: *mut Row,
    key: *const u8,
    out_flags: *mut i32,
    item_size: usize,
    plan: Plan,
    mode: u32,
    phase: u32,
    key_length: u16,
}
unsafe fn finish_set(m: &mut Mutation) -> i32 {
    if m.row.is_null() || m.plan.initialize > 1 || m.plan.flags & !3 != 0 {
        return -1;
    }
    unsafe {
        if m.plan.initialize != 0 {
            if swr_v1_memory_table_init(m.row, m.key, m.key_length) != 0 {
                return -1;
            }
            AtomicU32::from_ptr(m.counters.rows).fetch_add(1, Ordering::SeqCst);
        }
        if !m.plan.parent.is_null() {
            ptr::addr_of_mut!((*m.plan.parent.cast::<Row>()).next).write_unaligned(m.row);
        }
        if !m.out_flags.is_null() {
            m.out_flags.write(m.plan.flags as i32);
        }
        let counter = if m.plan.flags & 1 != 0 {
            m.counters.inserted
        } else {
            m.counters.updated
        };
        AtomicI64::from_ptr(counter).fetch_add(1, Ordering::SeqCst);
    }
    m.phase = 2;
    0
}
/// mode0 set, mode1 delete. Return1 requests the mode-specific native pool
/// allocate/free effect; resume the unchanged phase1 state after that effect.
/// Return0 success,2 missing delete,-1 invalid. No native callback enters Rust.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_mutation_step(state: *mut Mutation) -> i32 {
    if state.is_null() {
        return -1;
    }
    let m = unsafe { &mut *state };
    if m.mode > 1
        || m.phase > 1
        || m.root.is_null()
        || !m.counters.valid()
        || m.mode == 0 && !m.out_flags.is_null() && !m.out_flags.is_aligned()
    {
        return -1;
    }
    // Delete resume acknowledges an already completed native release. Its key
    // token may name that released storage and must never become a Rust borrow.
    if (m.phase == 0 || m.mode == 0) && unsafe { key(m.key, m.key_length) }.is_none() {
        return -1;
    }
    match (m.mode, m.phase) {
        (0, 0) => {
            let status =
                unsafe { swr_v1_memory_table_set_plan(m.root, m.key, m.key_length, &mut m.plan) };
            m.row = m.plan.row.cast();
            if status < 0 {
                return -1;
            }
            if status == 1 {
                unsafe {
                    AtomicUsize::from_ptr(m.counters.conflicts).fetch_add(1, Ordering::SeqCst);
                    AtomicU32::from_ptr(m.counters.max_conflict)
                        .fetch_max(m.plan.level, Ordering::SeqCst);
                }
                m.phase = 1;
                1
            } else {
                unsafe { finish_set(m) }
            }
        }
        (0, 1) => unsafe { finish_set(m) },
        (1, 0) => {
            let mut removed = ptr::null_mut();
            let status = unsafe {
                swr_v1_memory_table_delete(m.root, m.key, m.key_length, m.item_size, &mut removed)
            };
            m.removed = removed.cast();
            if status < 0 {
                return -1;
            }
            if status == 1 {
                m.phase = 2;
                return 2;
            }
            if !m.removed.is_null() {
                m.phase = 1;
                return 1;
            }
            unsafe {
                m.counters.deleted();
            }
            m.phase = 2;
            0
        }
        (1, 1) => {
            if m.removed.is_null() {
                return -1;
            }
            unsafe {
                m.counters.deleted();
            }
            m.phase = 2;
            0
        }
        _ => -1,
    }
}

/// Independent live scalar-field view; the native iterator/row mutexes never cross.
#[repr(C)]
pub struct IteratorFields {
    absolute: *mut u32,
    collision: *mut u32,
    current: *mut Row,
    row_size: usize,
}
impl IteratorFields {
    fn valid(&self) -> bool {
        !self.absolute.is_null()
            && self.absolute.is_aligned()
            && !self.collision.is_null()
            && self.collision.is_aligned()
            && !self.current.is_null()
            && self.row_size >= mem::size_of::<Row>()
            && self.row_size <= isize::MAX as usize
    }
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_iterator_reset(fields: *const IteratorFields) -> i32 {
    if fields.is_null() {
        return -1;
    }
    let f = unsafe { &*fields };
    if !f.valid() {
        return -1;
    }
    unsafe {
        f.absolute.write(0);
        f.collision.write(0);
        ptr::write_bytes(f.current.cast::<u8>(), 0, f.row_size);
    }
    0
}
/// phase0 starts selection; phase1 consumes one native lookup/lock observation.
/// Return1 requests lookup/locking of output bucket,0 completes,-1 rejects.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_iterator_step(
    fields: *const IteratorFields,
    buckets: usize,
    root: *mut Row,
    phase: u32,
    lookup: *mut u32,
) -> i32 {
    if fields.is_null() || lookup.is_null() {
        return -1;
    }
    unsafe {
        lookup.write(0);
    }
    let f = unsafe { &*fields };
    if !f.valid() || phase > 1 || buckets > u32::MAX as usize || phase == 0 && !root.is_null() {
        return -1;
    }
    let mut absolute = unsafe { f.absolute.read() };
    if phase == 1 && (absolute as usize) < buckets {
        if !root.is_null() {
            let mut collision = 0;
            let mut advance = 0;
            let result = unsafe {
                swr_v1_memory_table_next(
                    root,
                    f.collision.read(),
                    f.current,
                    f.row_size,
                    &mut collision,
                    &mut advance,
                )
            };
            if result < 0 {
                return -1;
            }
            unsafe {
                f.collision.write(collision);
            }
            if result == 0 {
                unsafe {
                    f.absolute.write(absolute + advance);
                }
                return 0;
            }
        }
        absolute += 1;
        unsafe {
            f.absolute.write(absolute);
        }
    }
    if (absolute as usize) < buckets {
        unsafe {
            lookup.write(absolute);
        }
        1
    } else {
        unsafe { swr_v1_memory_table_clear(f.current, 0) }
    }
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_column_size(
    kind: u32,
    requested: usize,
    output: *mut u32,
) -> i32 {
    if output.is_null() {
        return -1;
    }
    unsafe {
        output.write(0);
    }
    let size = match kind {
        1 | 2 => 8,
        3 => match requested.checked_add(4).and_then(|n| u32::try_from(n).ok()) {
            Some(n) => n,
            None => return -1,
        },
        _ => return -1,
    };
    unsafe {
        output.write(size);
    }
    0
}
/// Independent native descriptor snapshot, never a C++ TableColumn layout.
#[repr(C)]
#[derive(Default, Clone, Copy)]
pub struct Column {
    index: usize,
    width: u32,
    kind: u32,
}

/// Independent cursor: pointer tokens select live native descriptor facts, never
/// borrow the C++ column/vector objects. Native fills only the requested batch.
#[repr(C)]
#[derive(Default)]
pub struct Clear {
    row: *mut Row,
    columns: *const *mut c_void,
    count: usize,
    position: usize,
    item_size: usize,
    tokens: [*mut c_void; 8],
    batch: [Column; 8],
    take: u32,
    phase: u32,
}

/// 1 requests native field copies; 0 completes; -1 rejects. Each completed
/// batch is committed before requesting the next: failure is not transactional
/// across batches. No Rust borrow survives native descriptor marshalling.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_clear_step(cursor: *mut Clear) -> i32 {
    if cursor.is_null() {
        return -1;
    }
    let state = unsafe { &mut *cursor };
    if state.phase == 2 {
        return 0;
    }
    if state.phase > 1
        || state.position > state.count
        || state.count > isize::MAX as usize / mem::size_of::<*mut c_void>()
        || state.columns.is_null() && state.count != 0
        || state.item_size > isize::MAX as usize - mem::size_of::<Row>()
    {
        return -1;
    }
    if state.phase == 1 {
        if state.take == 0
            || state.take > 8
            || state.take as usize > state.count - state.position
            || unsafe {
                swr_v1_memory_table_clear_columns(
                    state.row,
                    state.batch.as_ptr(),
                    state.take as usize,
                    state.item_size,
                )
            } != 0
        {
            state.phase = 3;
            return -1;
        }
        state.position += state.take as usize;
    }
    state.take = (state.count - state.position).min(8) as u32;
    if state.take == 0 {
        state.phase = 2;
        return 0;
    }
    if state.row.is_null() {
        state.phase = 3;
        return -1;
    }
    for i in 0..state.take as usize {
        let token = unsafe { state.columns.add(state.position + i).read() };
        if token.is_null() {
            state.phase = 3;
            return -1;
        }
        state.tokens[i] = token;
    }
    state.phase = 1;
    1
}

/// Use the sole Rust token store during this call only. Neither the vector
/// representation nor a raw pointer into it is retained across native effects.
pub(super) unsafe fn clear_owned(cursor: *mut Clear, tokens: &[*mut c_void]) -> i32 {
    if cursor.is_null() {
        return -1;
    }
    unsafe {
        (*cursor).columns = tokens.as_ptr();
        (*cursor).count = tokens.len();
    }
    let status = unsafe { swr_v1_memory_table_clear_step(cursor) };
    unsafe {
        (*cursor).columns = ptr::null();
    }
    status
}

/// Validate a whole borrowed batch before clearing scalar/string-length bytes.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_clear_columns(
    row: *mut Row,
    columns: *const Column,
    count: usize,
    item_size: usize,
) -> i32 {
    if row.is_null()
        || columns.is_null() && count != 0
        || count > isize::MAX as usize / mem::size_of::<Column>()
        || item_size > isize::MAX as usize - mem::size_of::<Row>()
    {
        return -1;
    }
    let columns = if count == 0 {
        &[]
    } else {
        unsafe { slice::from_raw_parts(columns, count) }
    };
    for column in columns {
        if !matches!((column.kind, column.width), (1 | 2, 8) | (3, 4..))
            || column
                .index
                .checked_add(column.width as usize)
                .is_none_or(|end| end > item_size)
        {
            return -1;
        }
    }
    let data = unsafe { row.cast::<u8>().add(mem::size_of::<Row>()) };
    let (mut begin, mut end) = (0, 0);
    for column in columns {
        let bytes = if column.kind == 3 { 4 } else { 8 };
        if column.index == end {
            end += bytes;
        } else {
            if end != begin {
                unsafe { ptr::write_bytes(data.add(begin), 0, end - begin) };
            }
            begin = column.index;
            end = begin + bytes;
        }
    }
    if end != begin {
        unsafe { ptr::write_bytes(data.add(begin), 0, end - begin) };
    }
    0
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_clear_value(
    row: *mut Row,
    index: usize,
    width: u32,
    kind: u32,
) -> i32 {
    let bytes = match (kind, width) {
        (1 | 2, 8) => 8,
        (3, 4..) => 4, // Empty strings retain their payload, clearing only length.
        _ => return -1,
    };
    let end = mem::size_of::<Row>()
        .checked_add(index)
        .and_then(|offset| offset.checked_add(width as usize));
    if row.is_null() || end.is_none_or(|end| end > isize::MAX as usize) {
        return -1;
    }
    // Native Unix long zero and IEEE double positive zero both have zero bits.
    unsafe {
        ptr::write_bytes(
            row.cast::<u8>().add(mem::size_of::<Row>() + index),
            0,
            bytes,
        )
    };
    0
}
/// Native warning is an effect boundary, not a Rust callback. Ordinary writes
/// complete in one call; overlong strings return before any destination write.
#[repr(C)]
#[derive(Default)]
pub struct Value {
    row: *mut Row,
    value: *const c_void,
    length: usize,
    index: usize,
    width: u32,
    kind: u32,
    phase: u32,
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_value_step(cursor: *mut Value) -> i32 {
    if cursor.is_null() {
        return -1;
    }
    let state = unsafe { &mut *cursor };
    if state.phase > 1 {
        return -1;
    }
    if state.phase == 0
        && state.kind == 3
        && state.width >= 4
        && state.length > state.width as usize - 4
    {
        state.phase = 1;
        return 1;
    }
    state.phase = 2;
    unsafe {
        swr_v1_memory_table_set_value(
            state.row,
            state.index,
            state.width,
            state.kind,
            state.value,
            state.length,
        )
    }
}

/// Independent tokens only. Native destructors/free execute after each return;
/// after the final effect, only this cursor is read, not the released storage.
#[repr(C)]
#[derive(Default)]
pub struct IteratorRelease {
    current: *mut c_void,
    mutex: *mut c_void,
    phase: u32,
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_iterator_release_step(
    cursor: *mut IteratorRelease,
    output: *mut TeardownEffect,
) -> i32 {
    if cursor.is_null() || output.is_null() {
        return -1;
    }
    unsafe { output.write(TeardownEffect::default()) };
    let state = unsafe { &mut *cursor };
    loop {
        let effect = match state.phase {
            0 => {
                state.phase = 1;
                if state.current.is_null() {
                    continue;
                }
                TeardownEffect {
                    token: state.current,
                    action: 1,
                }
            }
            1 => {
                state.phase = 2;
                TeardownEffect {
                    token: state.mutex,
                    action: 2,
                }
            }
            2 => return 0,
            _ => return -1,
        };
        unsafe { output.write(effect) };
        return 1;
    }
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_set_value(
    row: *mut Row,
    index: usize,
    width: u32,
    kind: u32,
    value: *const c_void,
    length: usize,
) -> i32 {
    if row.is_null() || index > isize::MAX as usize - mem::size_of::<Row>() - width as usize {
        return -1;
    }
    let data = unsafe { row.cast::<u8>().add(mem::size_of::<Row>() + index) };
    match kind {
        1 | 2 if width == 8 && !value.is_null() => unsafe {
            ptr::copy_nonoverlapping(value.cast::<u8>(), data, 8);
        },
        3 if width >= 4 => {
            let length = if value.is_null() {
                0
            } else {
                length.min(width as usize - 4)
            };
            unsafe {
                data.cast::<u32>().write_unaligned(length as u32);
                if length != 0 {
                    ptr::copy_nonoverlapping(value.cast::<u8>(), data.add(4), length);
                }
            }
        }
        _ => return -1,
    }
    0
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_get_number(
    row: *const Row,
    index: usize,
    output: *mut c_void,
) -> i32 {
    if row.is_null() || output.is_null() || index > isize::MAX as usize - mem::size_of::<Row>() - 8
    {
        return -1;
    }
    unsafe {
        ptr::copy_nonoverlapping(
            row.cast::<u8>().add(mem::size_of::<Row>() + index),
            output.cast::<u8>(),
            8,
        );
    }
    0
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_get_string(
    row: *const Row,
    index: usize,
    width: u32,
    output: *mut *mut u8,
    length: *mut u32,
) -> i32 {
    if output.is_null() || length.is_null() {
        return -1;
    }
    unsafe {
        output.write(ptr::null_mut());
        length.write(0);
    }
    if row.is_null()
        || width < 4
        || index > isize::MAX as usize - mem::size_of::<Row>() - width as usize
    {
        return -1;
    }
    let data = unsafe { row.cast::<u8>().add(mem::size_of::<Row>() + index) };
    let count = unsafe { data.cast::<u32>().read_unaligned() };
    if count > width - 4 {
        return -1;
    }
    unsafe {
        output.write(data.add(4).cast_mut());
        length.write(count);
    }
    0
}

/// Key normalization and bucket policy around a native hash callback. Only the
/// pointer-token array is borrowed; no row/class/lock or callback enters Rust.
#[repr(C)]
#[derive(Default)]
pub struct Lookup {
    rows: *const *mut Row,
    count: usize,
    mask: usize,
    hash: u64,
    index: usize,
    row: *mut Row,
    length: u16,
    phase: u32,
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_lookup_step(cursor: *mut Lookup) -> i32 {
    if cursor.is_null() {
        return -1;
    }
    let state = unsafe { &mut *cursor };
    if state.phase > 1
        || state.rows.is_null()
        || state.count == 0
        || state.count > isize::MAX as usize / mem::size_of::<*mut Row>()
        || !state
            .rows
            .addr()
            .is_multiple_of(mem::align_of::<*mut Row>())
    {
        return -1;
    }
    if state.phase == 0 {
        state.length = state.length.min(63);
        state.phase = 1;
        return 1;
    }
    state.index = state.hash as usize & state.mask;
    if state.index >= state.count {
        return -1;
    }
    state.row = unsafe { state.rows.add(state.index).read() };
    state.phase = 2;
    0
}

/// Independent declaration cursor, borrowed name and actual scalar field views.
#[repr(C)]
#[derive(Default)]
pub struct Declaration {
    index: *mut crate::table_columns::Columns,
    item_size: *mut usize,
    name: *const u8,
    length: usize,
    requested: usize,
    base: usize,
    next: usize,
    column: *mut c_void,
    column_index: *mut usize,
    column_width: *mut u32,
    kind: u32,
    width: u32,
    phase: u32,
}
///0 commits,1 requests native column construction,2 vector append,3 rollback
/// append; -2 is unknown type (native warning),-1 other invalid/pre-effect error.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_declaration_step(cursor: *mut Declaration) -> i32 {
    if cursor.is_null() {
        return -1;
    }
    let state = unsafe { &mut *cursor };
    let rollback = if state.phase == 2 { 3 } else { -1 };
    if state.phase > 2
        || state.index.is_null()
        || state.item_size.is_null()
        || !state
            .item_size
            .addr()
            .is_multiple_of(mem::align_of::<usize>())
        || state.length > isize::MAX as usize
        || state.name.is_null() && state.length != 0
    {
        if rollback == 3 {
            state.phase = 3;
        }
        return rollback;
    }
    if state.phase == 0 {
        if !(1..=3).contains(&state.kind) {
            return -2;
        }
        let mut width = 0;
        if unsafe { swr_v1_memory_table_column_size(state.kind, state.requested, &mut width) } != 0
        {
            return -1;
        }
        let base = unsafe { state.item_size.read() };
        let Some(next) = base.checked_add(width as usize) else {
            return -1;
        };
        state.base = base;
        state.next = next;
        state.width = width;
        state.phase = 1;
        return 1;
    }
    if state.column.is_null()
        || state.column_index.is_null()
        || state.column_width.is_null()
        || !state
            .column_index
            .addr()
            .is_multiple_of(mem::align_of::<usize>())
        || !state
            .column_width
            .addr()
            .is_multiple_of(mem::align_of::<u32>())
        || unsafe { state.column_width.read() } != state.width
        || unsafe { state.item_size.read() } != state.base
    {
        if rollback == 3 {
            state.phase = 3;
        }
        return rollback;
    }
    if state.phase == 1 {
        unsafe { state.column_index.write(state.base) };
        state.phase = 2;
        return 2;
    }
    // The native append has completed; any insertion failure requests matching
    // rollback before its RAII owner destroys the still-unpublished column.
    let status = unsafe {
        crate::table_columns::swr_v1_memory_table_columns_insert(
            state.index,
            state.name,
            state.length,
            state.column,
        )
    };
    state.phase = 3;
    if status < 0 {
        return 3;
    }
    unsafe { state.item_size.write(state.next) };
    0
}

/// Typed addresses of actual metadata fields; no C++ class is borrowed.
#[repr(C)]
pub struct MetadataFields {
    size: *mut usize,
    mask: *mut usize,
    item_size: *mut usize,
    memory_size: *mut usize,
    conflict: *mut f32,
    created: *mut u8,
    rows: *mut *mut *mut Row,
    pool: *mut *mut c_void,
    iterator: *mut *mut c_void,
    memory: *mut *mut c_void,
    counters: CounterFields,
}
impl MetadataFields {
    fn valid(&self) -> bool {
        fn aligned<T>(p: *mut T) -> bool {
            !p.is_null() && p.addr().is_multiple_of(mem::align_of::<T>())
        }
        aligned(self.size)
            && aligned(self.mask)
            && aligned(self.item_size)
            && aligned(self.memory_size)
            && aligned(self.conflict)
            && aligned(self.created)
            && aligned(self.rows)
            && aligned(self.pool)
            && aligned(self.iterator)
            && aligned(self.memory)
            && self.counters.valid()
    }
}
/// Fresh unpublished field targets; validate configuration before any write.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_metadata_initialize(
    fields: *const MetadataFields,
    requested: u32,
    proportion: f32,
) -> i32 {
    if fields.is_null() {
        return -1;
    }
    let fields = unsafe { &*fields };
    let mut rows = 0;
    let mut conflict = 0.0;
    if !fields.valid()
        || unsafe { swr_v1_memory_table_config(requested, proportion, &mut rows, &mut conflict) }
            != 0
    {
        return -1;
    }
    unsafe {
        fields.size.write(rows as usize);
        fields.mask.write(rows as usize - 1);
        fields.item_size.write(0);
        fields.memory_size.write(0);
        fields.conflict.write(conflict);
        fields.created.write(0);
        fields.rows.write(ptr::null_mut());
        fields.pool.write(ptr::null_mut());
        fields.iterator.write(ptr::null_mut());
        fields.memory.write(ptr::null_mut());
        fields.counters.rows.write(0);
        fields.counters.inserted.write(0);
        fields.counters.deleted.write(0);
        fields.counters.updated.write(0);
        fields.counters.conflicts.write(0);
        fields.counters.max_conflict.write(0);
    }
    0
}
/// Unpublished factory transaction. Native object/Mutex/vector allocations are
/// effects; Rust owns configuration, optional-collection selection and readiness.
#[repr(C)]
#[derive(Default)]
pub struct Factory {
    table: *mut c_void,
    mutex: *mut c_void,
    list: *mut c_void,
    index: *mut crate::table_columns::Columns,
    rows: u32,
    conflict: f32,
    legacy: u32,
    phase: u32,
}
/// Positive results request1 Table allocation,2 Mutex,3 legacy vector.0 commits
/// the completed native tokens; no C++ constructor or allocator runs in Rust.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_factory_step(
    fields: *const MetadataFields,
    cursor: *mut Factory,
) -> i32 {
    if cursor.is_null() {
        return -1;
    }
    let state = unsafe { &mut *cursor };
    match state.phase {
        0 => {
            if state.legacy > 1 {
                return -1;
            }
            let (mut rows, mut conflict) = (0, 0.0);
            if unsafe {
                swr_v1_memory_table_config(state.rows, state.conflict, &mut rows, &mut conflict)
            } != 0
            {
                return -1;
            }
            state.rows = rows;
            state.conflict = conflict;
            state.phase = 1;
            return 1;
        }
        1 => {
            if state.table.is_null() {
                return -1;
            }
            state.phase = 2;
            return 2;
        }
        2 if state.legacy == 1 => {
            if state.mutex.is_null() {
                return -1;
            }
            state.phase = 3;
            return 3;
        }
        2 if state.legacy == 0 => {}
        3 if state.legacy == 1 && !state.list.is_null() => {}
        _ => return -1,
    }
    if state.mutex.is_null()
        || !state.index.is_null()
        || unsafe { swr_v1_memory_table_metadata_initialize(fields, state.rows, state.conflict) }
            != 0
    {
        return -1;
    }
    if state.legacy == 1
        && unsafe { crate::table_columns::swr_v1_memory_table_columns_create(&mut state.index) }
            != 0
    {
        return -1;
    }
    state.phase = 4;
    0
}

#[repr(C)]
#[derive(Default)]
pub struct Creation {
    logical: Layout,
    physical: Layout,
    memory: *mut c_void,
    pool: *mut c_void,
    iterator: *mut c_void,
    phase: u32,
}
/// phase0 plans; phase1 publishes ready native tokens to actual field targets.
/// Native owns rollback until success; no Rust borrow survives native effects.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_creation_step(
    fields: *const MetadataFields,
    cursor: *mut Creation,
) -> i32 {
    if fields.is_null() || cursor.is_null() {
        return -1;
    }
    let fields = unsafe { &*fields };
    let state = unsafe { &mut *cursor };
    if !fields.valid() || state.phase > 1 || unsafe { fields.created.read() } != 0 {
        return -1;
    }
    let Ok(rows) = u32::try_from(unsafe { fields.size.read() }) else {
        return -1;
    };
    let item = unsafe { fields.item_size.read() };
    let conflict = unsafe { fields.conflict.read() };
    let mut logical = Layout::default();
    let mut physical = Layout::default();
    if unsafe { swr_v1_memory_table_layout(rows, item, conflict, &mut logical) } != 0
        || unsafe { swr_v1_memory_table_storage_layout(rows, item, conflict, &mut physical) } != 0
    {
        return -1;
    }
    if state.phase == 0 {
        state.logical = logical;
        state.physical = physical;
        state.phase = 1;
        return 1;
    }
    if state.logical != logical
        || state.physical != physical
        || state.memory.is_null()
        || state.pool.is_null()
        || state.iterator.is_null()
        || !state.memory.addr().is_multiple_of(mem::align_of::<Row>())
    {
        return -1;
    }
    unsafe {
        fields.memory.write(state.memory);
        fields.rows.write(state.memory.cast());
        fields.pool.write(state.pool);
        fields.iterator.write(state.iterator);
        // Preserve frozen logical accounting despite padded physical strides.
        fields.memory_size.write(logical.pool_size);
        fields.created.write(1);
    }
    state.phase = 2;
    0
}

/// Construction owns ordering/readiness and arena pointer arithmetic. Each
/// requested native effect completes before resume; native RAII owns rollback.
#[repr(C)]
#[derive(Default)]
pub struct Construction {
    storage: Creation,
    phase: u32,
}
#[repr(C)]
#[derive(Default)]
pub struct ConstructionEffect {
    memory: *mut c_void,
    size: usize,
    row_size: usize,
    action: u32,
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_construction_step(
    fields: *const MetadataFields,
    cursor: *mut Construction,
    output: *mut ConstructionEffect,
) -> i32 {
    if output.is_null() {
        return -1;
    }
    unsafe { output.write(ConstructionEffect::default()) };
    if cursor.is_null() {
        return -1;
    }
    let state = unsafe { &mut *cursor };
    let storage = &mut state.storage;
    let effect = match state.phase {
        0 => {
            if unsafe { swr_v1_memory_table_creation_step(fields, storage) } != 1 {
                return -1;
            }
            ConstructionEffect {
                size: storage.physical.total,
                action: 1,
                ..Default::default()
            }
        }
        1 => {
            if unsafe { swr_v1_memory_table_arena(storage.memory, &storage.physical) } != 0 {
                return -1;
            }
            ConstructionEffect {
                memory: unsafe {
                    storage
                        .memory
                        .cast::<u8>()
                        .add(storage.physical.pool_offset)
                }
                .cast(),
                size: storage.physical.pool_size,
                row_size: storage.physical.row_size,
                action: 2,
            }
        }
        2 => {
            if storage.pool.is_null() {
                return -1;
            }
            ConstructionEffect {
                size: storage.physical.row_size,
                action: 3,
                ..Default::default()
            }
        }
        3 => {
            if unsafe { swr_v1_memory_table_creation_step(fields, storage) } != 0 {
                return -1;
            }
            state.phase = 4;
            return 0;
        }
        _ => return -1,
    };
    state.phase += 1;
    unsafe { output.write(effect) };
    1
}

/// Independent teardown cursor. Native resource tokens are never dereferenced in
/// Rust; only the live pointer-token span and actual memory field are accessed.
#[repr(C)]
pub struct Teardown {
    index: *mut crate::table_columns::Columns,
    columns: *const *mut c_void,
    count: usize,
    position: usize,
    list: *mut c_void,
    iterator: *mut c_void,
    pool: *mut c_void,
    memory: *mut *mut c_void,
    mutex: *mut c_void,
    table: *mut c_void,
    phase: u32,
}
#[repr(C)]
#[derive(Default)]
pub struct TeardownEffect {
    token: *mut c_void,
    action: u32,
}

/// One effect per return, in existing opt-in facade order. No pointer-token span
/// borrow survives native column/list destruction or arena/wrapper release.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_teardown_step(
    cursor: *mut Teardown,
    output: *mut TeardownEffect,
) -> i32 {
    if output.is_null() {
        return -1;
    }
    unsafe { output.write(TeardownEffect::default()) };
    if cursor.is_null() {
        return -1;
    }
    let state = unsafe { &mut *cursor };
    if state.phase == 8 {
        return 0;
    }
    if state.phase > 8
        || state.position > state.count
        || state.count > isize::MAX as usize / std::mem::size_of::<*mut c_void>()
        || state.columns.is_null() && state.count != 0
        || state.memory.is_null()
        || !state
            .memory
            .addr()
            .is_multiple_of(std::mem::align_of::<*mut c_void>())
    {
        return -1;
    }
    loop {
        let (token, action) = match state.phase {
            0 => {
                if unsafe { crate::table_columns::swr_v1_memory_table_columns_discard(state.index) }
                    != 0
                {
                    return -1;
                }
                state.index = ptr::null_mut();
                state.phase = 1;
                continue;
            }
            1 if state.position < state.count => {
                // Read one token only; a later effect may destroy its column.
                let token = unsafe { state.columns.add(state.position).read() };
                state.position += 1;
                (token, 1)
            }
            1 => {
                state.phase = 2;
                continue;
            }
            2 => {
                state.phase = 3;
                (state.list, 2)
            }
            3 => {
                state.phase = 4;
                (state.iterator, 3)
            }
            4 => {
                state.phase = 5;
                (state.pool, 4)
            }
            5 => {
                state.phase = 6;
                let memory = unsafe { state.memory.read() };
                if memory.is_null() {
                    continue;
                }
                (memory, 5)
            }
            6 => {
                // Native has completed the optional unmap; actual pointer field
                // is still live until the final native Table-owner release.
                unsafe { state.memory.write(ptr::null_mut()) };
                state.phase = 7;
                (state.mutex, 6)
            }
            7 => {
                state.phase = 8;
                (state.table, 7)
            }
            _ => return -1,
        };
        unsafe { output.write(TeardownEffect { token, action }) };
        return 1;
    }
}

/// Collection-free core custody is explicit; never discard a legacy index or
/// infer an alternative owner from a tagged pointer. The existing Rust teardown
/// owns all remaining native-effect selection and memory-field publication.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_table_core_teardown_step(
    cursor: *mut Teardown,
    output: *mut TeardownEffect,
) -> i32 {
    if output.is_null() {
        return -1;
    }
    unsafe { output.write(TeardownEffect::default()) };
    if cursor.is_null() {
        return -1;
    }
    let state = unsafe { &mut *cursor };
    if !state.index.is_null()
        || !state.columns.is_null()
        || !state.list.is_null()
        || state.count != 0
        || state.position != 0
        || (1..=2).contains(&state.phase)
    {
        return -1;
    }
    if state.phase == 0 {
        state.phase = 3;
    }
    unsafe { swr_v1_memory_table_teardown_step(cursor, output) }
}

#[cfg(test)]
#[path = "../../../tests/modules/memory/table.rs"]
mod tests;
