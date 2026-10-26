//! Borrowed binary queries and delimiter scanning. No handlers run in Rust.
use super::{INVALID, OVERFLOW};
use std::slice;

const CONTAINS: u32 = 0;
const STARTS_WITH: u32 = 1;
const ENDS_WITH: u32 = 2;
const EQUALS: u32 = 3;

unsafe fn bytes<'a>(data: *const u8, length: usize) -> Result<&'a [u8], i32> {
    if length == 0 {
        return Ok(&[]);
    }
    if length > isize::MAX as usize {
        return Err(OVERFLOW);
    }
    if data.is_null() {
        return Err(INVALID);
    }
    // SAFETY: non-null, `length <= isize::MAX`; callers lend that many initialized bytes.
    Ok(unsafe { slice::from_raw_parts(data, length) })
}
fn find(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    needle.first()?;
    memchr::memmem::find(haystack, needle)
}

/// # Safety
/// The byte ranges actually inspected are initialized/readable. No references
/// escape, outputs/callbacks/allocators are absent. Empty ranges may use null.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_string_match(
    data: *const u8,
    length: usize,
    needle: *const u8,
    count: usize,
    mode: u32,
) -> i32 {
    let result = (|| match mode {
        CONTAINS => {
            if count == 0 {
                return Err(INVALID);
            }
            if count > length {
                return Ok(false);
            }
            // SAFETY: the inspected haystack range is initialized and readable.
            let haystack = unsafe { bytes(data, length)? };
            // SAFETY: the inspected needle range is initialized and readable.
            let needle = unsafe { bytes(needle, count)? };
            Ok(find(haystack, needle).is_some())
        }
        STARTS_WITH | ENDS_WITH | EQUALS => {
            if (mode == EQUALS && length != count) || count > length {
                return Ok(false);
            }
            if count == 0 {
                return Ok(true);
            }
            let offset = if mode == ENDS_WITH { length - count } else { 0 };
            if offset > isize::MAX as usize {
                return Err(OVERFLOW);
            }
            if data.is_null() {
                return Err(INVALID);
            }
            // SAFETY: non-null; `offset + count <= length`, the inspected readable range.
            let view = unsafe { bytes(data.wrapping_add(offset), count)? };
            // SAFETY: the inspected needle range is initialized and readable.
            Ok(view == unsafe { bytes(needle, count)? })
        }
        _ => Err(INVALID),
    })();
    match result {
        Ok(value) => i32::from(value),
        Err(status) => status,
    }
}

/// Allocation-free, overflow-safe substring bounds, including exact-end empties.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_string_range(length: usize, offset: usize, count: usize) -> i32 {
    i32::from(offset <= length && count <= length - offset)
}

#[repr(C)]
#[derive(Default)]
pub struct StringSplitStep {
    pub begin: usize,
    pub length: usize,
    pub advance: usize,
    pub resume: i64,
    pub consumed: usize,
}

/// Inspect exactly one delimiter step. Native invokes its handler only after
/// return, then commits offset += advance; handler failure leaves it untouched.
/// # Safety
/// Initialized source/delimiter bytes and aligned, disjoint writable output are
/// valid. Borrowed/non-owning native Strings are allowed. No Rust borrow escapes.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_string_split_next(
    data: *const u8,
    length: usize,
    offset: i64,
    prefix: i64,
    delimiter: *const u8,
    delimiter_length: usize,
    output: *mut StringSplitStep,
) -> i32 {
    if output.is_null() {
        return INVALID;
    }
    // SAFETY: `output` is non-null (checked above), aligned, writable and disjoint.
    unsafe { output.write(StringSplitStep::default()) };
    let result = (|| {
        let offset = usize::try_from(offset).map_err(|_| INVALID)?;
        let prefix = usize::try_from(prefix).map_err(|_| INVALID)?;
        if offset > length || prefix > offset || delimiter_length == 0 {
            return Err(INVALID);
        }
        if length > isize::MAX as usize || delimiter_length > u32::MAX as usize {
            return Err(OVERFLOW);
        }
        // The pinned helper accepts uint32 lengths. Preserve its search window.
        #[expect(
            clippy::cast_possible_truncation,
            reason = "the pinned helper's uint32 search window"
        )]
        let available = (length - offset) as u32 as usize;
        let start = if offset == 0 {
            data
        } else {
            if data.is_null() {
                return Err(INVALID);
            }
            // In range: `offset <= length` (checked above).
            data.wrapping_add(offset)
        };
        // SAFETY: `available <= length - offset` initialized source bytes from `start`.
        let haystack = unsafe { bytes(start, available)? };
        // SAFETY: the delimiter's `delimiter_length` bytes are initialized and readable.
        let delimiter = unsafe { bytes(delimiter, delimiter_length)? };
        let found = find(haystack, delimiter);
        let step = if let Some(position) = found {
            let advance = position + delimiter_length;
            StringSplitStep {
                begin: offset - prefix,
                length: advance + prefix,
                advance,
                resume: i64::try_from(offset + advance).unwrap_or(i64::MAX),
                consumed: 0,
            }
        } else {
            // Upstream subtracts into a negative offset for short fragments.
            // Clamp to zero: no out-of-allocation pointer on the next receive.
            StringSplitStep {
                consumed: offset - prefix,
                resume: if prefix == offset {
                    i64::try_from(length.saturating_sub(delimiter_length)).unwrap_or(i64::MAX)
                } else {
                    i64::try_from(offset).unwrap_or(i64::MAX)
                },
                ..StringSplitStep::default()
            }
        };
        Ok((i32::from(found.is_some()), step))
    })();
    match result {
        Ok((status, step)) => {
            // SAFETY: as for the first write to `output`.
            unsafe { output.write(step) };
            status
        }
        Err(status) => status,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn binary_search_matches_independent_subsequence_model() {
        for length in 0..=8 {
            for bits in 0..1usize << length {
                let data: Vec<_> = (0..length)
                    .map(|i| if bits & (1 << i) == 0 { 0 } else { 255 })
                    .collect();
                for count in 1..=4 {
                    for pattern in 0..1usize << count {
                        let needle: Vec<_> = (0..count)
                            .map(|i| if pattern & (1 << i) == 0 { 0 } else { 255 })
                            .collect();
                        let expected = (0..=length)
                            .find(|&at| count <= length - at && data[at..at + count] == needle);
                        assert_eq!(find(&data, &needle), expected);
                    }
                }
            }
        }
    }
    #[test]
    fn range_does_not_wrap_and_exact_end_empty_is_valid() {
        assert_eq!(swr_v1_string_range(3, 3, 0), 1);
        assert_eq!(swr_v1_string_range(3, usize::MAX, 2), 0);
        assert_eq!(swr_v1_string_range(usize::MAX, usize::MAX, 0), 1);
        assert_eq!(swr_v1_string_range(usize::MAX, usize::MAX, 1), 0);
        assert!(find(b"abc", b"").is_none());
    }
    #[test]
    fn search_checks_full_candidate_and_last_possible_start() {
        for count in [1, 2, 8, 31, 64, 257] {
            for prefix in [0, 1, 15, 32, 4096] {
                let mut needle = vec![255; count];
                needle[count - 1] = 0;
                let mut haystack = vec![255; prefix];
                haystack.extend_from_slice(&needle);
                assert_eq!(find(&haystack, &needle), Some(prefix));
                haystack.pop();
                assert_eq!(find(&haystack, &needle), None);
            }
        }
    }
}

#[repr(C)]
#[derive(Default, Clone, Copy)]
pub struct StringSplitCursor {
    pub prefix: i64,
    pub advance: usize,
    pub pending: u32,
}
#[repr(C)]
#[derive(Default)]
pub struct StringSplitPlan {
    pub step: StringSplitStep,
    pub cursor: StringSplitCursor,
    pub offset: i64,
    pub value: i64,
    pub trace_value: usize,
    pub action: u32,
    pub trace: u32,
}

/// Combine fresh post-handler metadata, continuation policy and the next scan.
/// # Safety
/// Readable source/delimiter bytes and disjoint aligned PODs obey split_next.
/// Cursor is initialized from initial offset or the previous returned plan.
/// Handler effects complete before this call; no callback/borrow escapes Rust.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_string_split_plan(
    data: *const u8,
    length: usize,
    offset: i64,
    delimiter: *const u8,
    delimiter_length: usize,
    cursor: *const StringSplitCursor,
    accepted: u32,
    output: *mut StringSplitPlan,
) -> i32 {
    if output.is_null() {
        return INVALID;
    }
    let mut plan = StringSplitPlan {
        offset,
        ..StringSplitPlan::default()
    };
    let result = (|| {
        if cursor.is_null() || accepted > 1 {
            return INVALID;
        }
        // SAFETY: non-null (checked above), initialized, aligned and disjoint.
        let cursor = unsafe { &*cursor };
        if cursor.pending > 1 {
            return INVALID;
        }
        if cursor.pending == 1 {
            if accepted == 0 {
                plan.value = -1;
                return 0;
            }
            let Ok(advance) = i64::try_from(cursor.advance) else {
                return OVERFLOW;
            };
            let Some(next) = offset.checked_add(advance) else {
                return OVERFLOW;
            };
            plan.offset = next;
        }
        let prefix = if cursor.pending == 0 {
            cursor.prefix
        } else {
            0
        };
        // SAFETY: forwards the caller's source and delimiter spans; the output is a local.
        let status = unsafe {
            swr_v1_string_split_next(
                data,
                length,
                plan.offset,
                prefix,
                delimiter,
                delimiter_length,
                &mut plan.step,
            )
        };
        if status < 0 {
            return status;
        }
        if status == 0 {
            plan.offset = plan.step.resume;
            plan.value = i64::try_from(plan.step.consumed).unwrap_or(i64::MAX);
            if plan.step.consumed > 0 && plan.step.consumed < length {
                plan.trace = 5;
                plan.trace_value = length - usize::try_from(plan.offset).unwrap_or(length);
            } else if plan.step.consumed >= length {
                plan.trace = 3;
            }
        } else {
            plan.action = 1;
            plan.trace = 4;
            plan.trace_value = usize::try_from(plan.step.resume).unwrap_or(0);
            plan.cursor = StringSplitCursor {
                prefix: 0,
                advance: plan.step.advance,
                pending: 1,
            };
        }
        0
    })();
    // Offset commits precede a subsequent scan error just as native += did.
    // SAFETY: `output` is non-null (checked above), aligned, writable and disjoint.
    unsafe { output.write(plan) };
    result
}

#[cfg(test)]
mod continuation_tests {
    use super::*;
    #[test]
    fn continuation_observes_fresh_effects_false_result_and_error_prefix() {
        let mut data = *b"a\r\nb\r\n";
        let initial = StringSplitCursor::default();
        let mut plan = StringSplitPlan::default();
        unsafe {
            assert_eq!(
                swr_v1_string_split_plan(
                    data.as_ptr(),
                    6,
                    0,
                    b"\r\n".as_ptr(),
                    2,
                    &initial,
                    1,
                    &mut plan
                ),
                0
            )
        };
        assert_eq!(
            (plan.action, plan.offset, plan.step.begin, plan.step.length),
            (1, 0, 0, 3)
        );
        let cursor = plan.cursor;
        data[3] = b'c';
        unsafe {
            assert_eq!(
                swr_v1_string_split_plan(
                    data.as_ptr(),
                    6,
                    0,
                    b"\r\n".as_ptr(),
                    2,
                    &cursor,
                    1,
                    &mut plan
                ),
                0
            )
        };
        assert_eq!(
            (plan.action, plan.offset, plan.step.begin, plan.step.length),
            (1, 3, 3, 3)
        );
        // A false callback preserves even its changed offset and never scans.
        unsafe {
            assert_eq!(
                swr_v1_string_split_plan(
                    data.as_ptr(),
                    6,
                    5,
                    b"\r\n".as_ptr(),
                    2,
                    &cursor,
                    0,
                    &mut plan
                ),
                0
            )
        };
        assert_eq!((plan.action, plan.offset, plan.value), (0, 5, -1));
        // A callback offset side effect is committed before the next search.
        unsafe {
            assert_eq!(
                swr_v1_string_split_plan(
                    data.as_ptr(),
                    6,
                    3,
                    b"\r\n".as_ptr(),
                    2,
                    &cursor,
                    1,
                    &mut plan
                ),
                0
            )
        };
        assert_eq!((plan.action, plan.offset, plan.value), (0, 6, 6));
        // Rust-only invalid-state check: keep the already committed offset.
        unsafe {
            assert_eq!(
                swr_v1_string_split_plan(
                    data.as_ptr(),
                    6,
                    6,
                    b"\r\n".as_ptr(),
                    2,
                    &cursor,
                    1,
                    &mut plan
                ),
                INVALID
            )
        };
        assert_eq!((plan.action, plan.offset), (0, 9));
    }
}
