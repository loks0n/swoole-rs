//! Rust page registry and bump-allocation policy; native code supplies/frees pages.
use std::alloc::{Layout, alloc, dealloc};
use std::ffi::c_void;
use std::ptr::{self, NonNull};

/// Page invariant: every entry of `pages` is a fresh, disjoint, 8-aligned `page_size`-byte
/// arena the native facade handed over once (`add_page`), and `offset <= page_size`
/// counts the bytes already allocated in the last page.
struct Global {
    pages: Vec<NonNull<u8>>,
    page_size: usize,
    offset: usize,
    drained: Option<usize>,
    shared: bool,
    creator: i64,
}
impl Global {
    fn pop_page(&mut self) -> Option<NonNull<u8>> {
        // Even an empty drain irreversibly closes page/record registration.
        let index = self.drained.get_or_insert(0);
        let page = self.pages.get(*index).copied()?;
        *index += 1;
        Some(page)
    }
    fn allocation_size(&self, requested: u32) -> Option<(usize, usize)> {
        if self.drained.is_some() {
            return None;
        }
        let size = (requested as usize).checked_add(7)? & !7;
        let total = size.checked_add(8)?;
        (total <= self.page_size).then_some((size, total))
    }
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_global_page_size(
    requested: u32,
    system_page: u32,
    output: *mut u32,
) -> i32 {
    if output.is_null() {
        return -1;
    }
    // SAFETY: `output` is non-null (checked above), aligned and writable.
    unsafe {
        output.write(0);
    }
    if requested < 4096 || !system_page.is_power_of_two() || system_page < 8 {
        return -1;
    }
    let Some(aligned) = requested
        .checked_add(system_page - 1)
        .map(|n| n & !(system_page - 1))
    else {
        return -1;
    };
    // SAFETY: `output` is non-null (checked above), aligned and writable.
    unsafe {
        output.write(aligned);
    }
    0
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_global_request_valid(
    state: *const c_void,
    requested: u32,
    aligned: *mut u32,
) -> i32 {
    if aligned.is_null() {
        return -1;
    }
    // SAFETY: `aligned` is non-null (checked above), aligned and writable.
    unsafe {
        aligned.write(0);
    }
    let Some(size) = requested.checked_add(7).map(|n| n & !7) else {
        return -1;
    };
    // SAFETY: `aligned` is non-null (checked above), aligned and writable.
    unsafe {
        aligned.write(size);
    }
    if state.is_null() {
        return -1;
    }
    // SAFETY: `state` is non-null (checked above), aligned and initialized per the caller contract.
    if unsafe { &*state.cast::<Global>() }
        .allocation_size(requested)
        .is_some()
    {
        0
    } else {
        -1
    }
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_global_create(
    page_size: u32,
    output: *mut *mut c_void,
) -> i32 {
    if output.is_null() {
        return -1;
    }
    // SAFETY: `output` is non-null (checked above), aligned and writable.
    unsafe {
        output.write(ptr::null_mut());
    }
    if page_size < 8 || !page_size.is_multiple_of(8) {
        return -1;
    }
    #[expect(
        clippy::cast_ptr_alignment,
        reason = "alloc honours Layout::new::<Global>()"
    )]
    // SAFETY: `Global` is not zero-sized; null is handled below.
    let state = unsafe { alloc(Layout::new::<Global>()).cast::<Global>() };
    if state.is_null() {
        return -1;
    }
    // SAFETY: a fresh, non-null allocation with `Global`'s layout.
    unsafe {
        state.write(Global {
            pages: Vec::new(),
            page_size: page_size as usize,
            offset: 0,
            drained: None,
            shared: false,
            creator: 0,
        })
    };
    // SAFETY: `output` is non-null (checked above), aligned and writable.
    unsafe { output.write(state.cast()) };
    0
}
/// Independent effect descriptor. Native executes its action only after return.
#[repr(C)]
#[derive(Default)]
pub struct GlobalEffect {
    pub page: *mut c_void,
    pub page_size: u32,
    pub aligned: u32,
    pub action: u32,
}

/// Owned configuration uses the same opaque registry and frozen allocation APIs.
/// -2 is invalid configuration, -1 allocation failure; output is cleared first.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_global_open(
    requested: u32,
    system_page: u32,
    shared: u32,
    creator: i64,
    output: *mut *mut c_void,
) -> i32 {
    if output.is_null() {
        return -2;
    }
    // SAFETY: `output` is non-null (checked above), aligned and writable per the caller contract.
    unsafe { output.write(ptr::null_mut()) };
    let mut page_size = 0;
    if shared > 1
        // SAFETY: `page_size` is a writable local.
        || unsafe { swr_v1_memory_global_page_size(requested, system_page, &raw mut page_size) } != 0
    {
        return -2;
    }
    // SAFETY: `output` is non-null, aligned and writable.
    if unsafe { swr_v1_memory_global_create(page_size, output) } != 0 {
        return -1;
    }
    // SAFETY: as above; create succeeded, so it holds a fresh `Global`.
    let created = unsafe { *output };
    // SAFETY: as above, exclusively ours until we return it.
    let state = unsafe { &mut *created.cast::<Global>() };
    state.shared = shared != 0;
    state.creator = creator;
    0
}

/// phase0 plans a page allocation, phase1 validates a request and selects fork
/// reset, phase2 drains one page. Page effects and wrapper replacement stay native.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_global_step(
    state: *mut c_void,
    phase: u32,
    current: i64,
    requested: u32,
    output: *mut GlobalEffect,
) -> i32 {
    if output.is_null() {
        return -1;
    }
    // SAFETY: `output` is non-null (checked above), aligned and writable per the caller contract.
    unsafe { output.write(GlobalEffect::default()) };
    if state.is_null() {
        return -1;
    }
    // SAFETY: `state` is non-null (checked above), aligned and exclusive per the caller contract.
    let state = unsafe { &mut *state.cast::<Global>() };
    let mut effect = GlobalEffect {
        #[expect(
            clippy::cast_possible_truncation,
            reason = "the native uint32_t page size"
        )]
        page_size: state.page_size as u32,
        ..GlobalEffect::default()
    };
    let status = match phase {
        0 if state.drained.is_none() => {
            effect.action = if state.shared { 2 } else { 1 };
            0
        }
        1 => {
            effect.aligned = requested.checked_add(7).map_or(0, |n| n & !7);
            if state.allocation_size(requested).is_none() {
                -1
            } else {
                if state.shared && state.creator != current {
                    effect.action = 5;
                }
                0
            }
        }
        2 => {
            if let Some(page) = state.pop_page() {
                effect.page = page.as_ptr().cast();
                effect.action = if state.shared { 4 } else { 3 };
            }
            0
        }
        _ => -1,
    };
    // SAFETY: `output` is non-null (checked above), aligned and writable per the caller contract.
    unsafe { output.write(effect) };
    status
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_global_add_page(
    state: *mut c_void,
    page: *mut c_void,
) -> i32 {
    if state.is_null() || page.is_null() || !page.addr().is_multiple_of(8) {
        return -1;
    }
    // SAFETY: `state` is non-null (checked above), aligned and exclusive per the caller contract.
    let state = unsafe { &mut *state.cast::<Global>() };
    if state.drained.is_some() || state.pages.try_reserve(1).is_err() {
        return -1;
    }
    // Native facade supplies a fresh, disjoint, page_size-byte arena exactly once.
    if let Some(page) = NonNull::new(page.cast::<u8>()) {
        state.pages.push(page);
        state.offset = 0;
    }
    0
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_global_alloc(
    state: *mut c_void,
    size: u32,
    output: *mut *mut c_void,
) -> i32 {
    if output.is_null() {
        return -1;
    }
    // SAFETY: `output` is non-null (checked above), aligned and writable.
    unsafe {
        output.write(ptr::null_mut());
    }
    if state.is_null() {
        return -1;
    }
    // SAFETY: `state` is non-null (checked above), aligned and exclusive per the caller contract.
    let state = unsafe { &mut *state.cast::<Global>() };
    let Some((size, total)) = state.allocation_size(size) else {
        return -1;
    };
    let Some(page) = state
        .pages
        .last()
        .copied()
        .filter(|_| state.offset <= state.page_size - total)
    else {
        return 1;
    };
    // `offset + total <= page_size` (filtered above), so the 8-byte header and `size` payload
    // bytes fit in the last page (see `Global`); `offset` stays 8-aligned.
    let block = page.as_ptr().wrapping_add(state.offset);
    #[expect(
        clippy::cast_possible_truncation,
        clippy::cast_ptr_alignment,
        reason = "an 8-aligned native block header storing a sub-page uint32_t size"
    )]
    // SAFETY: as above.
    unsafe {
        block.cast::<u32>().write(size as u32)
    };
    // SAFETY: as above.
    unsafe { ptr::write_bytes(block.wrapping_add(8), 0, size) };
    // SAFETY: `output` is non-null (checked above), aligned and writable.
    unsafe { output.write(block.wrapping_add(8).cast()) };
    state.offset += total;
    0
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_global_capacity(state: *const c_void) -> usize {
    if state.is_null() {
        return 0;
    }
    // SAFETY: `state` is non-null (checked above), aligned and initialized per the caller contract.
    let state = unsafe { &*state.cast::<Global>() };
    state.page_size - state.offset
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_global_memory_size(state: *const c_void) -> usize {
    if state.is_null() {
        return 0;
    }
    // SAFETY: `state` is non-null (checked above), aligned and initialized per the caller contract.
    let state = unsafe { &*state.cast::<Global>() };
    state.pages.len().saturating_mul(state.page_size)
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_global_pop_page(state: *mut c_void) -> *mut c_void {
    if state.is_null() {
        return ptr::null_mut();
    }
    // SAFETY: `state` is non-null (checked above), aligned and exclusive per the caller contract.
    let state = unsafe { &mut *state.cast::<Global>() };
    state
        .pop_page()
        .map_or(ptr::null_mut(), |page| page.as_ptr().cast())
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_memory_global_release(state: *mut c_void) -> i32 {
    if state.is_null() {
        return -1;
    }
    // SAFETY: `state` is non-null (checked above), aligned and initialized per the caller contract.
    let value = unsafe { &*state.cast::<Global>() };
    if value.drained.unwrap_or(0) != value.pages.len() {
        return -1;
    }
    // SAFETY: a live, fully drained `Global` from create, released exactly once.
    unsafe { ptr::drop_in_place(state.cast::<Global>()) };
    // SAFETY: allocated with this layout by create; its value was just dropped.
    unsafe { dealloc(state.cast(), Layout::new::<Global>()) };
    0
}

#[cfg(test)]
#[path = "../../../tests/modules/memory/global.rs"]
mod tests;
