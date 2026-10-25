//! One externally native-owned container; raw payloads never acquire Rust custody.
use std::alloc::{alloc, dealloc, Layout};
use std::collections::VecDeque;
use std::ffi::c_void;
use std::ptr;

type SendQueue = VecDeque<*mut c_void>;

unsafe fn allocate_queue(allocator: unsafe fn(Layout) -> *mut u8) -> *mut c_void {
    let memory = allocator(Layout::new::<SendQueue>()).cast::<SendQueue>();
    if !memory.is_null() {
        ptr::write(memory, SendQueue::new());
    }
    memory.cast()
}

fn try_push(queue: &mut SendQueue, payload: *mut c_void, reserve: usize) -> bool {
    if queue.try_reserve(reserve).is_err() {
        return false;
    }
    queue.push_back(payload);
    true
}

/// Returns a sole externally owned opaque container, or NULL on allocation failure.
#[no_mangle]
pub extern "C" fn sw_rs_http2_send_queue_new() -> *mut c_void {
    #[cfg(test)]
    let _scope = crate::queue_faults::Scope::enter(1);
    // Internal allocation has no PHP callbacks; no native payload is constructed here.
    unsafe { allocate_queue(alloc) }
}

/// # Safety
/// `handle` is NULL or a live sole-owned queue, released exactly once with no active calls.
#[no_mangle]
pub unsafe extern "C" fn sw_rs_http2_send_queue_delete(handle: *mut c_void) {
    if !handle.is_null() {
        let queue = handle.cast::<SendQueue>();
        // Dropping raw pointer cells cannot invoke a Zend/native payload destructor.
        ptr::drop_in_place(queue);
        dealloc(queue.cast(), Layout::new::<SendQueue>());
    }
}

/// # Safety
/// `handle` is NULL or a live queue with exclusive access for this call.
#[no_mangle]
pub unsafe extern "C" fn sw_rs_http2_send_queue_len(handle: *const c_void) -> usize {
    handle
        .cast::<SendQueue>()
        .as_ref()
        .map_or(0, SendQueue::len)
}

/// Returns a copied native pointer; no Rust front reference escapes this call.
///
/// # Safety
/// `handle` is NULL or a live queue with exclusive access for this call.
#[no_mangle]
pub unsafe extern "C" fn sw_rs_http2_send_queue_front(handle: *const c_void) -> *mut c_void {
    handle
        .cast::<SendQueue>()
        .as_ref()
        .and_then(SendQueue::front)
        .copied()
        .unwrap_or(ptr::null_mut())
}

/// # Safety
/// `handle` is a live sole-owned queue with exclusive access. `payload` is non-NULL
/// and stays valid through its native uses, including suspended/reentrant sends.
/// Payload custody stays native; NULL is reserved as the empty-front sentinel.
#[no_mangle]
pub unsafe extern "C" fn sw_rs_http2_send_queue_push(
    handle: *mut c_void,
    payload: *mut c_void,
) -> u32 {
    #[cfg(test)]
    let _scope = crate::queue_faults::Scope::enter(2);
    match handle.cast::<SendQueue>().as_mut() {
        Some(queue) => u32::from(try_push(queue, payload, 1)),
        None => 0,
    }
}

/// Removes only a pointer cell. Native code releases its payload after this call returns.
///
/// # Safety
/// `handle` is NULL or a live sole-owned queue with exclusive access.
#[no_mangle]
pub unsafe extern "C" fn sw_rs_http2_send_queue_pop(handle: *mut c_void) {
    if let Some(queue) = handle.cast::<SendQueue>().as_mut() {
        queue.pop_front();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::Cell;
    use std::rc::Rc;

    #[test]
    fn native_token_fifo_growth_wrap_and_copied_front() {
        unsafe {
            let handle = sw_rs_http2_send_queue_new();
            assert!(!handle.is_null());
            let mut expected = Vec::new();
            for serial in 1..20_000usize {
                let token = ptr::without_provenance_mut(serial);
                assert_eq!(sw_rs_http2_send_queue_push(handle, token), 1);
                expected.push(token);
                let copied = sw_rs_http2_send_queue_front(handle);
                if serial % 3 != 0 {
                    assert_eq!(copied, expected.remove(0));
                    sw_rs_http2_send_queue_pop(handle);
                }
                assert_eq!(sw_rs_http2_send_queue_len(handle), expected.len());
                // Growth/movement of pointer cells must not invalidate the copied native token.
                if !expected.is_empty() && serial % 3 == 0 {
                    assert_eq!(copied, expected[0]);
                }
            }
            for token in expected {
                assert_eq!(sw_rs_http2_send_queue_front(handle), token);
                sw_rs_http2_send_queue_pop(handle);
            }
            assert_eq!(sw_rs_http2_send_queue_len(handle), 0);
            assert!(sw_rs_http2_send_queue_front(handle).is_null());
            sw_rs_http2_send_queue_delete(handle);
        }
    }

    #[test]
    fn allocation_and_capacity_failure_leave_payload_publication_unchanged() {
        unsafe fn unavailable(_: Layout) -> *mut u8 {
            ptr::null_mut()
        }
        assert!(unsafe { allocate_queue(unavailable) }.is_null());
        let mut queue = SendQueue::new();
        let first = ptr::dangling_mut::<c_void>();
        assert!(try_push(&mut queue, first, 1));
        assert!(!try_push(
            &mut queue,
            ptr::without_provenance_mut(2),
            usize::MAX
        ));
        assert_eq!(queue.len(), 1);
        assert_eq!(queue.front().copied(), Some(first));
    }

    #[test]
    fn container_drop_does_not_drop_native_payloads() {
        struct NativePayload(Rc<Cell<usize>>);
        impl Drop for NativePayload {
            fn drop(&mut self) {
                self.0.set(self.0.get() + 1);
            }
        }
        let dropped = Rc::new(Cell::new(0));
        unsafe {
            let handle = sw_rs_http2_send_queue_new();
            assert!(!handle.is_null());
            let mut payloads = Vec::new();
            for _ in 0..8 {
                let payload = Box::into_raw(Box::new(NativePayload(dropped.clone())));
                assert_eq!(sw_rs_http2_send_queue_push(handle, payload.cast()), 1);
                payloads.push(payload);
            }
            sw_rs_http2_send_queue_delete(handle);
            assert_eq!(dropped.get(), 0);
            for payload in payloads {
                drop(Box::from_raw(payload));
            }
        }
        assert_eq!(dropped.get(), 8);
    }
}
