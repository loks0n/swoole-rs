//! Static rewrite byte policy; Native retains regex execution and effects.
use crate::proxy::HttpProxyText;
use crate::{HttpSpan, INVALID, OVERFLOW, bytes};
#[repr(C)]
pub struct HttpRewriteLiteral {
    pub url: HttpProxyText,
    pub pattern: HttpProxyText,
    pub replacement: HttpProxyText,
}
use std::ptr;
pub(crate) fn classify(pattern: &[u8]) -> (crate::HttpSpan, bool) {
    let regex =
        pattern.len() >= 2 && pattern.first() == Some(&b'~') && pattern.last() == Some(&b'~');
    (
        crate::HttpSpan {
            offset: usize::from(regex),
            length: pattern.len() - 2 * usize::from(regex),
        },
        regex,
    )
}
/// Classify a native rule. Matching leading/trailing '~' delimiters select regex;
/// returned span excludes them. Everything else, including empty, is literal.
/// # Safety
/// Input is readable/initialized and both aligned outputs are writable/disjoint.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_http_rewrite_rule(
    pattern: *const u8,
    length: usize,
    span: *mut HttpSpan,
    regex: *mut u32,
) -> i32 {
    if span.is_null() || regex.is_null() {
        return INVALID;
    }
    let input = match unsafe { bytes(pattern, length) } {
        Ok(value) => value,
        Err(error) => return error,
    };
    let (classified, is_regex) = classify(input);
    unsafe {
        span.write(classified);
        regex.write(u32::from(is_regex));
    }
    0
}
// Shared safe byte policy for the public query/fill ABI and owned publication.
// A plan borrows only its input URL and never survives an effect boundary.
pub(crate) fn literal_suffix<'a>(
    url: &'a [u8],
    pattern: &[u8],
    replacement_length: usize,
) -> Result<Option<(&'a [u8], usize)>, i32> {
    let Some(suffix) = url.strip_prefix(pattern) else {
        return Ok(None);
    };
    let required = replacement_length
        .checked_add(suffix.len())
        .filter(|&length| length <= isize::MAX as usize)
        .ok_or(OVERFLOW)?;
    Ok(Some((suffix, required)))
}
/// Literal prefix replacement. Returns0=no match,1=match; capacity0 queries the
/// required output size, other capacities must fit it exactly or provide more.
/// Strings are byte spans (embedded NUL is significant), without a terminator.
/// # Safety
/// Every input span is readable/initialized. Output capacity and written are
/// writable, aligned where needed and mutually disjoint from all input spans.
/// No allocation/callback/borrow survives this call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_http_rewrite_literal(
    request: *const HttpRewriteLiteral,
    output: *mut u8,
    capacity: usize,
    written: *mut usize,
) -> i32 {
    if request.is_null() || written.is_null() || capacity != 0 && output.is_null() {
        return INVALID;
    }
    if capacity > isize::MAX as usize {
        return OVERFLOW;
    }
    let request = unsafe { &*request };
    let inputs = unsafe {
        [
            bytes(request.url.data, request.url.length),
            bytes(request.pattern.data, request.pattern.length),
            bytes(request.replacement.data, request.replacement.length),
        ]
    };
    let [url, pattern, replacement] = match inputs {
        [Ok(a), Ok(b), Ok(c)] => [a, b, c],
        values => return values.into_iter().find_map(Result::err).unwrap_or(INVALID),
    };
    let (suffix, required) = match literal_suffix(url, pattern, replacement.len()) {
        Ok(Some(plan)) => plan,
        Ok(None) => return 0,
        Err(error) => return error,
    };
    if capacity != 0 && capacity < required {
        return INVALID;
    }
    if capacity != 0 {
        unsafe {
            ptr::copy_nonoverlapping(replacement.as_ptr(), output, replacement.len());
            ptr::copy_nonoverlapping(suffix.as_ptr(), output.add(replacement.len()), suffix.len());
        }
    }
    unsafe { written.write(required) };
    1
}
/// Copied first-match cursor shared by legacy and sole-owner context callers.
/// Native configuration/regex effects occur only between complete calls.
#[repr(C)]
#[derive(Default)]
pub struct HttpRewriteState {
    phase: u32,
    index: usize,
    count: usize,
}
impl HttpRewriteState {
    pub(crate) fn legacy_step(&mut self, count: usize, observed: u32, index: &mut usize) -> i32 {
        if observed == 7 {
            return if self.phase == 2 { 6 } else { INVALID };
        }
        let action = self.step(count, observed, index);
        if action == 0 && observed == 4 {
            5
        } else {
            action
        }
    }
    pub(crate) fn step(&mut self, count: usize, observed: u32, index: &mut usize) -> i32 {
        const RULE: u32 = 1;
        const LITERAL: u32 = 2;
        const SEARCH: u32 = 3;
        const REPLACE: u32 = 4;
        const DONE: u32 = 5;
        if observed == 0 {
            *self = Self {
                count,
                ..Self::default()
            };
            if count == 0 {
                self.phase = DONE;
                return 0;
            }
            self.phase = RULE;
            *index = 0;
            return 1;
        }
        match (self.phase, observed) {
            (RULE, 1) => {
                self.phase = LITERAL;
                2
            }
            (RULE, 2) => {
                self.phase = SEARCH;
                3
            }
            (SEARCH, 5) => {
                self.phase = REPLACE;
                4
            }
            (LITERAL | REPLACE, 4) => {
                self.phase = DONE;
                0
            }
            (LITERAL | SEARCH | REPLACE, 3) if self.index < self.count => {
                self.index += 1;
                if self.index == self.count {
                    self.phase = DONE;
                    return 0;
                }
                self.phase = RULE;
                *index = self.index;
                1
            }
            _ => INVALID,
        }
    }
}
/// Legacy ordered-rule caller: existing observations0..5 and event6=completed
/// regex replacement,7=matched literal query. Actions0=not rewritten,1=read rule,2=literal query,3=search,
/// 4=replace,5=publish then return true,6=allocate/fill literal. A literal match
/// publishes even equal bytes; equal regex output resumes the next rule.
/// # Safety
/// Initialized unique state and disjoint writable index. At event6 both spans
/// are initialized/disjoint from state/output; ignored otherwise. Native config,
/// string/regex effects and publication complete after return, with no live Rust
/// borrow, retained operand or copied configuration owner.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_rewrite_step(
    state: *mut HttpRewriteState,
    count: usize,
    observed: u32,
    current: *const HttpProxyText,
    replacement: *const HttpProxyText,
    index: *mut usize,
) -> i32 {
    let (Some(state), Some(index)) = (unsafe { state.as_mut() }, unsafe { index.as_mut() }) else {
        return INVALID;
    };
    let observed = if observed == 6 {
        let (Some(current), Some(replacement)) =
            (unsafe { current.as_ref() }, unsafe { replacement.as_ref() })
        else {
            return INVALID;
        };
        let (Ok(current), Ok(replacement)) =
            (unsafe { bytes(current.data, current.length) }, unsafe {
                bytes(replacement.data, replacement.length)
            })
        else {
            return INVALID;
        };
        if current == replacement { 3 } else { 4 }
    } else {
        observed
    };
    state.legacy_step(count, observed, index)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn shared_cursor_preserves_first_match_and_unchanged_regex_continuation() {
        let mut state = HttpRewriteState::default();
        let mut index = 99;
        assert_eq!(state.step(2, 0, &mut index), 1);
        assert_eq!(index, 0);
        assert_eq!(state.step(0, 2, &mut index), 3);
        assert_eq!(state.step(0, 5, &mut index), 4);
        assert_eq!(state.step(0, 3, &mut index), 1);
        assert_eq!(index, 1);
        assert_eq!(state.step(0, 1, &mut index), 2);
        assert_eq!(state.step(0, 4, &mut index), 0);
    }
    #[test]
    fn binary_prefix_and_exact_capacity_are_preserved() {
        let url = b"/a\0suffix";
        let pattern = b"/a\0";
        let replacement = b"/b\0";
        let span = |value: &[u8]| HttpProxyText {
            data: value.as_ptr(),
            length: value.len(),
        };
        let request = HttpRewriteLiteral {
            url: span(url),
            pattern: span(pattern),
            replacement: span(replacement),
        };
        let mut output = [0xcc; 16];
        let mut written = 99;
        assert_eq!(
            unsafe { swr_v1_http_rewrite_literal(&request, output.as_mut_ptr(), 8, &mut written) },
            INVALID
        );
        assert_eq!(output, [0xcc; 16]);
        assert_eq!(written, 99);
        assert_eq!(
            unsafe { swr_v1_http_rewrite_literal(&request, output.as_mut_ptr(), 9, &mut written) },
            1
        );
        assert_eq!(&output[..written], b"/b\0suffix");
        assert_eq!(output[written], 0xcc);
    }
}
