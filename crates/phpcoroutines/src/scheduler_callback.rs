//! Sole Scheduler exit-condition identity. Native retains Zend Callable effects.
use crate::configure::{ConfigurePlan, ConfigureState, swr_v1_phpcoroutines_configure};
use crate::scheduler_control::{SchedulerConstants, swr_v1_phpcoroutines_scheduler_control};
use core::cell::UnsafeCell;

#[repr(C)]
pub struct SchedulerCallbackOwner {
    identity: UnsafeCell<usize>,
}
#[repr(C)]
pub struct OwnedConfigurePlan {
    plan: ConfigurePlan,
    identity: usize,
}
#[repr(C)]
#[derive(Default)]
pub struct CallbackControlState {
    stage: u32,
    asserted: u8,
}
#[repr(C)]
pub struct CallbackControlPlan {
    action: u32,
    identity: usize,
}
/// # Safety
/// Exclusive stack state is zero-seeded; owner is the single constant-zero Native
/// global cell under original defined serialization. No aliasing state/owner.
/// `created` is an opaque identity returned by the last requested Native creation.
/// No referent is interpreted; no borrow survives Native effects. During Native
/// free/create the old identity stays published exactly until creation returns.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_configure_owned(
    state: *mut ConfigureState,
    owner: *mut SchedulerCallbackOwner,
    mut observation: u8,
    created: usize,
) -> OwnedConfigurePlan {
    let identity = unsafe { (*owner).identity.get() };
    if unsafe { (*state).stage } == 10 {
        unsafe { identity.write(created) };
        observation = u8::from(created != 0);
    }
    loop {
        let plan = unsafe { swr_v1_phpcoroutines_configure(state, observation) };
        if plan.action == 7 {
            observation = u8::from(unsafe { identity.read() } != 0);
            continue;
        }
        let token = if plan.action == 8 {
            unsafe { identity.read() }
        } else {
            0
        };
        return OwnedConfigurePlan {
            plan,
            identity: token,
        };
    }
}
/// # Safety
/// State is exclusive zeroed local POD and fixed kind callback0 or shutdown2.
/// Owner has the original single Native global scope and defined serialization;
/// no new thread-safety guarantee. Constants/observation obey the existing control
/// contract. Native asserts/calls/frees only after return, then refreshes facts.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_callback_control(
    state: *mut CallbackControlState,
    owner: *mut SchedulerCallbackOwner,
    kind: u32,
    mut observation: i64,
    constants: *const SchedulerConstants,
) -> CallbackControlPlan {
    let identity = unsafe { (*owner).identity.get() };
    let state = unsafe { &mut *state };
    if kind == 0 && state.asserted == 0 {
        state.asserted = 1;
        return CallbackControlPlan {
            action: 18,
            identity: unsafe { identity.read() },
        };
    }
    loop {
        let action = unsafe {
            swr_v1_phpcoroutines_scheduler_control(&mut state.stage, kind, observation, constants)
        };
        match action {
            13 => {
                observation = i64::from(unsafe { identity.read() } != 0);
            }
            15 => {
                unsafe { identity.write(0) };
            }
            _ => {
                return CallbackControlPlan {
                    action,
                    identity: if action == 1 || action == 14 {
                        unsafe { identity.read() }
                    } else {
                        0
                    },
                };
            }
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn configure_replaces_only_after_native_creation_returns() {
        for initial in [0, 71] {
            for created in [0, 91] {
                let mut owner = SchedulerCallbackOwner {
                    identity: UnsafeCell::new(initial),
                };
                let mut state = ConfigureState::default();
                let mut actions = Vec::new();
                loop {
                    let p = unsafe {
                        swr_v1_phpcoroutines_configure_owned(&mut state, &mut owner, 1, created)
                    };
                    actions.push(p.plan.action);
                    if p.plan.action == 8 {
                        assert_eq!(p.identity, initial);
                    }
                    if p.plan.action == 9 {
                        assert_eq!(unsafe { *owner.identity.get() }, initial);
                    }
                    if p.plan.action == 0 {
                        break;
                    }
                }
                assert_eq!(actions.contains(&8), initial != 0);
                assert_eq!(actions.contains(&10), created != 0);
                assert_eq!(unsafe { *owner.identity.get() }, created);
            }
        }
    }
    #[test]
    fn callback_refreshes_identity_and_shutdown_clears_after_free() {
        let mut owner = SchedulerCallbackOwner {
            identity: UnsafeCell::new(71),
        };
        let constants = SchedulerConstants {
            success: 0,
            false_tag: 7,
            php_resolver: 9,
        };
        let mut state = CallbackControlState::default();
        let p = unsafe {
            swr_v1_phpcoroutines_callback_control(&mut state, &mut owner, 0, 0, &constants)
        };
        assert_eq!((p.action, p.identity), (18, 71));
        unsafe {
            *owner.identity.get() = 81;
        }
        let p = unsafe {
            swr_v1_phpcoroutines_callback_control(&mut state, &mut owner, 0, 0, &constants)
        };
        assert_eq!((p.action, p.identity), (1, 81));
        let mut state = CallbackControlState::default();
        let p = unsafe {
            swr_v1_phpcoroutines_callback_control(&mut state, &mut owner, 2, 0, core::ptr::null())
        };
        assert_eq!(p.action, 12);
        let p = unsafe {
            swr_v1_phpcoroutines_callback_control(&mut state, &mut owner, 2, 0, core::ptr::null())
        };
        assert_eq!((p.action, p.identity), (14, 81));
        assert_eq!(unsafe { *owner.identity.get() }, 81);
        let p = unsafe {
            swr_v1_phpcoroutines_callback_control(&mut state, &mut owner, 2, 0, core::ptr::null())
        };
        assert_eq!((p.action, unsafe { *owner.identity.get() }), (0, 0));
    }
}
