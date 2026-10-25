//! Sole primitive frontend configuration, in the original native TLS/global slot.
//! A zero disable bit preserves the original enabled deadlock-check default;
//! the native compile-time maximum seed needs no dynamic initializer.
#[repr(C)]
pub struct ConfigState {
    pub max_num: u64,
    pub hook_flags: u32,
    pub preemptive: u8,
    pub disable_deadlock: u8,
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
    match operation {
        0 => unsafe { std::ptr::read(std::ptr::addr_of!((*state).max_num)) },
        1 => {
            unsafe { std::ptr::write(std::ptr::addr_of_mut!((*state).max_num), value) };
            value
        }
        2 => u64::from(unsafe { std::ptr::read(std::ptr::addr_of!((*state).hook_flags)) }),
        3 => {
            let flags = value as u32;
            unsafe { std::ptr::write(std::ptr::addr_of_mut!((*state).hook_flags), flags) };
            u64::from(flags)
        }
        4 => u64::from(unsafe { std::ptr::read(std::ptr::addr_of!((*state).preemptive)) } != 0),
        5 => {
            let enabled = u8::from(value != 0);
            unsafe { std::ptr::write(std::ptr::addr_of_mut!((*state).preemptive), enabled) };
            u64::from(enabled)
        }
        6 => {
            u64::from(unsafe { std::ptr::read(std::ptr::addr_of!((*state).disable_deadlock)) } == 0)
        }
        7 => {
            let disabled = u8::from(value == 0);
            unsafe { std::ptr::write(std::ptr::addr_of_mut!((*state).disable_deadlock), disabled) };
            u64::from(value != 0)
        }
        _ => 0,
    }
}
