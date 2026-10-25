//! Sole ordered rewrite-rule ownership. All observations are copied before Native effects.
use crate::{INVALID, OVERFLOW, bytes, request_context::try_boxed};
use std::ptr;

struct RuleSpan {
    bytes: std::ops::Range<usize>,
    split: usize,
    regex: bool,
}
struct Rule<'a> {
    bytes: &'a [u8],
    split: usize,
    regex: bool,
}
#[derive(Default)]
pub struct HttpRewriteStore {
    bytes: Vec<u8>,
    rules: Vec<RuleSpan>,
}
impl HttpRewriteStore {
    fn rule(&self, index: usize) -> Option<Rule<'_>> {
        let rule = self.rules.get(index)?;
        Some(Rule {
            bytes: &self.bytes[rule.bytes.clone()],
            split: rule.split,
            regex: rule.regex,
        })
    }
    fn append(&mut self, pattern: &[u8], replacement: &[u8], regex: bool) -> Result<(), i32> {
        let length = pattern
            .len()
            .checked_add(replacement.len())
            .ok_or(OVERFLOW)?;
        // Both fallible reservations precede publication of bytes or records.
        // Capacity may grow on error, but all earlier logical rules stay intact.
        self.bytes.try_reserve(length).map_err(|_| OVERFLOW)?;
        self.rules.try_reserve(1).map_err(|_| OVERFLOW)?;
        let start = self.bytes.len();
        self.bytes.extend_from_slice(pattern);
        self.bytes.extend_from_slice(replacement);
        self.rules.push(RuleSpan {
            bytes: start..self.bytes.len(),
            split: pattern.len(),
            regex,
        });
        Ok(())
    }
}
#[repr(C)]
#[derive(Default, Debug, PartialEq)]
pub struct HttpRewriteRecord {
    pub pattern_length: usize,
    pub replacement_length: usize,
    pub regex: u32,
}
/// Append atomically after fallible reservations, allocating the owner lazily.
/// # Safety
/// `owner` uniquely owns null or this API's live store. Inputs are readable and
/// disjoint from the owner; no access overlaps another call or owner destruction.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_rewrite_store_add(
    owner: *mut *mut HttpRewriteStore,
    pattern: *const u8,
    pattern_length: usize,
    replacement: *const u8,
    replacement_length: usize,
) -> i32 {
    if owner.is_null() {
        return INVALID;
    }
    let (pattern, replacement) = match (unsafe { bytes(pattern, pattern_length) }, unsafe {
        bytes(replacement, replacement_length)
    }) {
        (Ok(a), Ok(b)) => (a, b),
        (Err(e), _) | (_, Err(e)) => return e,
    };
    let (classified, regex) = crate::rewrite::classify(pattern);
    let pattern = &pattern[classified.offset..classified.offset + classified.length];
    let current = unsafe { owner.read() };
    if current.is_null() {
        let mut value = HttpRewriteStore::default();
        if let Err(error) = value.append(pattern, replacement, regex) {
            return error;
        }
        let Some(value) = try_boxed(value) else {
            return OVERFLOW;
        };
        unsafe {
            owner.write(Box::into_raw(value));
        }
    } else {
        let value = unsafe { &mut *current };
        if let Err(error) = value.append(pattern, replacement, regex) {
            return error;
        }
    }
    0
}
/// # Safety
/// Null or live store, without concurrent mutation/destruction.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_rewrite_store_count(owner: *const HttpRewriteStore) -> usize {
    if owner.is_null() {
        0
    } else {
        unsafe { (*owner).rules.len() }
    }
}
/// Observe lengths with both capacities zero, or copy an entire immutable rule.
/// No store pointer is returned. Native scratch allocation happens between calls.
/// # Safety
/// Owner is live and index exists; record and nonzero output spans are writable,
/// disjoint from each other/store, with no concurrent mutation/destruction.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_rewrite_store_read(
    owner: *const HttpRewriteStore,
    index: usize,
    record: *mut HttpRewriteRecord,
    pattern: *mut u8,
    pattern_capacity: usize,
    replacement: *mut u8,
    replacement_capacity: usize,
) -> i32 {
    if owner.is_null() || record.is_null() {
        return INVALID;
    }
    let Some(rule) = (unsafe { &*owner }).rule(index) else {
        return INVALID;
    };
    let suffix = rule.bytes.len() - rule.split;
    let query = pattern_capacity == 0 && replacement_capacity == 0;
    if !query {
        if pattern_capacity < rule.split
            || replacement_capacity < suffix
            || (rule.split != 0 && pattern.is_null())
            || (suffix != 0 && replacement.is_null())
        {
            return INVALID;
        }
        if rule.split != 0 {
            unsafe {
                ptr::copy_nonoverlapping(rule.bytes.as_ptr(), pattern, rule.split);
            }
        }
        if suffix != 0 {
            unsafe {
                ptr::copy_nonoverlapping(rule.bytes.as_ptr().add(rule.split), replacement, suffix);
            }
        }
    }
    unsafe {
        record.write(HttpRewriteRecord {
            pattern_length: rule.split,
            replacement_length: suffix,
            regex: u32::from(rule.regex),
        });
    }
    0
}
/// Copy only the pattern (kind0) or replacement (kind1) at its actual Native
/// observation boundary. A zero capacity queries length without returning a view.
/// # Safety
/// Live unchanged owner; output and written are writable/disjoint from each
/// other and the owner. No concurrent mutation/destruction or Native effects.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_rewrite_store_text(
    owner: *const HttpRewriteStore,
    index: usize,
    kind: u32,
    output: *mut u8,
    capacity: usize,
    written: *mut usize,
) -> i32 {
    if written.is_null() || capacity != 0 && output.is_null() {
        return INVALID;
    }
    if capacity > isize::MAX as usize {
        return OVERFLOW;
    }
    let Some(owner) = (unsafe { owner.as_ref() }) else {
        return INVALID;
    };
    let Some(rule) = owner.rule(index) else {
        return INVALID;
    };
    let text = match kind {
        0 => &rule.bytes[..rule.split],
        1 => &rule.bytes[rule.split..],
        _ => return INVALID,
    };
    if capacity != 0 {
        if capacity < text.len() {
            return INVALID;
        }
        if !text.is_empty() {
            unsafe {
                ptr::copy_nonoverlapping(text.as_ptr(), output, text.len());
            }
        }
    }
    unsafe {
        written.write(text.len());
    }
    0
}
/// Apply a stored literal without materializing pattern/replacement in Native.
/// # Safety
/// Live immutable store; URL and output/written spans obey the existing literal
/// ABI contract and are disjoint from all store bytes and from each other.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_rewrite_store_literal(
    owner: *const HttpRewriteStore,
    index: usize,
    url: *const crate::HttpProxyText,
    output: *mut u8,
    capacity: usize,
    written: *mut usize,
) -> i32 {
    let (Some(owner), Some(url)) = (unsafe { owner.as_ref() }, unsafe { url.as_ref() }) else {
        return INVALID;
    };
    let Some(rule) = owner.rule(index) else {
        return INVALID;
    };
    let input = crate::HttpRewriteLiteral {
        url: crate::HttpProxyText {
            data: url.data,
            length: url.length,
        },
        pattern: crate::HttpProxyText {
            data: rule.bytes.as_ptr(),
            length: rule.split,
        },
        replacement: crate::HttpProxyText {
            data: unsafe { rule.bytes.as_ptr().add(rule.split) },
            length: rule.bytes.len() - rule.split,
        },
    };
    unsafe { crate::swr_v1_http_rewrite_literal(&input, output, capacity, written) }
}
/// Apply owned rule bytes directly to the distinct owned static context.
/// # Safety
/// Live immutable store and unique live disjoint context, without concurrent
/// mutation/destruction. No Native effect or pointer escapes this call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_rewrite_store_context_literal(
    owner: *const HttpRewriteStore,
    index: usize,
    context: *mut crate::HttpStaticContext,
) -> i32 {
    let Some(owner) = (unsafe { owner.as_ref() }) else {
        return INVALID;
    };
    let Some(rule) = owner.rule(index) else {
        return INVALID;
    };
    let Some(context) = (unsafe { context.as_mut() }) else {
        return INVALID;
    };
    context.rewrite_literal(&rule.bytes[..rule.split], &rule.bytes[rule.split..])
}
/// Consume copied control and consecutive literal misses entirely in Rust.
/// Returns only at a Native search(3), output allocation/fill(6), completion(0)
/// or existing error boundary. The existing FSM remains authoritative.
/// # Safety
/// Live immutable store; unique initialized state/action from the legacy rewrite
/// protocol, readable URL and writable index/required, all mutually disjoint.
/// Native effects run only after return; no owner borrow or operand is retained.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_rewrite_store_advance(
    owner: *const HttpRewriteStore,
    state: *mut crate::HttpRewriteState,
    mut action: i32,
    url: *const crate::HttpProxyText,
    index: *mut usize,
    required: *mut usize,
) -> i32 {
    let (Some(store), Some(state), Some(url), Some(index), Some(required)) = (
        unsafe { owner.as_ref() },
        unsafe { state.as_mut() },
        unsafe { url.as_ref() },
        unsafe { index.as_mut() },
        unsafe { required.as_mut() },
    ) else {
        return INVALID;
    };
    loop {
        let observed = match action {
            1 => {
                let Some(rule) = store.rule(*index) else {
                    return INVALID;
                };
                if rule.regex { 2 } else { 1 }
            }
            2 => match store.rule(*index).and_then(|rule| {
                unsafe { bytes(url.data, url.length) }.ok().and_then(|url| {
                    crate::rewrite::literal_suffix(
                        url,
                        &rule.bytes[..rule.split],
                        rule.bytes.len() - rule.split,
                    )
                    .ok()
                    .flatten()
                })
            }) {
                Some((_, length)) => {
                    *required = length;
                    7
                }
                None => 3,
            },
            _ => return action,
        };
        action = state.legacy_step(0, observed, index);
    }
}
/// Consume the same literal prefix chain directly into the distinct owned
/// context, returning only when Native regex effects or completion are needed.
/// # Safety
/// Live immutable store and unique live initialized disjoint context/action/index;
/// Native effects only after return. No Rust borrow or pointer escapes.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_rewrite_store_context_advance(
    owner: *const HttpRewriteStore,
    context: *mut crate::HttpStaticContext,
    mut action: i32,
    index: *mut usize,
) -> i32 {
    let (Some(store), Some(context), Some(index)) = (
        unsafe { owner.as_ref() },
        unsafe { context.as_mut() },
        unsafe { index.as_mut() },
    ) else {
        return INVALID;
    };
    loop {
        let observed = match action {
            1 => {
                let Some(rule) = store.rule(*index) else {
                    return INVALID;
                };
                if rule.regex { 2 } else { 1 }
            }
            2 => {
                let Some(rule) = store.rule(*index) else {
                    return -3;
                };
                let matched =
                    context.rewrite_literal(&rule.bytes[..rule.split], &rule.bytes[rule.split..]);
                // Preserve the prior Native literal caller's bad_alloc mapping
                // for any negative literal result; state errors remain INVALID.
                if matched < 0 {
                    return -3;
                }
                if matched == 1 { 4 } else { 3 }
            }
            _ => return action,
        };
        action = context.rewrite_step(0, observed, index);
    }
}
/// # Safety
/// Unique null/live owner with no active readers; resets caller custody to null.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_rewrite_store_drop(owner: *mut *mut HttpRewriteStore) {
    if !owner.is_null() {
        let value = unsafe { owner.replace(ptr::null_mut()) };
        if !value.is_null() {
            drop(unsafe { Box::from_raw(value) });
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn literal_batch_stops_at_native_regex_and_output_allocation_boundaries() {
        unsafe {
            let mut store = ptr::null_mut();
            for (pattern, replacement) in [
                (b"/missing".as_slice(), b"/wrong".as_slice()),
                (b"~^/file~".as_slice(), b"/regex".as_slice()),
                (b"/file".as_slice(), b"/literal".as_slice()),
            ] {
                assert_eq!(
                    swr_v2_http_rewrite_store_add(
                        &mut store,
                        pattern.as_ptr(),
                        pattern.len(),
                        replacement.as_ptr(),
                        replacement.len()
                    ),
                    0
                );
            }
            let url = crate::HttpProxyText {
                data: b"/file/tail".as_ptr(),
                length: b"/file/tail".len(),
            };
            let mut state = crate::HttpRewriteState::default();
            let mut index = 0;
            let mut required = 777;
            let action = crate::swr_v2_http_rewrite_step(
                &mut state,
                3,
                0,
                ptr::null(),
                ptr::null(),
                &mut index,
            );
            assert_eq!(
                swr_v2_http_rewrite_store_advance(
                    store,
                    &mut state,
                    action,
                    &url,
                    &mut index,
                    &mut required
                ),
                3
            );
            assert_eq!(index, 1);
            assert_eq!(required, 777);
            // Copied unmatched/equal-regex observation; no Native effect is
            // performed through Rust. The actual Native driver covers regex.
            let action = crate::swr_v2_http_rewrite_step(
                &mut state,
                0,
                3,
                ptr::null(),
                ptr::null(),
                &mut index,
            );
            assert_eq!(
                swr_v2_http_rewrite_store_advance(
                    store,
                    &mut state,
                    action,
                    &url,
                    &mut index,
                    &mut required
                ),
                6
            );
            assert_eq!(index, 2);
            assert_eq!(required, b"/literal/tail".len());
            let mut value = vec![0; required];
            assert_eq!(
                swr_v2_http_rewrite_store_literal(
                    store,
                    index,
                    &url,
                    value.as_mut_ptr(),
                    value.len(),
                    &mut required
                ),
                1
            );
            assert_eq!(value, b"/literal/tail");
            assert_eq!(
                crate::swr_v2_http_rewrite_step(
                    &mut state,
                    0,
                    4,
                    ptr::null(),
                    ptr::null(),
                    &mut index
                ),
                5
            );
            let context = crate::swr_v2_http_context_new(url.data, url.length, 128);
            assert!(!context.is_null());
            let action = crate::swr_v2_http_context_rewrite_step(context, 3, 0, &mut index);
            assert_eq!(
                swr_v2_http_rewrite_store_context_advance(store, context, action, &mut index),
                3
            );
            assert_eq!(index, 1);
            let action = crate::swr_v2_http_context_rewrite_step(context, 0, 3, &mut index);
            assert_eq!(
                swr_v2_http_rewrite_store_context_advance(store, context, action, &mut index),
                0
            );
            assert_eq!(index, 2);
            let mut value = vec![0; 32];
            assert_eq!(
                crate::swr_v2_http_context_text(
                    context,
                    0,
                    value.as_mut_ptr(),
                    value.len(),
                    &mut required
                ),
                0
            );
            value.truncate(required);
            assert_eq!(value, b"/literal/tail");
            crate::swr_v2_http_context_drop(context);
            swr_v2_http_rewrite_store_drop(&mut store);
        }
    }
    #[test]
    fn stored_literal_applies_without_native_rule_snapshots() {
        unsafe {
            let mut owner = ptr::null_mut();
            assert_eq!(
                swr_v2_http_rewrite_store_add(
                    &mut owner,
                    b"/first".as_ptr(),
                    6,
                    b"one".as_ptr(),
                    3
                ),
                0
            );
            let url = crate::HttpProxyText {
                data: b"/first/tail".as_ptr(),
                length: 11,
            };
            let mut length = 0;
            assert_eq!(
                swr_v2_http_rewrite_store_literal(owner, 0, &url, ptr::null_mut(), 0, &mut length),
                1
            );
            let mut output = vec![0; length];
            assert_eq!(
                swr_v2_http_rewrite_store_literal(
                    owner,
                    0,
                    &url,
                    output.as_mut_ptr(),
                    output.len(),
                    &mut length
                ),
                1
            );
            assert_eq!(output, b"one/tail");
            let context = crate::swr_v2_http_context_new(url.data, url.length, 128);
            assert!(!context.is_null());
            assert_eq!(
                swr_v2_http_rewrite_store_context_literal(owner, 0, context),
                1
            );
            let mut actual = vec![0; 32];
            assert_eq!(
                crate::swr_v2_http_context_text(
                    context,
                    0,
                    actual.as_mut_ptr(),
                    actual.len(),
                    &mut length
                ),
                0
            );
            actual.truncate(length);
            assert_eq!(actual, b"one/tail");
            crate::swr_v2_http_context_drop(context);
            swr_v2_http_rewrite_store_drop(&mut owner);
        }
    }
    #[test]
    fn growing_store_retains_declaration_order_and_earlier_copies() {
        unsafe {
            let mut owner = ptr::null_mut();
            for index in 0..257 {
                let pattern = format!("/prefix/{index}");
                let replacement = format!("/target/{index}");
                assert_eq!(
                    swr_v2_http_rewrite_store_add(
                        &mut owner,
                        pattern.as_ptr(),
                        pattern.len(),
                        replacement.as_ptr(),
                        replacement.len()
                    ),
                    0
                );
            }
            assert_eq!(swr_v2_http_rewrite_store_count(owner), 257);
            for index in 0..257 {
                let mut record = HttpRewriteRecord::default();
                assert_eq!(
                    swr_v2_http_rewrite_store_read(
                        owner,
                        index,
                        &mut record,
                        ptr::null_mut(),
                        0,
                        ptr::null_mut(),
                        0
                    ),
                    0
                );
                let mut pattern = vec![0; record.pattern_length];
                let mut replacement = vec![0; record.replacement_length];
                assert_eq!(
                    swr_v2_http_rewrite_store_read(
                        owner,
                        index,
                        &mut record,
                        pattern.as_mut_ptr(),
                        pattern.len(),
                        replacement.as_mut_ptr(),
                        replacement.len()
                    ),
                    0
                );
                assert_eq!(pattern, format!("/prefix/{index}").as_bytes());
                assert_eq!(replacement, format!("/target/{index}").as_bytes());
            }
            swr_v2_http_rewrite_store_drop(&mut owner);
        }
    }
    #[test]
    fn catalog_growth_keeps_earlier_literal_results_and_canaries() {
        unsafe {
            let mut owner = ptr::null_mut();
            let mut expected = Vec::new();
            for index in 0..65 {
                let pattern = format!("/path/{index}/");
                let replacement = "x".repeat(index * 17);
                assert_eq!(
                    swr_v2_http_rewrite_store_add(
                        &mut owner,
                        pattern.as_ptr(),
                        pattern.len(),
                        replacement.as_ptr(),
                        replacement.len()
                    ),
                    0
                );
                expected.push((pattern, replacement));
                // Reobserve old rules through real literal/copy APIs after
                // repeated admissions; no pointer into catalog storage escapes.
                if index % 8 == 0 {
                    for (rule, (pattern, replacement)) in expected.iter().enumerate() {
                        let url = format!("{pattern}tail");
                        let span = crate::HttpProxyText {
                            data: url.as_ptr(),
                            length: url.len(),
                        };
                        let mut length = 0;
                        assert_eq!(
                            swr_v2_http_rewrite_store_literal(
                                owner,
                                rule,
                                &span,
                                ptr::null_mut(),
                                0,
                                &mut length
                            ),
                            1
                        );
                        let mut output = vec![0xcc; length + 17];
                        assert_eq!(
                            swr_v2_http_rewrite_store_literal(
                                owner,
                                rule,
                                &span,
                                output.as_mut_ptr(),
                                length,
                                &mut length
                            ),
                            1
                        );
                        assert_eq!(&output[..length], format!("{replacement}tail").as_bytes());
                        assert!(output[length..].iter().all(|&byte| byte == 0xcc));
                    }
                }
            }
            swr_v2_http_rewrite_store_drop(&mut owner);
        }
    }
    #[test]
    fn ordered_binary_rules_are_copied_without_borrowing_storage() {
        unsafe {
            let mut owner = ptr::null_mut();
            assert_eq!(swr_v2_http_rewrite_store_count(owner), 0);
            type Case<'a> = (&'a [u8], &'a [u8], &'a [u8], u32);
            let cases: &[Case<'_>] = &[
                (b"/first", b"one", b"/first", 0),
                (b"~a\0b~", b"r\0x", b"a\0b", 1),
                (b"/first", b"two", b"/first", 0),
                (b"~~", b"", b"", 1),
                (b"", b"empty", b"", 0),
            ];
            for &(pattern, replacement, _, _) in cases {
                assert_eq!(
                    swr_v2_http_rewrite_store_add(
                        &mut owner,
                        pattern.as_ptr(),
                        pattern.len(),
                        replacement.as_ptr(),
                        replacement.len()
                    ),
                    0
                );
            }
            assert_eq!(swr_v2_http_rewrite_store_count(owner), cases.len());
            for (index, &(_, replacement, pattern, regex)) in cases.iter().enumerate() {
                let mut record = HttpRewriteRecord::default();
                assert_eq!(
                    swr_v2_http_rewrite_store_read(
                        owner,
                        index,
                        &mut record,
                        ptr::null_mut(),
                        0,
                        ptr::null_mut(),
                        0
                    ),
                    0
                );
                assert_eq!(
                    record,
                    HttpRewriteRecord {
                        pattern_length: pattern.len(),
                        replacement_length: replacement.len(),
                        regex
                    }
                );
                let mut a = vec![0; record.pattern_length];
                let mut b = vec![0; record.replacement_length];
                assert_eq!(
                    swr_v2_http_rewrite_store_read(
                        owner,
                        index,
                        &mut record,
                        a.as_mut_ptr(),
                        a.len(),
                        b.as_mut_ptr(),
                        b.len()
                    ),
                    0
                );
                assert_eq!(a, pattern);
                assert_eq!(b, replacement);
                for (kind, expected) in [(0, pattern), (1, replacement)] {
                    let mut length = 0;
                    assert_eq!(
                        swr_v2_http_rewrite_store_text(
                            owner,
                            index,
                            kind,
                            ptr::null_mut(),
                            0,
                            &mut length
                        ),
                        0
                    );
                    let mut text = vec![0; length];
                    assert_eq!(
                        swr_v2_http_rewrite_store_text(
                            owner,
                            index,
                            kind,
                            text.as_mut_ptr(),
                            text.len(),
                            &mut length
                        ),
                        0
                    );
                    assert_eq!(text, expected);
                }
            }
            swr_v2_http_rewrite_store_drop(&mut owner);
            assert!(owner.is_null());
        }
    }
}
