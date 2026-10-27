//! Complete `Scheduler::set` ordered lookup and exit-condition publication policy.
use std::ffi::c_char;
#[repr(C)]
#[derive(Default)]
pub struct ConfigureState {
    pub stage: u32,
    pub created: u8,
}
#[repr(C)]
pub struct ConfigurePlan {
    pub action: u32,
    pub key: *const c_char,
    pub key_length: usize,
}
impl ConfigurePlan {
    fn action(action: u32) -> Self {
        Self {
            action,
            key: std::ptr::null(),
            key_length: 0,
        }
    }
    fn lookup(action: u32, key: &'static [u8]) -> Self {
        Self {
            action,
            key: key.as_ptr().cast(),
            key_length: key.len() - 1,
        }
    }
}
/// # Safety
/// Native stack state is exclusive writable POD, initially zeroed. Observations
/// are freshly requested presence facts only; native pointers never enter Rust.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_configure(
    state: *mut ConfigureState,
    observation: u8,
) -> ConfigurePlan {
    // SAFETY: per this function's `# Safety` contract, `state` is live, aligned and exclusive.
    let state = unsafe { &mut *state };
    loop {
        let stage = state.stage;
        state.stage = stage.saturating_add(1);
        return match stage {
            0 => ConfigurePlan::action(1),
            1 => ConfigurePlan::action(2),
            2 => ConfigurePlan::lookup(3, b"dns_cache_expire\0"),
            3 if observation != 0 => ConfigurePlan::action(4),
            3 => continue,
            4 => ConfigurePlan::lookup(3, b"dns_cache_capacity\0"),
            5 if observation != 0 => ConfigurePlan::action(5),
            5 => continue,
            6 => ConfigurePlan::lookup(6, b"exit_condition\0"),
            7 if observation != 0 => ConfigurePlan::action(7),
            7 => {
                state.stage = 99;
                ConfigurePlan::action(0)
            }
            8 if observation != 0 => ConfigurePlan::action(8),
            8 => continue,
            9 => ConfigurePlan::action(9),
            10 => {
                state.created = u8::from(observation != 0);
                if state.created != 0 {
                    ConfigurePlan::action(10)
                } else {
                    continue;
                }
            }
            11 => ConfigurePlan::action(11),
            12 => {
                state.stage = if observation != 0 && state.created == 0 {
                    13
                } else {
                    99
                };
                ConfigurePlan::action(if observation == 0 {
                    0
                } else if state.created != 0 {
                    12
                } else {
                    13
                })
            }
            13 => {
                state.stage = 99;
                ConfigurePlan::action(14)
            }
            _ => {
                state.stage = 99;
                ConfigurePlan::action(0)
            }
        };
    }
}
