//! Sole channel token storage. Native code owns every pointed-to object.

use std::alloc::{Layout, alloc};
use std::collections::VecDeque;
use std::ffi::c_void;
use std::ptr::{self, NonNull};

pub struct ChannelTokens(pub(crate) VecDeque<*mut c_void>);

impl ChannelTokens {
    pub(crate) fn try_push(
        &mut self,
        token: *mut c_void,
    ) -> Result<(), std::collections::TryReserveError> {
        self.0.try_reserve(1)?;
        self.0.push_back(token);
        Ok(())
    }

    // Fallible admission precedes clone observation; Box alone owns cleanup.
    fn try_new() -> Option<Box<Self>> {
        #[expect(
            clippy::cast_ptr_alignment,
            reason = "alloc honours Layout::new::<ChannelTokens>()"
        )]
        // SAFETY: `ChannelTokens` is not zero-sized; null is handled by `NonNull::new`.
        let raw = NonNull::new(unsafe { alloc(Layout::new::<Self>()).cast::<Self>() })?;
        // SAFETY: a fresh, non-null allocation with this type's layout.
        unsafe { raw.as_ptr().write(Self(VecDeque::new())) };
        // SAFETY: a global allocation with `Box`'s layout, initialized above.
        Some(unsafe { Box::from_raw(raw.as_ptr()) })
    }
}

/// Fallible allocation; Native may throw only after return. No payload is released.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_channel_tokens_new() -> *mut ChannelTokens {
    ChannelTokens::try_new().map_or(ptr::null_mut(), Box::into_raw)
}

/// # Safety
/// `tokens` is a live owner with no concurrent mutation. This copies identities
/// only, matching native pointer-container copying without copying payloads.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_channel_tokens_clone(
    tokens: *const ChannelTokens,
) -> *mut ChannelTokens {
    let Some(mut copy) = ChannelTokens::try_new() else {
        return ptr::null_mut();
    };
    // SAFETY: `tokens` is a live owner with no concurrent mutation.
    let source = unsafe { &(*tokens).0 };
    if copy.0.try_reserve(source.len()).is_err() {
        return ptr::null_mut();
    }
    copy.0.extend(source.iter().copied());
    Box::into_raw(copy)
}

/// # Safety
/// `tokens` is null or an exclusive live owner returned by `tokens_new`.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_channel_tokens_free(tokens: *mut ChannelTokens) {
    if !tokens.is_null() {
        // SAFETY: an exclusive, live owner from `tokens_new`, freed once.
        drop(unsafe { Box::from_raw(tokens) });
    }
}

/// # Safety
/// `tokens` is a live owner, with no concurrent mutation.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_channel_tokens_len(tokens: *const ChannelTokens) -> usize {
    // SAFETY: per this function's `# Safety` contract, `tokens` is live, aligned and initialized.
    unsafe { (*tokens).0.len() }
}

/// # Safety
/// `tokens` is an exclusive live owner; the token is opaque and never accessed.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_channel_tokens_push(
    tokens: *mut ChannelTokens,
    token: *mut c_void,
) -> i32 {
    // SAFETY: per this function's `# Safety` contract, `tokens` is live, aligned and exclusive.
    unsafe { &mut *tokens }.try_push(token).map_or(-1, |()| 0)
}

/// # Safety
/// `tokens` is live and `output` is writable. They do not alias. Null token
/// values are valid: the separate status distinguishes them from an empty FIFO.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_channel_tokens_front(
    tokens: *const ChannelTokens,
    output: *mut *mut c_void,
) -> i32 {
    // SAFETY: per this function's `# Safety` contract, `tokens` is live, aligned and initialized.
    match unsafe { (*tokens).0.front() } {
        Some(&token) => {
            // SAFETY: per this function's `# Safety` contract, `output` is live, aligned and writable.
            unsafe { output.write(token) };
            1
        }
        None => 0,
    }
}

/// # Safety
/// `tokens` is an exclusive live owner. Removed tokens remain native-owned.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_channel_tokens_pop(tokens: *mut ChannelTokens) {
    // SAFETY: per this function's `# Safety` contract, `tokens` is live, aligned and initialized.
    unsafe { (*tokens).0.pop_front() };
}

/// Preserve std::list::remove's removal of *all* matching pointer identities.
/// # Safety
/// `tokens` is an exclusive live owner; no pointed-to object is accessed.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_channel_tokens_remove(
    tokens: *mut ChannelTokens,
    token: *mut c_void,
) {
    // SAFETY: per this function's `# Safety` contract, `tokens` is live, aligned and initialized.
    unsafe { (*tokens).0.retain(|&entry| entry != token) };
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fifo_wrap_growth_nulls_and_remove_all_match_native_contract() {
        let owner = swr_v1_channel_tokens_new();
        assert!(!owner.is_null());
        let mut first = 1_u8;
        let mut second = 2_u8;
        let a = ptr::from_mut(&mut first).cast();
        let b = ptr::from_mut(&mut second).cast();
        unsafe {
            for _ in 0..1024 {
                for token in [a, ptr::null_mut(), b, a] {
                    assert_eq!(swr_v1_channel_tokens_push(owner, token), 0);
                }
                swr_v1_channel_tokens_pop(owner);
            }
            assert_eq!(swr_v1_channel_tokens_len(owner), 3072);
            let copy = swr_v1_channel_tokens_clone(owner);
            assert!(!copy.is_null());
            assert_eq!(swr_v1_channel_tokens_len(copy), 3072);
            swr_v1_channel_tokens_remove(owner, a);
            let mut count = 0;
            let mut out = a;
            while swr_v1_channel_tokens_front(owner, &mut out) == 1 {
                assert_eq!(out, if count % 2 == 0 { ptr::null_mut() } else { b });
                swr_v1_channel_tokens_pop(owner);
                count += 1;
            }
            assert_eq!(count, 1536);
            assert_eq!(swr_v1_channel_tokens_len(owner), 0);
            assert_eq!(swr_v1_channel_tokens_len(copy), 3072);
            swr_v1_channel_tokens_free(copy);
            swr_v1_channel_tokens_free(owner);
            swr_v1_channel_tokens_free(ptr::null_mut());
        }
        assert_eq!((first, second), (1, 2));
    }
}
