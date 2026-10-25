use std::ffi::c_void;
use std::{mem, ptr};

#[repr(C)]
#[derive(Clone, Copy)]
pub struct Slice {
    lock: u8,
    next: *mut Slice,
    prev: *mut Slice,
}
#[repr(C)]
#[derive(Clone, Copy)]
pub struct Fixed {
    memory: *mut u8,
    size: usize,
    head: *mut Slice,
    tail: *mut Slice,
    slice_num: u32,
    slice_use: u32,
    slice_size: u32,
    shared: u8,
    allocated: u8,
}

impl Fixed {
    // Allocation/release are externally serialized, but immutable ABI getters
    // may observe configuration. Never give Rust an exclusive whole-header
    // reference or rewrite those immutable fields during a queue operation.
    unsafe fn publish_queue(&self, target: *mut Fixed) {
        unsafe {
            ptr::addr_of_mut!((*target).head).write(self.head);
            ptr::addr_of_mut!((*target).tail).write(self.tail);
            ptr::addr_of_mut!((*target).slice_use).write(self.slice_use);
        }
    }
}

#[repr(C)]
#[derive(Default)]
pub struct Usage {
    spare: u32,
    total: u32,
    width: u32,
}
/// Independent read-only snapshot; serialized with pool mutation.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_fixed_usage(pool: *const Fixed, output: *mut Usage) -> i32 {
    if output.is_null() {
        return -1;
    }
    unsafe { output.write(Usage::default()) };
    if pool.is_null() {
        return -1;
    }
    let pool = unsafe { &*pool };
    unsafe {
        output.write(Usage {
            spare: pool.slice_num.wrapping_sub(pool.slice_use),
            total: pool.slice_num,
            width: pool.slice_size,
        })
    };
    0
}

/// Shared arena ownership actions:0 no effect,1/2 heap/shared allocation,
///3/4 heap/shared release. Native effects execute only after this call returns.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_memory_arena_lifecycle(shared: u32, owned: u32, phase: u32) -> i32 {
    if shared > 1 || owned > 1 || phase > 1 {
        -1
    } else if owned == 0 {
        0
    } else {
        (1 + shared + 2 * phase) as i32
    }
}

#[repr(C)]
#[derive(Default)]
pub struct DebugCursor {
    next: *mut Slice,
    line: u64,
}
#[repr(C)]
#[derive(Default)]
pub struct DebugRecord {
    slice: *mut Slice,
    prev: *mut Slice,
    next: *mut Slice,
    data: *mut u8,
    line: u64,
    lock: u8,
    self_link: u8,
}

/// Serialized diagnostic traversal of actual linked storage, including odd widths.
/// Independent cursor/output are disjoint from pool and arena; no native callbacks.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_fixed_debug_step(
    pool: *const Fixed,
    cursor: *mut DebugCursor,
    max_lines: i32,
    output: *mut DebugRecord,
) -> i32 {
    if output.is_null() {
        return -1;
    }
    unsafe { output.write(DebugRecord::default()) };
    if pool.is_null() || cursor.is_null() {
        return -1;
    }
    let cursor = unsafe { &mut *cursor };
    let slice = if cursor.line == 0 {
        unsafe { (*pool).head }
    } else {
        cursor.next
    };
    if slice.is_null() {
        return 0;
    }
    let node = unsafe { slice.read_unaligned() };
    let Some(next_line) = cursor.line.checked_add(1) else {
        return -1;
    };
    let record = DebugRecord {
        slice,
        prev: node.prev,
        next: node.next,
        data: unsafe { slice.cast::<u8>().add(mem::size_of::<Slice>()) },
        line: cursor.line,
        lock: node.lock,
        self_link: u8::from(node.next == slice),
    };
    // Preserve the original post-print `line++ > max_lines` bound: max0 emits2.
    cursor.next = if max_lines < 0 || cursor.line > max_lines as u64 {
        ptr::null_mut()
    } else {
        node.next
    };
    cursor.line = next_line;
    unsafe { output.write(record) };
    1
}

/// Complete arena plan; the native facade only supplies allocation effects.
#[repr(C)]
#[derive(Clone, Copy, Default, Debug, PartialEq, Eq)]
pub struct Layout {
    total: usize,
    usable: usize,
    slices: u32,
    width: u32,
}
impl Layout {
    fn new(count: u32, width: u32, available: usize, owned: u32) -> Option<Self> {
        let (total, usable, slices, width) = match owned {
            1 if count >= 2 && available == 0 => {
                let width = width.checked_add(7)? & !7;
                let usable =
                    (mem::size_of::<Slice>() + width as usize).checked_mul(count as usize)?;
                (
                    usable.checked_add(mem::size_of::<Fixed>())?,
                    usable,
                    count,
                    width,
                )
            }
            0 if count == 0 => {
                let usable = available.checked_sub(mem::size_of::<Fixed>())?;
                let slices =
                    u32::try_from(usable / (mem::size_of::<Slice>() + width as usize)).ok()?;
                if slices < 2 {
                    return None;
                }
                (available, usable, slices, width)
            }
            _ => return None,
        };
        (total <= isize::MAX as usize).then_some(Self {
            total,
            usable,
            slices,
            width,
        })
    }
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_fixed_layout(
    count: u32,
    width: u32,
    available: usize,
    owned: u32,
    output: *mut Layout,
) -> i32 {
    if output.is_null() {
        return -1;
    }
    unsafe {
        output.write(Layout::default());
    }
    let Some(layout) = Layout::new(count, width, available, owned) else {
        return -1;
    };
    unsafe {
        output.write(layout);
    }
    0
}
/// Initialize actual arena header and links after native allocation has returned.
/// `arena` covers layout.total exclusive bytes; layout is separate initialized storage.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_fixed_construct(
    arena: *mut Fixed,
    layout: *const Layout,
    shared: u32,
    owned: u32,
) -> i32 {
    if arena.is_null()
        || layout.is_null()
        || !arena.addr().is_multiple_of(mem::align_of::<Fixed>())
        || shared > 1
    {
        return -1;
    }
    let plan = unsafe { layout.read() };
    let expected = Layout::new(
        if owned == 1 { plan.slices } else { 0 },
        plan.width,
        if owned == 0 { plan.total } else { 0 },
        owned,
    );
    if expected != Some(plan) || arena.addr().checked_add(plan.total).is_none() {
        return -1;
    }
    unsafe {
        // Preserve original whole-header zeroing, including ABI padding.
        // Whole repr(C) value writes can copy uninitialized Rust padding.
        ptr::write_bytes(arena.cast::<u8>(), 0, mem::size_of::<Fixed>());
        ptr::addr_of_mut!((*arena).memory).write(arena.cast::<u8>().add(mem::size_of::<Fixed>()));
        ptr::addr_of_mut!((*arena).size).write(plan.usable);
        ptr::addr_of_mut!((*arena).slice_num).write(plan.slices);
        ptr::addr_of_mut!((*arena).slice_size).write(plan.width);
        ptr::addr_of_mut!((*arena).shared).write(shared as u8);
        ptr::addr_of_mut!((*arena).allocated).write(owned as u8);
        swr_v1_memory_fixed_init(arena)
    }
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_fixed_init(pool: *mut Fixed) -> i32 {
    if pool.is_null() {
        return -1;
    }
    let p = unsafe { &mut *pool };
    let Some(stride) = mem::size_of::<Slice>().checked_add(p.slice_size as usize) else {
        return -1;
    };
    // Table row sizes may be odd: slice headers require unaligned loads/stores.
    if p.memory.is_null()
        || p.slice_num < 2
        || (p.slice_num as usize)
            .checked_mul(stride)
            .is_none_or(|n| n > p.size)
    {
        return -1;
    }
    p.head = ptr::null_mut();
    p.tail = p.memory.cast();
    for i in 0..p.slice_num as usize {
        let node = unsafe { p.memory.add(i * stride).cast::<Slice>() };
        unsafe {
            ptr::write_bytes(node.cast::<u8>(), 0, mem::size_of::<Slice>());
            ptr::addr_of_mut!((*node).next).write_unaligned(p.head);
        }
        if !p.head.is_null() {
            unsafe {
                ptr::addr_of_mut!((*p.head).prev).write_unaligned(node);
            }
        }
        p.head = node;
    }
    p.slice_use = 0;
    0
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_fixed_alloc(pool: *mut Fixed) -> *mut c_void {
    if pool.is_null() {
        return ptr::null_mut();
    }
    let mut p = unsafe { pool.read() };
    let node = p.head;
    if node.is_null() || unsafe { node.read_unaligned().lock } != 0 {
        return ptr::null_mut();
    }
    // At least two nodes always remain in the combined idle/busy list.
    unsafe {
        let value = node.read_unaligned();
        p.slice_use += 1;
        p.head = value.next;
        ptr::addr_of_mut!((*p.head).prev).write_unaligned(ptr::null_mut());
        ptr::addr_of_mut!((*p.tail).next).write_unaligned(node);
        ptr::addr_of_mut!((*node).lock).write(1);
        ptr::addr_of_mut!((*node).next).write_unaligned(ptr::null_mut());
        ptr::addr_of_mut!((*node).prev).write_unaligned(p.tail);
        p.tail = node;
        p.publish_queue(pool);
        node.cast::<u8>().add(mem::size_of::<Slice>()).cast()
    }
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_fixed_free(pool: *mut Fixed, data: *mut c_void) -> i32 {
    if pool.is_null() || data.is_null() {
        return -1;
    }
    let mut p = unsafe { pool.read() };
    let Some(offset) = data
        .addr()
        .checked_sub(p.memory.addr() + mem::size_of::<Slice>())
    else {
        return -1;
    };
    let stride = mem::size_of::<Slice>() + p.slice_size as usize;
    if offset % stride != 0 || offset / stride >= p.slice_num as usize {
        return -1;
    }
    let node = unsafe { p.memory.add(offset).cast::<Slice>() };
    let value = unsafe { node.read_unaligned() };
    if value.lock != 1 || p.slice_use == 0 {
        return -1;
    }
    unsafe {
        ptr::addr_of_mut!((*node).lock).write_unaligned(0);
        p.slice_use -= 1;
        if node != p.head {
            if node == p.tail {
                ptr::addr_of_mut!((*value.prev).next).write_unaligned(ptr::null_mut());
                p.tail = value.prev;
            } else {
                ptr::addr_of_mut!((*value.prev).next).write_unaligned(value.next);
                ptr::addr_of_mut!((*value.next).prev).write_unaligned(value.prev);
            }
            ptr::addr_of_mut!((*node).next).write_unaligned(p.head);
            ptr::addr_of_mut!((*node).prev).write_unaligned(ptr::null_mut());
            ptr::addr_of_mut!((*p.head).prev).write_unaligned(node);
            p.head = node;
        }
    }
    unsafe { p.publish_queue(pool) };
    0
}

#[cfg(test)]
#[path = "../../../tests/modules/memory/fixed.rs"]
mod tests;
