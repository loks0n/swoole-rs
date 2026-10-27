//! Conditional-date policy; libc calendar objects remain in the native facade.
use crate::{INVALID, OVERFLOW};
use std::ffi::{CStr, c_char};
static FORMATS: [&CStr; 4] = [
    c"%a, %d %b %Y %T GMT",
    c"%a, %d %b %Y %T UTC",
    c"%A, %d-%b-%y %T GMT",
    c"%a %b %e %T %Y",
];
#[repr(C)]
#[derive(Default)]
pub struct HttpConditional {
    pub phase: u32,
    pub kind: u32,
    pub valid: u32,
    pub length: usize,
    pub timezone: i64,
    pub file_mtime: i64,
    pub value: i64,
    pub parsed_time: i64,
}
/// Native strptime format, immutable for process lifetime. Unknown index is null.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_http_date_format(index: u32) -> *const c_char {
    FORMATS
        .get(index as usize)
        .map_or(std::ptr::null(), |format| format.as_ptr())
}
/// Kind0=If-Modified-Since; kind1=If-Range mismatch. Returns native actions:
/// 0=false,1..4=strptime format0..3,5=gmtime(file),6=mktime(parsed),
/// 7=mktime(file GMT),8=true. Native stores result validity/value before resume.
/// # Safety
/// State is writable/aligned and retained unchanged except native result fields.
/// Native calendar objects survive between calls; Rust borrows none of them.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_http_conditional(state: *mut HttpConditional) -> i32 {
    if state.is_null() {
        return INVALID;
    }
    // SAFETY: `state` is non-null (checked above), aligned and exclusive per the caller contract.
    let state = unsafe { &mut *state };
    if state.kind > 1 {
        return INVALID;
    }
    match state.phase {
        0 => {
            if state.length > isize::MAX as usize {
                return OVERFLOW;
            }
            if state.length == 0 || state.kind == 0 && state.length > 63 {
                state.phase = 10;
                return 0;
            }
            state.phase = 1;
            1
        }
        1..=4 => {
            if state.valid != 0 {
                if state.kind == 0 {
                    state.phase = 6;
                    6
                } else {
                    state.phase = 5;
                    5
                }
            } else if state.phase < 4 {
                state.phase += 1;
                state.phase.cast_signed()
            } else if state.kind == 1 {
                state.phase = 9;
                5
            } else {
                state.phase = 10;
                0
            }
        }
        5 => {
            if state.valid == 0 {
                state.phase = 10;
                return 0;
            }
            state.phase = 6;
            6
        }
        6 => {
            if state.kind == 0 {
                state.phase = 10;
                state
                    .value
                    .checked_sub(state.timezone)
                    .map_or(
                        OVERFLOW,
                        |parsed| if parsed >= state.file_mtime { 8 } else { 0 },
                    )
            } else {
                state.parsed_time = state.value;
                state.phase = 7;
                7
            }
        }
        7 => {
            state.phase = 10;
            if state.parsed_time == state.value {
                0
            } else {
                8
            }
        }
        // Legacy If-Range calls gmtime even if all date formats failed.
        9 => {
            state.phase = 10;
            0
        }
        _ => INVALID,
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn range_parse_failure_still_requests_gmtime_and_since_does_not() {
        for kind in [0, 1] {
            let mut state = HttpConditional {
                kind,
                length: 12,
                ..Default::default()
            };
            for action in 1..=4 {
                assert_eq!(unsafe { swr_v1_http_conditional(&raw mut state) }, action);
            }
            if kind == 1 {
                assert_eq!(unsafe { swr_v1_http_conditional(&raw mut state) }, 5);
            }
            assert_eq!(unsafe { swr_v1_http_conditional(&raw mut state) }, 0);
        }
    }
    #[test]
    fn signed_time_comparison_and_invalid_metadata_are_checked() {
        let mut state = HttpConditional {
            kind: 0,
            phase: 6,
            value: i64::MIN,
            timezone: 1,
            ..Default::default()
        };
        assert_eq!(unsafe { swr_v1_http_conditional(&raw mut state) }, OVERFLOW);
        state = HttpConditional {
            kind: 0,
            phase: 6,
            value: 100,
            timezone: 1,
            file_mtime: 99,
            ..Default::default()
        };
        assert_eq!(unsafe { swr_v1_http_conditional(&raw mut state) }, 8);
        state = HttpConditional {
            kind: 0,
            length: 64,
            ..Default::default()
        };
        assert_eq!(unsafe { swr_v1_http_conditional(&raw mut state) }, 0);
        assert!(swr_v1_http_date_format(4).is_null());
    }
}
