//! Sole persistent StaticHandlerV2 task storage. Native owns one local immutable
//! send snapshot and executes RNG/MIME/date/allocation/IO effects after return.
use crate::INVALID;
use crate::range_response::{HttpRangeFormat, swr_v1_http_range_format};
use std::alloc::{Layout, alloc};

#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct HttpStaticTask {
    pub offset: i64,
    pub length: usize,
    pub part_header: [u8; 256],
}
impl Default for HttpStaticTask {
    fn default() -> Self {
        Self {
            offset: 0,
            length: 0,
            part_header: [0; 256],
        }
    }
}
#[derive(Default)]
pub struct HttpTasks {
    items: Vec<HttpStaticTask>,
    scratch: HttpStaticTask,
}
const ALLOCATION: i32 = -3;

impl HttpTasks {
    pub(crate) fn begin(&mut self) {
        self.scratch = HttpStaticTask::default();
    }
    pub(crate) fn push(&mut self) -> i32 {
        if self.items.try_reserve(1).is_err() {
            return ALLOCATION;
        }
        self.items.push(self.scratch);
        0
    }
    pub(crate) fn count(&self) -> usize {
        self.items.len()
    }
    pub(crate) fn clear(&mut self) {
        self.items.clear();
    }
    // Format contains external spans, validated by the shared formatter. No
    // caller effect runs during this operation and no span is retained.
    pub(crate) unsafe fn prepare(
        &mut self,
        offset: i64,
        length: usize,
        format: *const HttpRangeFormat,
        written: *mut usize,
    ) -> i32 {
        self.scratch.offset = offset;
        self.scratch.length = length;
        if format.is_null() {
            // SAFETY: callers pass the export's aligned, writable `written` output.
            unsafe { written.write(0) };
            return 0;
        }
        // SAFETY: `format` is non-null with validated spans; the scratch header holds 256
        // writable bytes; `written` is the caller's output.
        unsafe {
            swr_v1_http_range_format(format, self.scratch.part_header.as_mut_ptr(), 256, written)
        }
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v2_http_tasks_new() -> *mut HttpTasks {
    #[expect(
        clippy::cast_ptr_alignment,
        reason = "alloc honours Layout::new::<HttpTasks>()"
    )]
    // SAFETY: a non-zero-sized layout; null is handled below.
    let owner = unsafe { alloc(Layout::new::<HttpTasks>()).cast::<HttpTasks>() };
    if !owner.is_null() {
        // SAFETY: `owner` is a fresh, non-null allocation with its type's layout.
        unsafe { owner.write(HttpTasks::default()) };
    }
    owner
}
/// # Safety
/// Null or a unique live owner from tasks_new, dropped once. Native snapshots
/// are independent copies and may outlive this owner.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_tasks_drop(owner: *mut HttpTasks) {
    if !owner.is_null() {
        // SAFETY: a unique, live owner from `tasks_new`, dropped once.
        unsafe { drop(Box::from_raw(owner)) };
    }
}
/// Reset per-parse scratch, retaining previously committed tasks exactly as the
/// original method's local task initialization and persistent vector do.
/// # Safety
/// Unique live owner; no Rust task pointers are exported or retained by native.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_tasks_begin(owner: *mut HttpTasks) -> i32 {
    // SAFETY: `owner` is null or live, aligned and exclusively lent for this call.
    let Some(owner) = (unsafe { owner.as_mut() }) else {
        return INVALID;
    };
    owner.begin();
    0
}
/// Prepare copied metadata and optional range header in Rust-owned scratch. Null
/// format is a full-file task and preserves previous scratch header bytes. Header
/// formatting reuses the existing v1 byte/errno-count policy, including retained
/// initialized tail bytes. This does not commit a task or allocate.
/// # Safety
/// Unique live owner; optional initialized format and all spans disjoint from
/// owner; aligned writable written disjoint from all inputs/owner. Native MIME/
/// boundary effects have completed. No borrow or frame crosses those effects.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_tasks_prepare(
    owner: *mut HttpTasks,
    offset: i64,
    length: usize,
    format: *const HttpRangeFormat,
    written: *mut usize,
) -> i32 {
    if written.is_null() {
        return INVALID;
    }
    // SAFETY: `owner` is null or live, aligned and exclusively lent for this call.
    let Some(owner) = (unsafe { owner.as_mut() }) else {
        return INVALID;
    };
    // SAFETY: `written` is non-null (checked above); `format` follows the export contract.
    unsafe { owner.prepare(offset, length, format, written) }
}
/// Commit the prepared value with fallible admission; error publishes no task.
/// Native updates original content accounting before this call as it did before
/// vector::push_back. Allocation failure/exception equivalence is unqualified.
/// # Safety
/// Unique live owner with initialized per-parse scratch. No concurrent observer.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_tasks_push(owner: *mut HttpTasks) -> i32 {
    // SAFETY: `owner` is null or live, aligned and exclusively lent for this call.
    let Some(owner) = (unsafe { owner.as_mut() }) else {
        return INVALID;
    };
    owner.push()
}
/// # Safety
/// Null lazy-empty or live unchanged owner for this complete call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_tasks_count(owner: *const HttpTasks) -> usize {
    // SAFETY: `owner` is null or live and aligned for this call.
    unsafe { owner.as_ref() }.map_or(0, HttpTasks::count)
}
/// Copy one completed task into Native send-snapshot storage. No Rust pointer or
/// borrowed header bytes escape. Invalid index leaves output unchanged.
/// # Safety
/// Live unchanged owner and aligned writable output disjoint from owner storage.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_tasks_copy(
    owner: *const HttpTasks,
    index: usize,
    output: *mut HttpStaticTask,
) -> i32 {
    if output.is_null() {
        return INVALID;
    }
    // SAFETY: `owner` is null or live and aligned for this call.
    let Some(owner) = (unsafe { owner.as_ref() }) else {
        return INVALID;
    };
    let Some(task) = owner.items.get(index) else {
        return INVALID;
    };
    // SAFETY: `output` is non-null (checked above), aligned and writable per the caller contract.
    unsafe { output.write(*task) };
    0
}
/// Query or copy the whole immutable Native IO snapshot in one call. Capacity0
/// queries count without reading output. Insufficient capacity/invalid metadata
/// changes neither output nor written; successful fill owns independent values.
/// # Safety
/// Null lazy-empty or live unchanged owner; aligned writable written and output
/// capacity are disjoint from one another and the owner. Native constructed the
/// typed destination records, and publishes them only after this call returns.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_tasks_snapshot(
    owner: *const HttpTasks,
    output: *mut HttpStaticTask,
    capacity: usize,
    written: *mut usize,
) -> i32 {
    if written.is_null() {
        return INVALID;
    }
    // SAFETY: `owner` is null or live and aligned for this call.
    let tasks = unsafe { owner.as_ref() }.map_or(&[][..], |owner| owner.items.as_slice());
    if capacity != 0 {
        if capacity < tasks.len()
            || capacity > isize::MAX as usize / std::mem::size_of::<HttpStaticTask>()
        {
            return crate::OVERFLOW;
        }
        if output.is_null() {
            return INVALID;
        }
        if !tasks.is_empty() {
            // SAFETY: non-null (checked above), `len <= capacity` slots, disjoint from the owner.
            unsafe { std::ptr::copy_nonoverlapping(tasks.as_ptr(), output, tasks.len()) };
        }
    }
    // SAFETY: `written` is non-null (checked above), aligned and writable per the caller contract.
    unsafe { written.write(tasks.len()) };
    0
}
/// Clear completed task values, retaining capacity and scratch for the original
/// If-Range full-file replacement. No native object/resource destructor runs.
/// # Safety
/// Unique live owner. Native IO snapshots, if any, are independent owned copies.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_tasks_clear(owner: *mut HttpTasks) -> i32 {
    // SAFETY: `owner` is null or live, aligned and exclusively lent for this call.
    let Some(owner) = (unsafe { owner.as_mut() }) else {
        return INVALID;
    };
    owner.clear();
    0
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::proxy::HttpProxyText;
    #[test]
    fn bulk_snapshot_admission_preserves_outputs_before_publication() {
        let owner = swr_v2_http_tasks_new();
        assert!(!owner.is_null());
        assert_eq!(unsafe { swr_v2_http_tasks_push(owner) }, 0);
        assert_eq!(unsafe { swr_v2_http_tasks_push(owner) }, 0);
        let mut destination = HttpStaticTask {
            offset: 77,
            ..HttpStaticTask::default()
        };
        let before = destination;
        let mut written = 91;
        assert_eq!(
            unsafe { swr_v2_http_tasks_snapshot(owner, &raw mut destination, 1, &raw mut written) },
            crate::OVERFLOW
        );
        assert_eq!(destination, before);
        assert_eq!(written, 91);
        let mut output = [HttpStaticTask::default(); 2];
        assert_eq!(
            unsafe {
                swr_v2_http_tasks_snapshot(
                    owner,
                    output.as_mut_ptr(),
                    output.len(),
                    &raw mut written,
                )
            },
            0
        );
        assert_eq!(written, 2);
        unsafe { swr_v2_http_tasks_drop(owner) };
        assert_eq!(output, [HttpStaticTask::default(); 2]);
        assert_eq!(
            unsafe {
                swr_v2_http_tasks_snapshot(
                    std::ptr::null(),
                    std::ptr::null_mut(),
                    0,
                    &raw mut written,
                )
            },
            0
        );
        assert_eq!(written, 0);
    }
    #[test]
    fn owned_tasks_copy_headers_and_snapshot_survives_owner_mutation() {
        let owner = swr_v2_http_tasks_new();
        assert!(!owner.is_null());
        assert_eq!(unsafe { swr_v2_http_tasks_begin(owner) }, 0);
        let mut boundary = b"fixed-boundary".to_vec();
        let format = HttpRangeFormat {
            boundary: HttpProxyText {
                data: boundary.as_ptr(),
                length: boundary.len(),
            },
            mime: HttpProxyText {
                data: b"text/plain".as_ptr(),
                length: 10,
            },
            offset: 3,
            length: 5,
            filesize: 100,
            part: 0,
            separator: 0,
        };
        let mut written = 0;
        assert_eq!(
            unsafe { swr_v2_http_tasks_prepare(owner, 3, 5, &raw const format, &raw mut written) },
            0
        );
        assert!(written > 0);
        assert_eq!(unsafe { swr_v2_http_tasks_push(owner) }, 0);
        boundary.fill(b'x');
        let mut snapshot = HttpStaticTask::default();
        assert_eq!(
            unsafe { swr_v2_http_tasks_copy(owner, 0, &raw mut snapshot) },
            0
        );
        assert!(
            snapshot
                .part_header
                .windows(14)
                .any(|s| s == b"fixed-boundary")
        );
        assert_eq!(unsafe { swr_v2_http_tasks_clear(owner) }, 0);
        assert_eq!(unsafe { swr_v2_http_tasks_count(owner) }, 0);
        assert_eq!(
            unsafe { swr_v2_http_tasks_prepare(owner, 0, 100, std::ptr::null(), &raw mut written) },
            0
        );
        assert_eq!(unsafe { swr_v2_http_tasks_push(owner) }, 0);
        let mut full = HttpStaticTask::default();
        assert_eq!(
            unsafe { swr_v2_http_tasks_copy(owner, 0, &raw mut full) },
            0
        );
        assert_eq!(full.part_header, snapshot.part_header);
        assert_eq!(full.offset, 0);
        assert_eq!(full.length, 100);
        assert_eq!(snapshot.offset, 3);
        assert_eq!(snapshot.length, 5);
        let mut required = 0;
        assert_eq!(
            unsafe {
                swr_v2_http_tasks_snapshot(owner, std::ptr::null_mut(), 0, &raw mut required)
            },
            0
        );
        assert_eq!(required, 1);
        let mut bulk = HttpStaticTask::default();
        assert_eq!(
            unsafe { swr_v2_http_tasks_snapshot(owner, &raw mut bulk, 1, &raw mut required) },
            0
        );
        assert_eq!(bulk, full);

        assert_eq!(
            unsafe { swr_v2_http_tasks_copy(owner, 1, &raw mut full) },
            INVALID
        );
        assert_eq!(full.length, 100);
        assert_eq!(unsafe { swr_v2_http_tasks_begin(owner) }, 0);
        assert_eq!(unsafe { swr_v2_http_tasks_count(owner) }, 1);
        unsafe { swr_v2_http_tasks_drop(owner) };
        assert!(
            snapshot
                .part_header
                .windows(14)
                .any(|s| s == b"fixed-boundary")
        );
    }
}
