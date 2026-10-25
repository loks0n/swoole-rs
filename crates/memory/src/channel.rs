use std::ffi::c_void;
use std::ptr;

#[repr(C)]
pub struct Channel {
    head: i64,
    tail: i64,
    size: usize,
    head_tag: u8,
    tail_tag: u8,
    num: i32,
    max_num: i32,
    bytes: usize,
    flags: i32,
    maxlen: i32,
    mem: *mut u8,
}
fn valid(c: &Channel) -> bool {
    // These predicates only read scalar POD fields. Combine them eagerly so
    // native callers do not pay a dependent branch for every invariant. Keep
    // pointer dereferences and queue writes behind the combined result.
    (!c.mem.is_null())
        & (c.size > 0)
        & (c.size <= (isize::MAX as usize).saturating_sub(c.maxlen.max(0) as usize + 4))
        // The bounded size above is <= isize::MAX, so unsigned cursor
        // comparisons reject negative cursors and the upper bound together.
        & ((c.head as usize) < c.size)
        & ((c.tail as usize) < c.size)
        & ((c.head_tag | c.tail_tag) <= 1)
        & (c.num >= 0)
        & (c.maxlen >= 0)
        & (c.maxlen as usize <= c.size)
}
// Short channel records should not need a dynamic libc memcpy dispatch. Copy
// fixed-width endpoints, which may overlap each other but stay inside both
// disjoint borrowed ranges. No speculative byte access outside the record: a
// one-byte record at the end of a mapping needs only one readable byte.
#[inline(always)]
unsafe fn copy_record(input: *const u8, output: *mut u8, length: usize) {
    #[inline]
    unsafe fn endpoints<const N: usize>(input: *const u8, output: *mut u8, length: usize) {
        unsafe {
            ptr::copy_nonoverlapping(input, output, N);
            ptr::copy_nonoverlapping(input.add(length - N), output.add(length - N), N);
        }
    }
    unsafe {
        if length > 64 {
            ptr::copy_nonoverlapping(input, output, length);
        } else if length >= 32 {
            endpoints::<32>(input, output, length);
        } else if length >= 16 {
            endpoints::<16>(input, output, length);
        } else if length >= 8 {
            endpoints::<8>(input, output, length);
        } else if length >= 4 {
            endpoints::<4>(input, output, length);
        } else if length >= 2 {
            endpoints::<2>(input, output, length);
        } else if length == 1 {
            ptr::copy_nonoverlapping(input, output, 1);
        }
    }
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_channel_in(
    channel: *mut Channel,
    input: *const c_void,
    length: i32,
) -> i32 {
    if channel.is_null() || length < 0 || length > 0 && input.is_null() {
        return -1;
    }
    let c = unsafe { &mut *channel };
    if !valid(c) || length > c.maxlen || c.num == i32::MAX {
        return -1;
    }
    let Some(used) = (c.num as usize)
        .checked_mul(4)
        .and_then(|n| c.bytes.checked_add(n))
    else {
        return -1;
    };
    if c.head == c.tail && c.tail_tag != c.head_tag || used == c.size {
        return -1;
    }
    let packet = length as usize + 4;
    if c.tail < c.head && (c.head - c.tail) < packet as i64 {
        return -1;
    }
    let Some(bytes) = c.bytes.checked_add(length as usize) else {
        return -1;
    };
    unsafe {
        let item = c.mem.add(c.tail as usize);
        item.cast::<i32>().write_unaligned(length);
        copy_record(input.cast::<u8>(), item.add(4), length as usize);
    }
    c.tail += packet as i64;
    if c.tail >= c.size as i64 {
        c.tail = 0;
        c.tail_tag = 1 - c.tail_tag;
    }
    c.num += 1;
    c.bytes = bytes;
    0
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_channel_out(
    channel: *mut Channel,
    output: *mut c_void,
    capacity: i32,
    consume: u32,
) -> i32 {
    if channel.is_null() || capacity < 0 || consume > 1 {
        return -1;
    }
    let length = unsafe { read_record(&*channel, output, capacity) };
    if length >= 0 && consume != 0 {
        let c = unsafe { &mut *channel };
        c.head += length as i64 + 4;
        if c.head >= c.size as i64 {
            c.head = 0;
            c.head_tag = 1 - c.head_tag;
        }
        c.num -= 1;
        c.bytes -= length as usize;
    }
    length
}
unsafe fn read_record(c: &Channel, output: *mut c_void, capacity: i32) -> i32 {
    if capacity < 0 || !valid(c) || c.num == 0 {
        return -1;
    }
    let item = unsafe { c.mem.add(c.head as usize) };
    let length = unsafe { item.cast::<i32>().read_unaligned() };
    if length < 0
        || length > c.maxlen
        || length > capacity
        || length as usize > c.bytes
        || length > 0 && output.is_null()
    {
        return -1;
    }
    unsafe {
        copy_record(item.add(4), output.cast::<u8>(), length as usize);
    }
    length
}
/// Independent descriptor, not a C++ object or prefix. Its disjoint typed targets
/// are live and serialized for this call; native Lock/Pipe objects never enter Rust.
#[repr(C)]
pub struct Fields {
    head: *mut i64,
    tail: *mut i64,
    size: *mut usize,
    head_tag: *mut u8,
    tail_tag: *mut u8,
    num: *mut i32,
    max_num: *mut i32,
    bytes: *mut usize,
    flags: *mut i32,
    maxlen: *mut i32,
    mem: *mut *mut u8,
}
impl Fields {
    fn valid(&self) -> bool {
        !self.head.is_null()
            && self.head.is_aligned()
            && !self.tail.is_null()
            && self.tail.is_aligned()
            && !self.size.is_null()
            && self.size.is_aligned()
            && !self.head_tag.is_null()
            && self.head_tag.is_aligned()
            && !self.tail_tag.is_null()
            && self.tail_tag.is_aligned()
            && !self.num.is_null()
            && self.num.is_aligned()
            && !self.max_num.is_null()
            && self.max_num.is_aligned()
            && !self.bytes.is_null()
            && self.bytes.is_aligned()
            && !self.flags.is_null()
            && self.flags.is_aligned()
            && !self.maxlen.is_null()
            && self.maxlen.is_aligned()
            && !self.mem.is_null()
            && self.mem.is_aligned()
    }
    unsafe fn load(&self) -> Channel {
        Channel {
            head: unsafe { self.head.read() },
            tail: unsafe { self.tail.read() },
            size: unsafe { self.size.read() },
            head_tag: unsafe { self.head_tag.read() },
            tail_tag: unsafe { self.tail_tag.read() },
            num: unsafe { self.num.read() },
            max_num: unsafe { self.max_num.read() },
            bytes: unsafe { self.bytes.read() },
            flags: unsafe { self.flags.read() },
            maxlen: unsafe { self.maxlen.read() },
            mem: unsafe { self.mem.read() },
        }
    }
    unsafe fn publish(&self, state: &Channel, producer: bool) {
        unsafe {
            if producer {
                self.tail.write(state.tail);
                self.tail_tag.write(state.tail_tag);
            } else {
                self.head.write(state.head);
                self.head_tag.write(state.head_tag);
            }
            self.num.write(state.num);
            self.bytes.write(state.bytes);
        }
    }
}
#[repr(C)]
#[derive(Clone, Copy, Default, PartialEq, Eq)]
pub struct StoragePlan {
    total: usize,
    size: usize,
    header_size: usize,
    maxlen: i32,
    flags: i32,
}
impl StoragePlan {
    fn new(size: usize, maxlen: usize, flags: i32, header_size: usize) -> Option<Self> {
        let maxlen = i32::try_from(maxlen).ok()?;
        if size < maxlen as usize || header_size == 0 {
            return None;
        }
        let total = size
            .checked_add(maxlen as usize)?
            .checked_add(4)?
            .checked_add(header_size)?;
        (total <= isize::MAX as usize).then_some(Self {
            total,
            size,
            header_size,
            maxlen,
            flags,
        })
    }
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_channel_storage_plan(
    size: usize,
    maxlen: usize,
    flags: i32,
    header_size: usize,
    output: *mut StoragePlan,
) -> i32 {
    if output.is_null() {
        return -1;
    }
    unsafe {
        output.write(StoragePlan::default());
    }
    let Some(plan) = StoragePlan::new(size, maxlen, flags, header_size) else {
        return -1;
    };
    unsafe {
        output.write(plan);
    }
    0
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_channel_storage_init(
    fields: *const Fields,
    plan: *const StoragePlan,
    memory: *mut c_void,
) -> i32 {
    if fields.is_null() || plan.is_null() || memory.is_null() {
        return -1;
    }
    let fields = unsafe { &*fields };
    let plan = unsafe { plan.read() };
    if !fields.valid()
        || StoragePlan::new(
            plan.size,
            plan.maxlen as usize,
            plan.flags,
            plan.header_size,
        ) != Some(plan)
        || memory
            .addr()
            .checked_add(plan.total - plan.header_size)
            .is_none()
    {
        return -1;
    }
    unsafe {
        fields.head.write(0);
        fields.tail.write(0);
        fields.size.write(plan.size);
        fields.head_tag.write(0);
        fields.tail_tag.write(0);
        fields.num.write(0);
        fields.max_num.write(0);
        fields.bytes.write(0);
        fields.flags.write(plan.flags);
        fields.maxlen.write(plan.maxlen);
        fields.mem.write(memory.cast());
    }
    0
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_channel_storage_in(
    fields: *const Fields,
    input: *const c_void,
    length: i32,
) -> i32 {
    if fields.is_null() {
        return -1;
    }
    let fields = unsafe { &*fields };
    if !fields.valid() {
        return -1;
    }
    let mut state = unsafe { fields.load() };
    let result = unsafe { swr_v1_memory_channel_in(&mut state, input, length) };
    if result == 0 {
        unsafe {
            fields.publish(&state, true);
        }
    }
    result
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_channel_storage_out(
    fields: *const Fields,
    output: *mut c_void,
    capacity: i32,
) -> i32 {
    if fields.is_null() {
        return -1;
    }
    let fields = unsafe { &*fields };
    if !fields.valid() {
        return -1;
    }
    let mut state = unsafe { fields.load() };
    let result = unsafe { swr_v1_memory_channel_out(&mut state, output, capacity, 1) };
    if result >= 0 {
        unsafe {
            fields.publish(&state, false);
        }
    }
    result
}

/// Only the initialized scalar fields read by public Channel::full cross ABI.
#[repr(C)]
pub struct CapacityState {
    head: i64,
    tail: i64,
    size: usize,
    bytes: usize,
    num: i32,
    head_tag: u8,
    tail_tag: u8,
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_channel_full(state: *const CapacityState) -> i32 {
    if state.is_null() {
        return -1;
    }
    let state = unsafe { &*state };
    let occupied = state
        .bytes
        .wrapping_add((state.num as usize).wrapping_mul(4));
    i32::from(
        state.head == state.tail && state.tail_tag != state.head_tag || occupied == state.size,
    )
}

/// Native effects execute only after this independent action plan returns.
#[repr(C)]
#[derive(Default)]
pub struct Lifecycle {
    count: u32,
    actions: [u32; 4],
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_channel_lifecycle(
    flags: i32,
    phase: u32,
    output: *mut Lifecycle,
) -> i32 {
    if output.is_null() {
        return -1;
    }
    unsafe {
        output.write(Lifecycle::default());
    }
    if phase > 1 {
        return -1;
    }
    let mut plan = Lifecycle::default();
    let mut push = |action| {
        plan.actions[plan.count as usize] = action;
        plan.count += 1;
    };
    if phase == 0 {
        push(if flags & 8 == 0 { 1 } else { 2 }); // allocate heap/shared
        push(3); // initialize scalar storage
        if flags & 2 != 0 {
            push(4);
        } // create native lock
        if flags & 4 != 0 {
            push(5);
        } // create native notification pipe
    } else {
        if flags & 2 != 0 {
            push(6);
        } // delete native lock
        if flags & 4 != 0 {
            push(7);
        } // close/delete native pipe
        push(if flags & 8 == 0 { 8 } else { 9 }); // release heap/shared
    }
    unsafe {
        output.write(plan);
    }
    0
}

#[cfg(test)]
#[path = "../../../tests/modules/memory/channel.rs"]
mod tests;
