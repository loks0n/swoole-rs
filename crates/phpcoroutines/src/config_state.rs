//! Sole primitive frontend configuration, in the original native TLS/global slot.
//! A zero disable bit preserves the original enabled deadlock-check default;
//! the native compile-time maximum seed needs no dynamic initializer.
use std::mem::offset_of;

#[repr(C)]
pub struct ConfigState {
    pub max_num: u64,
    pub hook_flags: u32,
    pub preemptive: u8,
    pub disable_deadlock: u8,
}

// The address of one field inside `state`, computed without dereferencing it.
fn field<T>(state: *mut ConfigState, offset: usize) -> *mut T {
    state.wrapping_byte_add(offset).cast()
}

/// # Safety
/// State is a live aligned module-local POD, constantly initialized with the
/// configured maximum and zero remaining fields. Native scope owns its lifetime.
/// Each operation accesses only its corresponding original field. Concurrent
/// reads or disjoint-field operations need no whole-state exclusive borrow;
/// writes racing reads/writes of that same field remain outside the original
/// defined native contract. No Zend memory or borrow enters this operation.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_config(
    state: *mut ConfigState,
    operation: u32,
    value: u64,
) -> u64 {
    // Each operation reads or writes exactly its own field of the caller's live, aligned,
    // initialized state; same-field races are outside the native contract.
    match operation {
        // SAFETY: as above.
        0 => unsafe { field::<u64>(state, offset_of!(ConfigState, max_num)).read() },
        1 => {
            // SAFETY: as above.
            unsafe { field::<u64>(state, offset_of!(ConfigState, max_num)).write(value) };
            value
        }
        // SAFETY: as above.
        2 => u64::from(unsafe { field::<u32>(state, offset_of!(ConfigState, hook_flags)).read() }),
        3 => {
            #[expect(
                clippy::cast_possible_truncation,
                reason = "the native uint32_t hook flags"
            )]
            let flags = value as u32;
            // SAFETY: as above.
            unsafe { field::<u32>(state, offset_of!(ConfigState, hook_flags)).write(flags) };
            u64::from(flags)
        }
        // SAFETY: as above.
        4 => u64::from(
            unsafe { field::<u8>(state, offset_of!(ConfigState, preemptive)).read() } != 0,
        ),
        5 => {
            let enabled = u8::from(value != 0);
            // SAFETY: as above.
            unsafe { field::<u8>(state, offset_of!(ConfigState, preemptive)).write(enabled) };
            u64::from(enabled)
        }
        6 => {
            // SAFETY: as above.
            u64::from(
                unsafe { field::<u8>(state, offset_of!(ConfigState, disable_deadlock)).read() }
                    == 0,
            )
        }
        7 => {
            let disabled = u8::from(value == 0);
            // SAFETY: as above.
            unsafe {
                field::<u8>(state, offset_of!(ConfigState, disable_deadlock)).write(disabled)
            };
            u64::from(value != 0)
        }
        _ => 0,
    }
}
