//! PHP Scheduler frontend metadata. Zend payloads and execution stay native.
#![cfg_attr(
    not(test),
    deny(
        clippy::undocumented_unsafe_blocks,
        clippy::multiple_unsafe_ops_per_block
    )
)]
mod activation;
mod allocation;
mod autoload;
mod bootstrap;
mod config_state;
mod configure;
mod context;
mod context_metadata;
mod create;
mod deferred;
mod exit;
mod fiber;
mod interrupt;
mod introspection;
mod join;
mod method_catalogue;
mod options;
mod scheduler_callback;
mod scheduler_control;
mod scheduler_phase;
mod scheduler_slot;
mod stats;
mod system;
mod yield_registry;

use std::collections::VecDeque;

/// Only metadata is owned here: tokens are never dereferenced or destroyed.
pub struct SchedulerQueue(VecDeque<Task>);

#[derive(Clone, Copy)]
struct Task {
    token: usize,
    count: i64,
}

/// A popped task belongs to the native caller before any callback can run.
#[repr(C)]
#[derive(Default)]
pub struct SchedulerTask {
    pub token: usize,
    pub repetitions: u64,
}

impl SchedulerQueue {
    fn new() -> Self {
        Self(VecDeque::new())
    }
    fn try_new() -> *mut Self {
        allocation::try_owned(Self::new())
    }
    fn push(&mut self, token: usize, count: i64) {
        self.0.push_back(Task { token, count });
    }
    fn try_push(&mut self, token: usize, count: i64) -> u8 {
        if self.0.try_reserve(1).is_err() {
            return 0;
        }
        self.push(token, count);
        1
    }
    fn pop(&mut self) -> Option<SchedulerTask> {
        self.0.pop_front().map(|task| SchedulerTask {
            token: task.token,
            repetitions: task.count.max(0).unsigned_abs(),
        })
    }
    /// Consume exactly one live owner, after Native payloads have been drained.
    unsafe fn drop_owned(queue: *mut Self) {
        // SAFETY: callers pass an owned queue from `try_owned`, dropped exactly once.
        unsafe { drop(Box::from_raw(queue)) };
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_phpcoroutines_scheduler_new() -> *mut SchedulerQueue {
    Box::into_raw(Box::new(SchedulerQueue::new()))
}

/// # Safety
/// `queue` is a live exclusively owned handle returned by `scheduler_new`.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_scheduler_push(
    queue: *mut SchedulerQueue,
    token: usize,
    count: i64,
) {
    // SAFETY: per this function's `# Safety` contract, `queue` is live, aligned and exclusive.
    unsafe { &mut *queue }.push(token, count);
}

/// Remove a task before returning to native callback/refcount effects. Negative
/// and zero counts produce zero repetitions, matching `for (i=0; i<count; i++)`.
/// # Safety
/// `queue` is live and exclusive; `output` is writable and does not alias it.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_scheduler_pop(
    queue: *mut SchedulerQueue,
    output: *mut SchedulerTask,
) -> u8 {
    // SAFETY: per this function's `# Safety` contract, `queue` is live, aligned and exclusive.
    match unsafe { &mut *queue }.pop() {
        Some(task) => {
            // SAFETY: per this function's `# Safety` contract, `output` is live, aligned and writable.
            unsafe { output.write(task) };
            1
        }
        None => 0,
    }
}

/// # Safety
/// Consume the live handle exactly once, after native payloads have been drained.
/// This drops metadata only and never calls Zend or destroys a token's referent.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_scheduler_drop(queue: *mut SchedulerQueue) {
    // SAFETY: the caller consumes its owned handle once.
    unsafe { SchedulerQueue::drop_owned(queue) };
}

/// Fallible actual-native admission; legacy new/push ABI stays unchanged.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_phpcoroutines_scheduler_try_new() -> *mut SchedulerQueue {
    SchedulerQueue::try_new()
}
/// # Safety
/// Handle is live/exclusive. Failure publishes no new task; native throws after
/// return. Tokens remain opaque, including on capacity/allocation failure.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_scheduler_try_push(
    queue: *mut SchedulerQueue,
    token: usize,
    count: i64,
) -> u8 {
    // SAFETY: per this function's `# Safety` contract, `queue` is live, aligned and exclusive.
    unsafe { &mut *queue }.try_push(token, count)
}
