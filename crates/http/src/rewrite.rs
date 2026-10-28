//! Static rewrite byte policy; Native retains regex execution and effects.
use crate::{HttpSpan, INVALID, OVERFLOW, bytes};
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
    // SAFETY: the caller lends `length` initialized bytes at `pattern` (null only when empty).
    let input = match unsafe { bytes(pattern, length) } {
        Ok(value) => value,
        Err(error) => return error,
    };
    let (classified, is_regex) = classify(input);
    // SAFETY: both are non-null (checked above), aligned, writable and disjoint.
    unsafe { span.write(classified) };
    // SAFETY: as above.
    unsafe { regex.write(u32::from(is_regex)) };
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
        .filter(|&length| isize::try_from(length).is_ok())
        .ok_or(OVERFLOW)?;
    Ok(Some((suffix, required)))
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
    fn binary_prefix_keeps_the_suffix_after_embedded_nul() {
        assert_eq!(
            literal_suffix(b"/a\0suffix", b"/a\0", 3),
            Ok(Some((&b"suffix"[..], 9)))
        );
        assert_eq!(literal_suffix(b"/a", b"/a\0", 3), Ok(None));
    }
}
