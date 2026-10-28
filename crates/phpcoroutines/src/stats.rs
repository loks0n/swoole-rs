//! Ordered frontend statistics projection. Runtime reads and Zend writes stay native.
use std::ffi::c_char;

#[repr(C)]
#[derive(Default)]
pub(crate) struct StatsState {
    pub index: u32,
    pub zero_async: u8,
}
#[repr(C)]
pub(crate) struct StatsPlan {
    pub action: u32,
    pub key: *const c_char,
    pub key_length: usize,
    pub zero: u8,
}
const KEYS: [&[u8]; 15] = [
    b"event_num\0",
    b"signal_listener_num\0",
    b"\0",
    b"aio_task_num\0",
    b"aio_worker_num\0",
    b"aio_queue_size\0",
    b"c_stack_size\0",
    b"coroutine_num\0",
    b"coroutine_peak_num\0",
    b"coroutine_last_cid\0",
    b"\0",
    b"iouring_task_num\0",
    b"iouring_sq_usage_percent\0",
    b"iouring_waiting_task_num\0",
    b"\0",
];
/// Presence observations belong only to the previously requested native getter.
/// No runtime pointer or counter enters Rust; native reads retain original order.
/// # Safety
/// `state` is exclusive writable native stack POD, initially zeroed and preserved
/// between steps. `has_iouring` is the actual native configuration capability.
#[unsafe(no_mangle)]
pub(crate) unsafe extern "C" fn swr_v1_phpcoroutines_stats(
    state: *mut StatsState,
    observation: u8,
    has_iouring: u8,
) -> StatsPlan {
    // SAFETY: per this function's `# Safety` contract, `state` is live, aligned and exclusive.
    let state = unsafe { &mut *state };
    if state.index == 3 {
        state.zero_async = u8::from(observation == 0);
    }
    if state.index == 10 && has_iouring == 0 || state.index == 11 && observation == 0 {
        state.index = 14;
    }
    let index = state.index.min(14) as usize;
    let key = KEYS[index];
    let action = if index == 14 {
        0
    } else {
        u32::try_from(index + 1).unwrap_or(0)
    };
    state.index = (state.index + 1).min(14);
    StatsPlan {
        action,
        key: key.as_ptr().cast(),
        key_length: key.len() - 1,
        zero: u8::from((3..=5).contains(&index) && state.zero_async != 0),
    }
}
