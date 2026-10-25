//! Fixture-only actual allocator failures; absent from ordinary library builds.
use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::Cell;
use std::ptr;

#[derive(Clone, Copy)]
struct State {
    site: u32,
    remaining: usize,
    attempts: u32,
    failures: u32,
    failed_site: u32,
}
const IDLE: State = State {
    site: 0,
    remaining: usize::MAX,
    attempts: 0,
    failures: 0,
    failed_site: 0,
};
thread_local! {
    static STATE: Cell<State> = const { Cell::new(IDLE) };
}

fn fail_allocation() -> bool {
    STATE.with(|cell| {
        let mut state = cell.get();
        if state.site == 0 || state.remaining == usize::MAX {
            return false;
        }
        state.attempts += 1;
        let fail = state.remaining == 0;
        if fail {
            state.failures += 1;
            state.failed_site = state.site;
            state.remaining = usize::MAX; // One failure; native handler retry may succeed.
        } else {
            state.remaining -= 1;
        }
        cell.set(state);
        fail
    })
}

struct FaultAllocator;
#[global_allocator]
static ALLOCATOR: FaultAllocator = FaultAllocator;
unsafe impl GlobalAlloc for FaultAllocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        if fail_allocation() {
            ptr::null_mut()
        } else {
            System.alloc(layout)
        }
    }
    unsafe fn realloc(&self, pointer: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        if fail_allocation() {
            ptr::null_mut()
        } else {
            System.realloc(pointer, layout, size)
        }
    }
    unsafe fn dealloc(&self, pointer: *mut u8, layout: Layout) {
        System.dealloc(pointer, layout);
    }
}

pub(crate) struct Scope(u32);
impl Scope {
    pub(crate) fn enter(site: u32) -> Self {
        STATE.with(|cell| {
            let mut state = cell.get();
            let previous = state.site;
            state.site = site;
            cell.set(state);
            Self(previous)
        })
    }
}
impl Drop for Scope {
    fn drop(&mut self) {
        STATE.with(|cell| {
            let mut state = cell.get();
            state.site = self.0;
            cell.set(state);
        });
    }
}

#[no_mangle]
pub extern "C" fn sw_rs_http2_test_queue_failure_after(remaining: usize) {
    STATE.with(|cell| cell.set(State { remaining, ..IDLE }));
}
#[repr(C)]
pub struct Http2TestQueueFaultState {
    site: u32,
    failed_site: u32,
    attempts: u32,
    failures: u32,
}
/// # Safety
/// `out` points to writable fixture state storage. This export exists only with cfg(test).
#[no_mangle]
pub unsafe extern "C" fn sw_rs_http2_test_queue_fault_state(out: *mut Http2TestQueueFaultState) {
    STATE.with(|cell| {
        let state = cell.get();
        out.write(Http2TestQueueFaultState {
            site: state.site,
            failed_site: state.failed_site,
            attempts: state.attempts,
            failures: state.failures,
        });
    });
}
