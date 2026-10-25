//! Single-producer, multi-releaser ring policy over the unchanged shared arena.
use std::ffi::c_void;
use std::ptr;
use std::sync::atomic::{AtomicU16, AtomicU32, Ordering};

#[repr(C)]
pub struct Ring {
    memory: *mut u8,
    size: u32,
    alloc_offset: u32,
    collect_offset: u32,
    alloc_count: u32,
    status: u8,
    free_count: *mut u32,
}
// Actual C POD shared header. Never borrow the whole object: consumers update
// free_count concurrently while only the producer accesses the cursor fields.
#[repr(C)]
pub struct Storage {
    memory: *mut u8,
    shared: u8,
    status: u8,
    size: u32,
    alloc_offset: u32,
    collect_offset: u32,
    alloc_count: u32,
    free_count: u32,
}
impl Ring {
    fn valid(&self) -> bool {
        !self.memory.is_null()
            && self.memory.addr().is_multiple_of(8)
            && self.size >= 16
            && self.alloc_offset <= self.size
            && self.collect_offset <= self.size
            && self.alloc_offset.is_multiple_of(8)
            && self.collect_offset.is_multiple_of(8)
            && !self.free_count.is_null()
            && self.free_count.addr().is_multiple_of(4)
            && self.status <= 1
    }
    unsafe fn collect(&mut self) -> bool {
        let count = unsafe { AtomicU32::from_ptr(self.free_count) };
        let mut index = 0;
        // The counter only bounds work; it does not publish any particular
        // record. An out-of-order consumer can supply the count while a
        // different record reaches the front. Its acquire lock load below
        // remains the publication barrier; all counter RMWs remain SeqCst.
        // Deliberately retain upstream's shrinking-bound collection loop.
        while index < count.load(Ordering::Relaxed) {
            if self.collect_offset > self.size - 8 {
                return false;
            }
            let item = unsafe { self.memory.add(self.collect_offset as usize) };
            if unsafe { AtomicU16::from_ptr(item.cast()) }.load(Ordering::Acquire) != 0 {
                break;
            }
            let length = unsafe { item.add(4).cast::<u32>().read() };
            let Some(next) = length
                .checked_add(8)
                .and_then(|n| self.collect_offset.checked_add(n))
                .filter(|&n| n <= self.size)
            else {
                return false;
            };
            self.collect_offset = next;
            if self.collect_offset > self.size - 8 || self.collect_offset >= self.size {
                self.collect_offset = 0;
                self.status = 0;
            }
            count.fetch_sub(1, Ordering::SeqCst);
            index += 1;
        }
        true
    }
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_ring_layout(
    requested: u32,
    total: *mut u32,
    payload: *mut u32,
) -> i32 {
    if total.is_null() || payload.is_null() {
        return -1;
    }
    unsafe {
        total.write(0);
        payload.write(0);
    }
    let Some(size) = requested
        .checked_add(7)
        .map(|n| n & !7)
        .filter(|&n| n >= 48)
    else {
        return -1;
    };
    unsafe {
        total.write(size);
        payload.write(size - 32);
    }
    0
}
/// Initialize fresh exclusive declared C arena storage before any consumer exists.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_ring_construct(
    storage: *mut Storage,
    total: u32,
    shared: u32,
) -> i32 {
    if storage.is_null()
        || !storage.is_aligned()
        || shared > 1
        || total < 48
        || !total.is_multiple_of(8)
        || storage.addr().checked_add(total as usize).is_none()
    {
        return -1;
    }
    unsafe {
        ptr::write_bytes(storage.cast::<u8>(), 0, std::mem::size_of::<Storage>());
        ptr::addr_of_mut!((*storage).memory).write(storage.cast::<u8>().add(32));
        ptr::addr_of_mut!((*storage).size).write(total - 32);
        ptr::addr_of_mut!((*storage).shared).write(shared as u8);
    }
    0
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_ring_alloc(state: *mut Ring, requested: u32) -> *mut c_void {
    unsafe { allocate(state, requested) }
}
#[inline(always)]
unsafe fn allocate(state: *mut Ring, requested: u32) -> *mut c_void {
    if state.is_null() || requested == 0 {
        return ptr::null_mut();
    }
    let c = unsafe { &mut *state };
    if !c.valid() {
        return ptr::null_mut();
    }
    let Some(size) = requested.checked_add(7).map(|n| n & !7) else {
        return ptr::null_mut();
    };
    let Some(total) = size.checked_add(8) else {
        return ptr::null_mut();
    };
    if !unsafe { c.collect() } {
        return ptr::null_mut();
    }
    let count = unsafe { AtomicU32::from_ptr(c.free_count) };
    let capacity;
    if c.status == 0 {
        if u64::from(c.alloc_offset) + u64::from(total) >= u64::from(c.size - 8) {
            let skip = c.size - c.alloc_offset;
            if skip >= 8 {
                let item = unsafe { c.memory.add(c.alloc_offset as usize) };
                unsafe {
                    item.add(4).cast::<u32>().write(skip - 8);
                    AtomicU16::from_ptr(item.cast()).store(0, Ordering::Release);
                }
                count.fetch_add(1, Ordering::SeqCst);
            }
            c.alloc_offset = 0;
            c.status = 1;
            capacity = c.collect_offset;
        } else {
            capacity = c.size - c.alloc_offset;
        }
    } else {
        let Some(available) = c.collect_offset.checked_sub(c.alloc_offset) else {
            return ptr::null_mut();
        };
        capacity = available;
    }
    if capacity < total {
        return ptr::null_mut();
    }
    let item = unsafe { c.memory.add(c.alloc_offset as usize) };
    unsafe {
        item.add(2).cast::<u16>().write(c.alloc_count as u16);
        item.add(4).cast::<u32>().write(size);
        AtomicU16::from_ptr(item.cast()).store(1, Ordering::Release);
    }
    c.alloc_offset += total;
    c.alloc_count = c.alloc_count.wrapping_add(1);
    unsafe { item.add(8).cast() }
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_ring_storage_alloc(
    storage: *mut Storage,
    requested: u32,
) -> *mut c_void {
    if storage.is_null()
        || !storage
            .addr()
            .is_multiple_of(std::mem::align_of::<Storage>())
    {
        return ptr::null_mut();
    }
    unsafe {
        let mut state = Ring {
            memory: ptr::addr_of!((*storage).memory).read(),
            size: ptr::addr_of!((*storage).size).read(),
            alloc_offset: ptr::addr_of!((*storage).alloc_offset).read(),
            collect_offset: ptr::addr_of!((*storage).collect_offset).read(),
            alloc_count: ptr::addr_of!((*storage).alloc_count).read(),
            status: ptr::addr_of!((*storage).status).read(),
            free_count: ptr::addr_of_mut!((*storage).free_count),
        };
        let result = allocate(&mut state, requested);
        // A failed allocation can still collect/wrap, exactly as the snapshot ABI.
        ptr::addr_of_mut!((*storage).alloc_offset).write(state.alloc_offset);
        ptr::addr_of_mut!((*storage).collect_offset).write(state.collect_offset);
        ptr::addr_of_mut!((*storage).alloc_count).write(state.alloc_count);
        ptr::addr_of_mut!((*storage).status).write(state.status);
        result
    }
}

// All guards are scalar and can be combined before any memory access. With
// size>=8, a wrapped subtraction is larger than every permitted u32 range.
fn release_offset(memory: usize, size: u32, count: usize, data: usize) -> Option<usize> {
    let offset = data.wrapping_sub(memory).wrapping_sub(8);
    let aligned = ((memory | data) & 7) | (count & 3) == 0;
    let valid = (memory != 0)
        & (count != 0)
        & (data >= memory)
        & (size >= 8)
        & (offset <= (size as usize).wrapping_sub(8))
        & aligned;
    valid.then_some(offset)
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_ring_free(
    memory: *mut c_void,
    size: u32,
    free_count: *mut u32,
    data: *mut c_void,
) -> i32 {
    let Some(offset) = release_offset(memory.addr(), size, free_count.addr(), data.addr()) else {
        return -1;
    };
    let item = unsafe { memory.cast::<u8>().add(offset) };
    let lock = unsafe { AtomicU16::from_ptr(item.cast()) };
    // Exactly one consumer owns this live record. A second simultaneous
    // release is outside the contract, so no competing writer needs a CAS.
    // Keep the sequential duplicate-release check; the release store publishes
    // completed payload access to the producer's acquire collection load.
    if lock.load(Ordering::Relaxed) != 1 {
        return -1;
    }
    lock.store(0, Ordering::Release);
    unsafe { AtomicU32::from_ptr(free_count) }.fetch_add(1, Ordering::SeqCst);
    0
}

#[cfg(test)]
#[path = "../../../tests/modules/memory/ring.rs"]
mod tests;
