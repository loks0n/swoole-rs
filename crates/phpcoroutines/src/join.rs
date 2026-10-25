//! Sole join identity-set/cancellation metadata. Native payloads never enter Rust.
use std::cell::UnsafeCell;
use std::sync::atomic::{AtomicUsize, Ordering, fence};

pub struct JoinOwner {
    references: AtomicUsize,
    tokens: UnsafeCell<Vec<usize>>,
    canceled: UnsafeCell<bool>,
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_phpcoroutines_join_try_new() -> *mut JoinOwner {
    crate::allocation::try_owned(JoinOwner {
        references: AtomicUsize::new(1),
        tokens: UnsafeCell::new(Vec::new()),
        canceled: UnsafeCell::new(false),
    })
}
/// # Safety
/// Owner has a live strong reference held throughout this call. Independent
/// Native capture copies/drops may overlap; payload access may not. Failed
/// refcount admission leaves ownership unchanged and executes no Native effect.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_join_clone(owner: *const JoinOwner) -> u8 {
    let references = unsafe { &(*owner).references };
    u8::from(
        references
            .fetch_update(Ordering::Relaxed, Ordering::Relaxed, |count| {
                count
                    .checked_add(1)
                    .filter(|next| *next <= isize::MAX as usize)
            })
            .is_ok(),
    )
}
/// # Safety
/// Consume one live strong reference exactly once, after all uses of that
/// reference. Final drop frees Rust metadata only, never token referents. Native
/// lifetime/capture validity is authoritative, as for the original shared_ptr.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_join_drop(owner: *const JoinOwner) {
    if unsafe { (*owner).references.fetch_sub(1, Ordering::Release) } == 1 {
        fence(Ordering::Acquire);
        unsafe { drop(Box::from_raw(owner.cast_mut())) };
    }
}
/// # Safety
/// A live strong reference is held. Payload access is serial/exclusive under the
/// original Native set/canceled contract. Token is identity only; it is never
/// interpreted, dereferenced or converted into a pointer in Rust. Ordering is
/// the qualified Native uintptr_t/pointer-order correspondence on supported ABIs.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_join_try_insert(
    owner: *const JoinOwner,
    token: usize,
) -> u8 {
    let tokens = unsafe { &mut *(*owner).tokens.get() };
    if let Err(index) = tokens.binary_search(&token) {
        if tokens.try_reserve(1).is_err() {
            return 0;
        }
        tokens.insert(index, token);
    }
    1
}
/// # Safety
/// Same live/serial payload contract as insertion. Erase precedes the returned
/// emptiness decision, including missing-token/empty-set behavior.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_join_erase_empty(
    owner: *const JoinOwner,
    token: usize,
) -> u8 {
    let tokens = unsafe { &mut *(*owner).tokens.get() };
    if let Ok(index) = tokens.binary_search(&token) {
        tokens.remove(index);
    }
    u8::from(tokens.is_empty())
}
/// # Safety
/// Owner is held live, payload reads are serial with writes as in Native.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_join_empty(owner: *const JoinOwner) -> u8 {
    u8::from(unsafe { &*(*owner).tokens.get() }.is_empty())
}
/// # Safety
/// Owner is held live with serial payload access. Cursor/output are writable,
/// distinct local POD and cannot alias metadata. Cursor starts at zero; no token
/// mutation occurs during traversal. Empty leaves cursor/output untouched.
/// Iteration does not erase membership before Native clears on_close fields.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_join_next(
    owner: *const JoinOwner,
    cursor: *mut usize,
    output: *mut usize,
) -> u8 {
    let tokens = unsafe { &*(*owner).tokens.get() };
    let index = unsafe { *cursor };
    if let Some(token) = tokens.get(index) {
        unsafe {
            *output = *token;
            *cursor = index + 1;
        }
        1
    } else {
        0
    }
}
/// # Safety
/// A live reference is held and membership access is serial. The original
/// Native stack-set scope has ended; subsequent captures access only the flag.
/// Release capacity without dropping token referents or cancellation custody.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_join_release_membership(owner: *const JoinOwner) {
    drop(unsafe { std::mem::take(&mut *(*owner).tokens.get()) });
}
/// # Safety
/// Owner is held live with original Native serial canceled-flag access. This
/// publication occurs only after Native callback-field cleanup completes.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_join_cancel(owner: *const JoinOwner) {
    unsafe { *(*owner).canceled.get() = true };
}
/// # Safety
/// Owner is held live with original Native serial canceled-flag access. Native
/// resumes only after this decision returns; no Rust frame/borrow spans resume.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_join_can_resume(owner: *const JoinOwner) -> u8 {
    u8::from(!unsafe { *(*owner).canceled.get() })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn identity_set_iteration_and_cancellation_are_sole_metadata() {
        let owner = swr_v1_phpcoroutines_join_try_new();
        assert!(!owner.is_null());
        unsafe {
            assert_eq!(swr_v1_phpcoroutines_join_empty(owner), 1);
            assert_eq!(swr_v1_phpcoroutines_join_erase_empty(owner, 99), 1);
            for token in [71, 0, 19, 71, usize::MAX] {
                assert_eq!(swr_v1_phpcoroutines_join_try_insert(owner, token), 1);
            }
            let mut cursor = 0;
            let mut token = 99;
            let mut actual = Vec::new();
            while swr_v1_phpcoroutines_join_next(owner, &mut cursor, &mut token) != 0 {
                actual.push(token);
            }
            assert_eq!(actual, vec![0, 19, 71, usize::MAX]);
            assert_eq!(swr_v1_phpcoroutines_join_empty(owner), 0);
            let before = (cursor, token);
            assert_eq!(
                swr_v1_phpcoroutines_join_next(owner, &mut cursor, &mut token),
                0
            );
            assert_eq!((cursor, token), before);
            assert_eq!(swr_v1_phpcoroutines_join_erase_empty(owner, 99), 0);
            for token in [0, 19, 71] {
                assert_eq!(swr_v1_phpcoroutines_join_erase_empty(owner, token), 0);
            }
            assert_eq!(swr_v1_phpcoroutines_join_erase_empty(owner, usize::MAX), 1);
            assert_eq!(swr_v1_phpcoroutines_join_can_resume(owner), 1);
            assert_eq!(swr_v1_phpcoroutines_join_clone(owner), 1);
            assert_eq!(swr_v1_phpcoroutines_join_try_insert(owner, 23), 1);
            swr_v1_phpcoroutines_join_release_membership(owner);
            assert_eq!(swr_v1_phpcoroutines_join_empty(owner), 1);
            assert_eq!((*(*owner).tokens.get()).capacity(), 0);
            swr_v1_phpcoroutines_join_drop(owner); // other strong owner remains
            swr_v1_phpcoroutines_join_cancel(owner);
            assert_eq!(swr_v1_phpcoroutines_join_can_resume(owner), 0);
            swr_v1_phpcoroutines_join_drop(owner);
        }
    }
}
