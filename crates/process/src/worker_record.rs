//! The server's `Worker` record, whose layout Rust owns (`#[repr(C)]`) so the
//! `sw_shm`-backed worker array every process maps is defined here, and the scalar
//! process fields (pid/status/type/id) move behind accessors one at a time. The C++
//! `swoole::Worker` keeps its methods and pointer/atomic fields; a `static_assert`
//! in the patch locks `sizeof`/`offsetof` to this layout, so a mismatch fails the
//! build rather than corrupting shared memory. See #629.

use std::ffi::{c_int, c_void};

/// Byte-exact mirror of `swoole::Worker` (`include/swoole_process_pool.h`). Field order,
/// types and padding match the pinned C++ struct; the pointer and atomic fields are
/// opaque storage here (owned by C++ for now). Only the scalar process fields are
/// migrated behind the accessors below.
#[repr(C)]
pub struct WorkerRecord {
    pid: c_int,
    id: u32,
    pool: *mut c_void,
    queue: *mut c_void,
    shared: bool,
    redirect_stdout: bool,
    redirect_stdin: bool,
    redirect_stderr: bool,
    status: u8,
    kind: u8,
    msgqueue_mode: u8,
    child_process: u8,
    concurrency: u32,
    start_time: i64,
    dispatch_count: i64,
    request_count: i64,
    response_count: i64,
    coroutine_num: usize,
    lock: *mut c_void,
    pipe_object: *mut c_void,
    pipe_master: *mut c_void,
    pipe_worker: *mut c_void,
    pipe_current: *mut c_void,
    ptr: *mut c_void,
}

/// The worker's status (`SW_WORKER_IDLE`/`BUSY`/…).
///
/// # Safety
/// `worker` points to a live `Worker`/`WorkerRecord` in its backing memory.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_worker_status(worker: *const WorkerRecord) -> u8 {
    // SAFETY: the caller lends a live worker record. Reading the field through the
    // pointer makes no reference to the whole record, which other processes write
    // in shared memory.
    unsafe { (*worker).status }
}

/// Set the worker's status.
///
/// # Safety
/// `worker` points to a live, writable `Worker`/`WorkerRecord`.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_worker_set_status(worker: *mut WorkerRecord, status: u8) {
    // SAFETY: the caller lends a live, writable worker record; as above, only the
    // field is written, with no reference to the whole record.
    unsafe { (*worker).status = status };
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::mem::align_of;

    // The exact offsets/size are locked C++-side: the patch's `static_assert`s compare
    // `swoole::Worker` against the `swr_v1_worker_record` mirror in swoole_rs_process.h,
    // which has these same `#[repr(C)]` fields. Here just sanity-check the Rust record's
    // alignment and that the accessors read/write the right field.
    #[test]
    fn record_is_pointer_aligned() {
        assert_eq!(align_of::<WorkerRecord>(), 8);
    }

    #[test]
    fn status_accessors_round_trip() {
        let mut record: WorkerRecord = unsafe { std::mem::zeroed() };
        unsafe {
            swr_v1_worker_set_status(&raw mut record, 2);
            assert_eq!(swr_v1_worker_status(&raw const record), 2);
        }
    }
}
