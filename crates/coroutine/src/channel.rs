//! Coupled inline Channel state and authoritative queue operations. Native owns
//! every token pointee, timer, trace, callback and context effect after return.
use crate::{ChannelCursor, ChannelTokens, channel_step};
use std::ffi::c_void;
use std::ptr;

#[repr(C)]
#[derive(Clone, Copy)]
pub struct ChannelState {
    pub capacity: usize,
    pub closed: u8,
    pub error: i32,
}

#[repr(C)]
pub struct ChannelView {
    pub length: usize,
    pub producers: usize,
    pub consumers: usize,
    pub error: i32,
    pub closed: u8,
    pub full: u8,
    pub empty: u8,
}

#[repr(C)]
pub struct OwnedChannelCursor {
    pub step: ChannelCursor,
    pub pending: u32,
}

#[repr(C)]
pub struct ChannelAction {
    pub action: i32,
    pub token: *mut c_void,
}

#[repr(C)]
pub struct ChannelWaiter {
    pub status: i32,
    pub role: u32,
    pub token: *mut c_void,
}

/// Whole waiter role selection and FIFO mutation. Original enqueue/pop treat
/// PRODUCER as special; original removal treats CONSUMER as special instead.
/// Native alone traces, yields, resumes and owns all pointed-to objects.
/// # Safety
/// Both queues are distinct live exclusive owners. Tokens are opaque. No borrow
/// survives return; the caller performs Native effects only after this call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_channel_waiter(
    producers: *mut ChannelTokens,
    consumers: *mut ChannelTokens,
    operation: u32,
    role: u32,
    token: *mut c_void,
) -> ChannelWaiter {
    let producer = if operation == 1 { role != 2 } else { role == 1 };
    let mut result = ChannelWaiter {
        status: 0,
        role: if producer { 1 } else { 2 },
        token: ptr::null_mut(),
    };
    // Reject an unknown operation before observing either queue.
    if operation > 2 {
        result.status = -4;
        return result;
    }
    let queue = unsafe { &mut *if producer { producers } else { consumers } };
    match operation {
        0 => {
            if queue.try_push(token).is_err() {
                result.status = -5;
            }
        }
        1 => queue.0.retain(|&entry| entry != token),
        _ => match queue.0.pop_front() {
            Some(token) => result.token = token,
            None => result.status = -4,
        },
    }
    result
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_channel_state_new(capacity: usize) -> ChannelState {
    ChannelState {
        capacity,
        closed: 0,
        error: 0,
    }
}

/// # Safety
/// State and all three token owners are live initialized readable storage with
/// serialized access. Native copies this POD only, never its Native pointees.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_channel_view_read(
    state: *const ChannelState,
    data: *const ChannelTokens,
    producers: *const ChannelTokens,
    consumers: *const ChannelTokens,
) -> ChannelView {
    let state = unsafe { &*state };
    let length = unsafe { &*data }.0.len();
    ChannelView {
        length,
        producers: unsafe { &*producers }.0.len(),
        consumers: unsafe { &*consumers }.0.len(),
        error: state.error,
        closed: state.closed,
        full: u8::from(length == state.capacity),
        empty: u8::from(length == 0),
    }
}

/// Whole optional data removal. A stored null and absent data both return null,
/// as the original public pop_data method does; no Native payload is destroyed.
/// # Safety
/// Data is a live exclusive token owner; no borrow survives this call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_channel_pop_data(data: *mut ChannelTokens) -> *mut c_void {
    unsafe { &mut *data }
        .0
        .pop_front()
        .unwrap_or(ptr::null_mut())
}

/// Whole queue-aware operation, with the legacy phase/error/fairness algorithm.
/// Pending publication means Native must first execute the requested close trace.
/// Allocation refusal returns -5; Native raises only after Rust returns.
/// # Safety
/// Cursor is independent exclusive initialized zeroed storage, state is a live
/// initialized inline POD, and queues are live distinct module-owned handles.
/// Shared observations and selected queue mutations end before Native effects.
/// Op remains fixed. External facts are freshly copied timer/cancel/timeout bits.
/// Tokens are opaque identities; Native owns every pointee and effect/lifetime.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_channel_owned_step(
    cursor: *mut OwnedChannelCursor,
    state: *mut ChannelState,
    data: *mut ChannelTokens,
    producers: *mut ChannelTokens,
    consumers: *mut ChannelTokens,
    op: u32,
    external: u32,
    input: *mut c_void,
) -> ChannelAction {
    let cursor = unsafe { &mut *cursor };
    let state = unsafe { &mut *state };
    if cursor.pending != 0 {
        state.closed = 1;
        cursor.pending = 0;
    }
    let empty = unsafe { &*data }.0.is_empty();
    let full = unsafe { &*data }.0.len() == state.capacity;
    let waiting_producers = !unsafe { &*producers }.0.is_empty();
    let waiting_consumers = !unsafe { &*consumers }.0.is_empty();
    let facts = (u32::from(state.closed != 0) * crate::CLOSED)
        | (u32::from(empty) * crate::EMPTY)
        | (u32::from(full) * crate::FULL)
        | (u32::from(waiting_producers) * crate::PRODUCERS)
        | (u32::from(waiting_consumers) * crate::CONSUMERS)
        | (external
            & (crate::POSITIVE_TIMEOUT | crate::HAS_TIMER | crate::CANCELED | crate::TIMEDOUT));
    let action = channel_step(&mut cursor.step, op, facts);
    let mut result = ChannelAction {
        action,
        token: ptr::null_mut(),
    };
    match action {
        crate::PUBLISH_CLOSED => cursor.pending = 1,
        crate::TRANSFER if op == 0 => {
            if unsafe { &mut *data }.try_push(input).is_err() {
                result.action = -5;
            }
        }
        crate::TRANSFER => {
            if let Some(token) = unsafe { &mut *data }.0.pop_front() {
                result.token = token;
            } else {
                result.action = -4;
            }
        }
        crate::WAKE_PRODUCER => {
            if let Some(token) = unsafe { &mut *producers }.0.pop_front() {
                result.token = token;
            } else {
                result.action = -4;
            }
        }
        crate::WAKE_CONSUMER => {
            if let Some(token) = unsafe { &mut *consumers }.0.pop_front() {
                result.token = token;
            } else {
                result.action = -4;
            }
        }
        -3..=-1 if op != 2 => state.error = action,
        _ => {}
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        swr_v1_channel_tokens_free, swr_v1_channel_tokens_new, swr_v1_channel_tokens_push,
    };

    struct Fixture {
        state: ChannelState,
        queues: [*mut ChannelTokens; 3],
    }
    impl Fixture {
        fn new(capacity: usize) -> Self {
            let queues = std::array::from_fn(|_| swr_v1_channel_tokens_new());
            assert!(queues.iter().all(|p| !p.is_null()));
            Self {
                state: swr_v1_channel_state_new(capacity),
                queues,
            }
        }
        fn step(
            &mut self,
            cursor: &mut OwnedChannelCursor,
            op: u32,
            facts: u32,
            input: *mut c_void,
        ) -> ChannelAction {
            unsafe {
                swr_v1_channel_owned_step(
                    cursor,
                    &mut self.state,
                    self.queues[0],
                    self.queues[1],
                    self.queues[2],
                    op,
                    facts,
                    input,
                )
            }
        }
        fn view(&self) -> ChannelView {
            unsafe {
                swr_v1_channel_view_read(
                    &self.state,
                    self.queues[0],
                    self.queues[1],
                    self.queues[2],
                )
            }
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            for queue in self.queues {
                unsafe { swr_v1_channel_tokens_free(queue) };
            }
        }
    }
    fn cursor() -> OwnedChannelCursor {
        OwnedChannelCursor {
            step: ChannelCursor { phase: 0 },
            pending: 0,
        }
    }

    #[test]
    fn waiter_role_branches_fifo_and_remove_all_preserve_opaque_identity() {
        let f = Fixture::new(1);
        let mut bytes = [11_u8, 22];
        let a = ptr::from_mut(&mut bytes[0]).cast();
        let b = ptr::from_mut(&mut bytes[1]).cast();
        let call = |op, role, token| unsafe {
            swr_v1_channel_waiter(f.queues[1], f.queues[2], op, role, token)
        };
        for role in [1, 2, 0] {
            let selected = if role == 1 { 1 } else { 2 };
            for token in [a, ptr::null_mut(), b, a] {
                let out = call(0, role, token);
                assert_eq!((out.status, out.role), (0, selected));
            }
            // Removal's OTHER branch differs from enqueue/pop. Preserve it,
            // including all duplicates, without interpreting a token pointee.
            let remove_role = if selected == 1 { 0 } else { 2 };
            let removed = call(1, remove_role, a);
            assert_eq!((removed.status, removed.role), (0, selected));
            for token in [ptr::null_mut(), b] {
                let out = call(2, role, ptr::null_mut());
                assert_eq!((out.status, out.role, out.token), (0, selected, token));
            }
            assert_eq!((f.view().producers, f.view().consumers), (0, 0));
        }
        assert_eq!(bytes, [11, 22]);
    }

    #[test]
    fn direct_fifo_null_capacity_zero_and_passive_copy_remain_exact() {
        let mut zero = Fixture::new(0);
        assert_eq!((zero.view().empty, zero.view().full), (1, 1));
        assert_eq!(
            zero.step(&mut cursor(), 0, 0, ptr::null_mut()).action,
            crate::YIELD
        );
        let mut f = Fixture::new(2);
        let mut byte = 7u8;
        let token = (&raw mut byte).cast();
        for input in [ptr::null_mut(), token] {
            let mut c = cursor();
            assert_eq!(f.step(&mut c, 0, 0, input).action, crate::TRANSFER);
            assert_eq!(f.step(&mut c, 0, 0, input).action, crate::DONE);
        }
        assert_eq!((f.view().length, f.view().full), (2, 1));
        let copy = f.state;
        assert_eq!((copy.capacity, copy.closed, copy.error), (2, 0, 0));
        for expected in [ptr::null_mut(), token] {
            let mut c = cursor();
            let plan = f.step(&mut c, 1, 0, ptr::null_mut());
            assert_eq!((plan.action, plan.token), (crate::TRANSFER, expected));
            assert_eq!(f.step(&mut c, 1, 0, ptr::null_mut()).action, crate::DONE);
        }
        assert_eq!((f.view().length, f.view().empty, f.view().error), (0, 1, 0));
        assert_eq!(byte, 7);
    }

    #[test]
    fn close_publication_and_role_order_keep_sticky_error() {
        let mut f = Fixture::new(1);
        let mut tokens = [1u8, 2, 3];
        let ptrs = tokens
            .iter_mut()
            .map(|p| (p as *mut u8).cast())
            .collect::<Vec<_>>();
        unsafe {
            assert_eq!(swr_v1_channel_tokens_push(f.queues[1], ptrs[0]), 0);
            assert_eq!(swr_v1_channel_tokens_push(f.queues[1], ptrs[1]), 0);
            assert_eq!(swr_v1_channel_tokens_push(f.queues[2], ptrs[2]), 0);
        }
        let mut c = cursor();
        assert_eq!(
            f.step(&mut c, 2, 0, ptr::null_mut()).action,
            crate::PUBLISH_CLOSED
        );
        assert_eq!(f.state.closed, 0); // Native trace must finish first.
        for (action, token) in [
            (crate::WAKE_PRODUCER, ptrs[0]),
            (crate::WAKE_PRODUCER, ptrs[1]),
            (crate::WAKE_CONSUMER, ptrs[2]),
        ] {
            let plan = f.step(&mut c, 2, 0, ptr::null_mut());
            assert_eq!((plan.action, plan.token), (action, token));
            assert_eq!(f.state.closed, 1);
        }
        assert_eq!(f.step(&mut c, 2, 0, ptr::null_mut()).action, crate::DONE);
        assert_eq!(f.view().error, 0);
        assert_eq!(f.step(&mut cursor(), 0, 0, ptr::null_mut()).action, -2);
        assert_eq!(f.view().error, -2);
        assert_eq!(f.step(&mut cursor(), 2, 0, ptr::null_mut()).action, -2);
        assert_eq!(f.view().error, -2); // Already-closed close never changes error.
        assert_eq!(tokens, [1, 2, 3]);
    }

    #[test]
    fn copied_wait_facts_keep_timer_cancel_precedence_and_success_sticky_error() {
        let mut f = Fixture::new(1);
        assert_eq!(
            f.step(&mut cursor(), 0, 0, ptr::null_mut()).action,
            crate::TRANSFER
        );
        let mut wait = cursor();
        for (facts, expected) in [
            (crate::POSITIVE_TIMEOUT, crate::ARM_TIMER),
            (crate::HAS_TIMER, crate::YIELD),
            (crate::HAS_TIMER, crate::DELETE),
            (crate::CANCELED | crate::TIMEDOUT, -3),
        ] {
            assert_eq!(
                f.step(&mut wait, 0, facts, ptr::null_mut()).action,
                expected
            );
        }
        assert_eq!((f.view().length, f.view().error), (1, -3));
        assert_eq!(
            f.step(&mut cursor(), 1, 0, ptr::null_mut()).action,
            crate::TRANSFER
        );
        assert_eq!((f.view().length, f.view().error), (0, -3));
    }
}
