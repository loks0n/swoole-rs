//! OS support policy. All storage, syscalls, threads and callbacks remain native.
mod read_content;
pub use read_content::{ReadContentState, swr_v1_os_read_content_next};
mod file_content;
pub use file_content::{FileContentState, swr_v1_os_file_content_next};
mod sendfile_fallback;
pub use sendfile_fallback::{SendfileFallbackState, swr_v1_os_sendfile_fallback_next};
mod random_bytes;
pub use random_bytes::{RandomBytesState, swr_v1_os_random_bytes_next};
mod file_line;
pub use file_line::{FileLineResult, swr_v1_os_file_line_result};
mod file_io;
pub use file_io::{FileIoState, swr_v1_os_file_io_next};
#[repr(C)]
#[derive(Debug, Copy, Clone, PartialEq)]
pub struct PoolConfig {
    pub core: usize,
    pub workers: usize,
    pub wait: f64,
    pub idle: f64,
}
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_os_pool_config(
    cpu: usize,
    core: usize,
    workers: usize,
    wait: f64,
    idle: f64,
) -> PoolConfig {
    let core = if core == 0 { cpu } else { core.max(1) };
    PoolConfig {
        core,
        workers: if workers == 0 {
            cpu.wrapping_mul(8)
        } else {
            workers.max(core)
        },
        wait: if wait == 0.0 { 0.001 } else { wait },
        idle: if idle == 0.0 { 1.0 } else { idle },
    }
}
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_os_pool_expand(
    waiting: usize,
    threads: usize,
    workers: usize,
    threshold: f64,
    age: f64,
) -> usize {
    usize::from(waiting == 0 && threads < workers && threshold > 0.0 && age > threshold)
}
/// 0 invoke native handler, 1 missing handler, 2 canceled. Missing wins.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_os_event_action(handler: bool, canceled: bool) -> i32 {
    if !handler {
        1
    } else if canceled {
        2
    } else {
        0
    }
}
/// One worker iteration after the native wait/pop. 0 wait, 1 invoke handler,
/// 2 bad request, 3 canceled, 4 retire idle worker. Event handling wins timeout.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_os_worker_action(
    event: bool,
    handler: bool,
    canceled: bool,
    timeout: bool,
    closing: usize,
) -> i32 {
    if event {
        swr_v1_os_event_action(handler, canceled) + 1
    } else if timeout && closing == 0 {
        4
    } else {
        0
    }
}

/// Native errno values are reduced to flags before calling; 0 stop, 1 retry, 2 warn.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_os_fs_error(result: i64, retry: bool) -> i32 {
    if result == 0 {
        0
    } else if retry {
        1
    } else {
        2
    }
}
/// Empty takes priority over too large. 0 permitted, 1 empty, 2 too large.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_os_content(length: u64, maximum: u64) -> i32 {
    if length == 0 {
        1
    } else if length > maximum {
        2
    } else {
        0
    }
}
/// Return 0 for a regular file, 1 for failed fstat, or 2 for a non-regular file.
/// Syscall execution, errno publication and returned size remain native.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_os_file_size_action(
    fstat_succeeded: bool,
    mode: u64,
    type_mask: u64,
    regular_type: u64,
) -> i32 {
    if !fstat_succeeded {
        1
    } else if mode & type_mask != regular_type {
        2
    } else {
        0
    }
}
/// Returns terminator-inclusive length, or zero when there is no terminator.
/// # Safety
/// data points to exactly length initialized readable bytes, or length is zero.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_os_line_end(data: *const u8, length: usize) -> usize {
    if length == 0 {
        return 0;
    }
    // The native read already established this initialized prefix.
    let bytes = unsafe { std::slice::from_raw_parts(data, length) };
    bytes
        .iter()
        .position(|&b| b == 0 || b == b'\n')
        .map_or(0, |n| n + 1)
}
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_os_permissions(perms: i32) -> i32 {
    if perms <= 0 || perms >= 0o1000 {
        0o666
    } else {
        perms
    }
}
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_os_queue_flags(flags: i32, blocking: bool, nowait: i32) -> i32 {
    if blocking {
        flags & !nowait
    } else {
        flags | nowait
    }
}
/// Msgsnd failed: 1 retry, 2 quiet final failure, 3 warned final failure.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_os_queue_error(interrupted: bool, again: bool) -> i32 {
    if interrupted {
        1
    } else if again {
        2
    } else {
        3
    }
}
/// The entropy loop retries only EINTR/EAGAIN on result -1, otherwise stops.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_os_random_error(result: i64, interrupted: bool, again: bool) -> bool {
    result == -1 && (interrupted || again)
}
/// Darwin/BSD sendfile after native offset update: retry, error, success, warn.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_os_sendfile_action(result: i64, interrupted: bool) -> i32 {
    if result == -1 {
        if interrupted { 1 } else { 2 }
    } else if result == 0 {
        0
    } else {
        3
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn pool_preserves_independent_defaults() {
        assert_eq!(
            swr_v1_os_pool_config(2, 64, 0, 0., 0.),
            PoolConfig {
                core: 64,
                workers: 16,
                wait: 0.001,
                idle: 1.
            }
        );
        assert_eq!(
            swr_v1_os_pool_config(2, 64, 1, -1., 0.5),
            PoolConfig {
                core: 64,
                workers: 64,
                wait: -1.,
                idle: 0.5
            }
        );
        assert_eq!(swr_v1_os_pool_expand(0, 1, 8, 0.1, 0.1), 0);
        assert_eq!(swr_v1_os_pool_expand(0, 1, 8, 0.1, 0.2), 1);
        assert_eq!(swr_v1_os_pool_expand(1, 1, 8, 0.1, 0.2), 0);
        assert_eq!(
            swr_v1_os_pool_expand(0, usize::MAX - 1, usize::MAX, 0.1, 0.2),
            1
        );
        assert_eq!(
            swr_v1_os_pool_expand(0, usize::MAX, usize::MAX, 0.1, 0.2),
            0
        );
        assert_eq!(swr_v1_os_event_action(false, true), 1);
        assert_eq!(swr_v1_os_worker_action(true, false, true, true, 0), 2);
        assert_eq!(swr_v1_os_worker_action(false, false, false, true, 0), 4);
        assert_eq!(swr_v1_os_worker_action(false, false, false, true, 1), 0);
    }
    #[test]
    fn file_size_action_preserves_native_stat_and_mode_outcomes() {
        for (succeeded, mode, mask, regular, expected) in [
            (false, 0, 0o170000, 0o100000, 1),
            (false, 0o040755, 0o170000, 0o100000, 1),
            (true, 0o100644, 0o170000, 0o100000, 0),
            (true, 0o040755, 0o170000, 0o100000, 2),
            (true, 0o020600, 0o170000, 0o100000, 2),
        ] {
            assert_eq!(
                swr_v1_os_file_size_action(succeeded, mode, mask, regular),
                expected
            );
        }
    }

    #[test]
    fn file_and_ipc_priorities() {
        assert_eq!(swr_v1_os_fs_error(0, true), 0);
        assert_eq!(swr_v1_os_fs_error(-1, true), 1);
        assert_eq!(swr_v1_os_content(0, 0), 1);
        assert_eq!(swr_v1_os_content(1, 0), 2);
        assert_eq!(unsafe { swr_v1_os_line_end(b"ab\0cd\n".as_ptr(), 6) }, 3);
        assert_eq!(unsafe { swr_v1_os_line_end(b"abc".as_ptr(), 3) }, 0);
        assert_eq!(swr_v1_os_permissions(0o1000), 0o666);
        assert_eq!(swr_v1_os_queue_error(true, true), 1);
        assert_eq!(swr_v1_os_sendfile_action(-1, true), 1);
    }
}

/// Sole private queue container. Native owns/dereferences/frees all event tokens.
/// All accesses are serialized by the existing native event_mutex.
pub struct OsQueue {
    entries: std::collections::VecDeque<usize>,
}

#[repr(C)]
#[derive(Debug, Copy, Clone, Default, PartialEq, Eq)]
pub struct QueueItem {
    pub token: usize,
    pub present: bool,
}

/// Fallible handle allocation; no Box allocation failure handler or native callback.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_os_queue_create() -> *mut OsQueue {
    let memory =
        unsafe { std::alloc::alloc(std::alloc::Layout::new::<OsQueue>()) }.cast::<OsQueue>();
    if !memory.is_null() {
        unsafe {
            memory.write(OsQueue {
                entries: std::collections::VecDeque::new(),
            });
        }
    }
    memory
}

/// Drop only pointer-token backing storage, never any native payload.
/// # Safety
/// queue is null or a live handle from create, exclusively owned and unused by
/// other threads. Every live handle is destroyed exactly once, after worker joins.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_os_queue_destroy(queue: *mut OsQueue) {
    if !queue.is_null() {
        unsafe {
            std::ptr::drop_in_place(queue);
            std::alloc::dealloc(queue.cast(), std::alloc::Layout::new::<OsQueue>());
        }
    }
}

/// Fallible enqueue. Failure leaves the queue unchanged; zero is a valid token.
/// # Safety
/// queue is null or a live handle, with exclusive native mutex custody.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_os_queue_push(queue: *mut OsQueue, token: usize) -> bool {
    let Some(queue) = (unsafe { queue.as_mut() }) else {
        return false;
    };
    if queue.entries.try_reserve(1).is_err() {
        return false;
    }
    queue.entries.push_back(token);
    true
}

/// # Safety
/// queue is null or live, with exclusive native mutex custody; no native token
/// is dereferenced or deleted. An empty result is distinct from stored token0.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_os_queue_pop(queue: *mut OsQueue) -> QueueItem {
    let value = unsafe { queue.as_mut() }.and_then(|q| q.entries.pop_front());
    QueueItem {
        token: value.unwrap_or(0),
        present: value.is_some(),
    }
}

/// # Safety
/// queue is null or live, under the same native mutex. No returned token retains
/// a Rust borrow; native may inspect its own event only after this function returns.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_os_queue_front(queue: *const OsQueue) -> QueueItem {
    let value = unsafe { queue.as_ref() }.and_then(|q| q.entries.front().copied());
    QueueItem {
        token: value.unwrap_or(0),
        present: value.is_some(),
    }
}

/// # Safety
/// queue is null or a live handle protected by the existing native mutex.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_os_queue_count(queue: *const OsQueue) -> usize {
    unsafe { queue.as_ref() }.map_or(0, |q| q.entries.len())
}

#[cfg(test)]
mod queue_tests {
    use super::*;
    use std::alloc::{GlobalAlloc, Layout, System};
    use std::cell::Cell;
    thread_local! { static FAIL_NEXT: Cell<bool> = const { Cell::new(false) }; }
    struct FaultAllocator;
    fn fail() -> bool {
        FAIL_NEXT
            .try_with(|flag| flag.replace(false))
            .unwrap_or(false)
    }
    unsafe impl GlobalAlloc for FaultAllocator {
        unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
            if fail() {
                std::ptr::null_mut()
            } else {
                unsafe { System.alloc(layout) }
            }
        }
        unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
            if fail() {
                std::ptr::null_mut()
            } else {
                unsafe { System.alloc_zeroed(layout) }
            }
        }
        unsafe fn realloc(&self, pointer: *mut u8, layout: Layout, size: usize) -> *mut u8 {
            if fail() {
                std::ptr::null_mut()
            } else {
                unsafe { System.realloc(pointer, layout, size) }
            }
        }
        unsafe fn dealloc(&self, pointer: *mut u8, layout: Layout) {
            unsafe { System.dealloc(pointer, layout) }
        }
    }
    #[global_allocator]
    static TEST_ALLOCATOR: FaultAllocator = FaultAllocator;
    #[test]
    fn allocation_failure_is_fallible_and_transactional() {
        FAIL_NEXT.with(|flag| flag.set(true));
        assert!(swr_v1_os_queue_create().is_null());
        let queue = swr_v1_os_queue_create();
        assert!(!queue.is_null());
        unsafe {
            FAIL_NEXT.with(|flag| flag.set(true));
            assert!(!swr_v1_os_queue_push(queue, 99));
            assert_eq!(swr_v1_os_queue_count(queue), 0);
            assert!(swr_v1_os_queue_push(queue, 0));
            while (*queue).entries.len() < (*queue).entries.capacity() {
                assert!(swr_v1_os_queue_push(queue, usize::MAX));
            }
            let length = swr_v1_os_queue_count(queue);
            FAIL_NEXT.with(|flag| flag.set(true));
            assert!(!swr_v1_os_queue_push(queue, 99));
            assert_eq!(swr_v1_os_queue_count(queue), length);
            assert_eq!(
                swr_v1_os_queue_pop(queue),
                QueueItem {
                    token: 0,
                    present: true
                }
            );
            swr_v1_os_queue_destroy(queue);
            swr_v1_os_queue_destroy(std::ptr::null_mut());
        }
    }
    #[test]
    fn empty_and_zero_token_are_distinct() {
        let queue = swr_v1_os_queue_create();
        assert!(!queue.is_null());
        unsafe {
            assert_eq!(swr_v1_os_queue_pop(queue), QueueItem::default());
            assert!(swr_v1_os_queue_push(queue, 0));
            assert_eq!(
                swr_v1_os_queue_front(queue),
                QueueItem {
                    token: 0,
                    present: true
                }
            );
            assert_eq!(
                swr_v1_os_queue_pop(queue),
                QueueItem {
                    token: 0,
                    present: true
                }
            );
            assert_eq!(swr_v1_os_queue_pop(queue), QueueItem::default());
            swr_v1_os_queue_destroy(queue);
        }
    }
}
