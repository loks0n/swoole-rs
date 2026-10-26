//! Whole cookie scratch preparation/iteration policy. Native reserves and invokes
//! callbacks only after return; no Rust pointer or borrow survives either effect.
use crate::{HttpCookie, INVALID, OVERFLOW};
#[repr(C)]
#[derive(Default)]
pub struct HttpCookieFlow {
    pub phase: u32,
    pub source_inside: u32,
    pub source_offset: usize,
    pub required: usize,
    pub cursor: usize,
    pub cookie: HttpCookie,
}
const COPY: u32 = 1;
const RESUME: u32 = 2;
const DONE: u32 = 3;
const CALLBACK: i32 = 1;
const RESERVE: i32 = 2;
/// Start with zeroed flow. Returns2=Native reserve(required),1=Native callback
/// using copied cookie offsets,0=done. Feed the actual callback boolean on resume.
/// Mode copy_only1 prepares scratch for native multipart filename consumers;
/// mode0 additionally tokenizes/calls back. Mode/length stay fixed across steps.
/// Existing scratch growth/alias rebasing corrections are retained; no reference
/// implementation overflow/alias/reentry/failure profile is made safe by this API.
/// # Safety
/// Flow is aligned/writable/disjoint. Initial source has length initialized bytes
/// (null allowed only when length0); scratch is a live Native allocation through
/// capacity<=isize::MAX. Native completes reserve before resuming with fresh base/
/// capacity; callback completes before resume with fresh captured scratch fields.
/// No callback/allocation may occur through a Rust frame. Valid initialized span,
/// effect, aliasing and callback lifetime preconditions remain the Native caller's.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_cookie_flow(
    flow: *mut HttpCookieFlow,
    source: *const u8,
    length: usize,
    scratch: *mut u8,
    capacity: usize,
    callback_result: u32,
    copy_only: u32,
) -> i32 {
    // SAFETY: `flow` is null or live, aligned and exclusively lent for this call.
    let Some(flow) = (unsafe { flow.as_mut() }) else {
        return INVALID;
    };
    if callback_result > 1 || copy_only > 1 || capacity > isize::MAX as usize {
        return INVALID;
    }
    if flow.phase == 0 {
        let Some(required) = length.checked_add(1).filter(|&n| n <= isize::MAX as usize) else {
            return OVERFLOW;
        };
        let base = scratch as usize;
        let input = source as usize;
        let offset = input.wrapping_sub(base);
        flow.source_inside =
            u32::from(input >= base && offset <= capacity && length <= capacity - offset);
        flow.source_offset = offset;
        flow.required = required;
        flow.phase = COPY;
        if length >= capacity {
            return RESERVE;
        }
    }
    if flow.phase == COPY {
        if scratch.is_null()
            || flow.required > capacity
            || length.checked_add(1) != Some(flow.required)
        {
            return INVALID;
        }
        let input = if flow.source_inside != 0 {
            if flow.source_offset > capacity || length > capacity - flow.source_offset {
                return INVALID;
            }
            // In range: `source_offset + length <= capacity` (checked above).
            scratch.wrapping_add(flow.source_offset).cast_const()
        } else {
            source
        };
        if length != 0 {
            if input.is_null() {
                return INVALID;
            }
            // Raw memmove semantics: valid overlapping Native spans are allowed;
            // no simultaneous overlapping Rust references are constructed.
            // SAFETY: both non-null; `length < capacity` writable scratch bytes and `length` readable input.
            unsafe { std::ptr::copy(input, scratch, length) };
        }
        // SAFETY: `length + 1 == required <= capacity`, inside the writable scratch.
        unsafe { scratch.wrapping_add(length).write(0) };
        flow.cursor = 0;
        if copy_only != 0 {
            flow.phase = DONE;
            return 0;
        }
    } else if flow.phase == RESUME {
        if callback_result == 0 {
            flow.phase = DONE;
            return 0;
        }
    } else if flow.phase == DONE {
        return 0;
    } else {
        return INVALID;
    }
    // SAFETY: the scratch holds the NUL-terminated cookie text in `capacity` bytes; the
    // cursor and cookie are fields of the caller's exclusive flow.
    let result = unsafe {
        crate::swr_v1_http_cookie_next(scratch, capacity, &mut flow.cursor, &mut flow.cookie)
    };
    if result == CALLBACK {
        flow.phase = RESUME;
    } else if result == 0 {
        flow.phase = DONE;
    }
    result
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn ordinary_growth_and_callbacks_leave_allocation_and_effects_outside_rust() {
        let source = b"first=one; second=two; last=three";
        let mut scratch = vec![b'?'; 4];
        let mut flow = HttpCookieFlow::default();
        let step = |flow: &mut HttpCookieFlow, scratch: &mut Vec<u8>, observed| unsafe {
            swr_v2_http_cookie_flow(
                flow,
                source.as_ptr(),
                source.len(),
                scratch.as_mut_ptr(),
                scratch.len(),
                observed,
                0,
            )
        };
        assert_eq!(step(&mut flow, &mut scratch, 1), RESERVE);
        assert!(scratch.iter().all(|&byte| byte == b'?'));
        scratch.resize(flow.required, b'?'); // Explicit external effect after return.
        let mut pairs = Vec::new();
        while step(&mut flow, &mut scratch, 1) == CALLBACK {
            let cookie = &flow.cookie;
            pairs.push((
                scratch[cookie.key_offset..cookie.key_offset + cookie.key_length].to_vec(),
                scratch[cookie.value_offset..cookie.value_offset + cookie.value_length].to_vec(),
            ));
        }
        assert_eq!(
            pairs,
            vec![
                (b"first".to_vec(), b"one".to_vec()),
                (b"second".to_vec(), b"two".to_vec()),
                (b"last".to_vec(), b"three".to_vec())
            ]
        );
        assert_eq!(flow.phase, DONE);
    }
    #[test]
    fn ordinary_callback_stop_does_not_parse_later_tokens() {
        let source = b"first=one;second=two";
        let mut scratch = [b'?'; 64];
        let mut flow = HttpCookieFlow::default();
        assert_eq!(
            unsafe {
                swr_v2_http_cookie_flow(
                    &mut flow,
                    source.as_ptr(),
                    source.len(),
                    scratch.as_mut_ptr(),
                    scratch.len(),
                    1,
                    0,
                )
            },
            CALLBACK
        );
        let before = scratch;
        assert_eq!(
            unsafe {
                swr_v2_http_cookie_flow(
                    &mut flow,
                    source.as_ptr(),
                    source.len(),
                    scratch.as_mut_ptr(),
                    scratch.len(),
                    0,
                    0,
                )
            },
            0
        );
        assert_eq!(scratch, before);
        assert_eq!(flow.phase, DONE);
    }
    #[test]
    fn ordinary_copy_only_preserves_delimiters_for_the_real_header_consumer() {
        let source = b"name=ordinary; filename=plain.txt";
        let mut scratch = vec![b'?'; 4];
        let mut flow = HttpCookieFlow::default();
        assert_eq!(
            unsafe {
                swr_v2_http_cookie_flow(
                    &mut flow,
                    source.as_ptr(),
                    source.len(),
                    scratch.as_mut_ptr(),
                    scratch.len(),
                    1,
                    1,
                )
            },
            RESERVE
        );
        scratch.resize(flow.required, b'?');
        assert_eq!(
            unsafe {
                swr_v2_http_cookie_flow(
                    &mut flow,
                    source.as_ptr(),
                    source.len(),
                    scratch.as_mut_ptr(),
                    scratch.len(),
                    1,
                    1,
                )
            },
            0
        );
        assert_eq!(&scratch[..source.len()], source);
        assert_eq!(scratch[source.len()], 0);
        assert_eq!(flow.phase, DONE);
    }
}
