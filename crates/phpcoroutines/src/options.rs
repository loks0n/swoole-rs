//! Ordered coroutine-option lookup, alias precedence and application policy.
use std::ffi::c_char;

#[repr(C)]
#[derive(Default)]
pub(crate) struct OptionState {
    pub index: u32,
    pub stage: u32,
}
#[repr(C)]
pub(crate) struct OptionPlan {
    pub action: u32,
    pub key: *const c_char,
    pub key_length: usize,
    pub value: i64,
}
struct OptionEntry {
    key: &'static [u8],
    action: u32,
    skip_alias: bool,
}
const OPTIONS: [OptionEntry; 8] = [
    OptionEntry {
        key: b"max_coro_num\0",
        action: 2,
        skip_alias: true,
    },
    OptionEntry {
        key: b"max_coroutine\0",
        action: 2,
        skip_alias: false,
    },
    OptionEntry {
        key: b"enable_deadlock_check\0",
        action: 4,
        skip_alias: false,
    },
    OptionEntry {
        key: b"hook_flags\0",
        action: 5,
        skip_alias: false,
    },
    OptionEntry {
        key: b"enable_preemptive_scheduler\0",
        action: 6,
        skip_alias: false,
    },
    OptionEntry {
        key: b"c_stack_size\0",
        action: 7,
        skip_alias: true,
    },
    OptionEntry {
        key: b"stack_size\0",
        action: 7,
        skip_alias: false,
    },
    OptionEntry {
        key: b"name_resolver\0",
        action: 8,
        skip_alias: false,
    },
];
impl OptionPlan {
    fn action(action: u32) -> Self {
        Self {
            action,
            key: std::ptr::null(),
            key_length: 0,
            value: 0,
        }
    }
}
/// Each step returns before a native lookup/conversion/setter/callback effect.
/// `observation` belongs only to the previously requested effect.
/// # Safety
/// `state` is exclusive writable native-owned POD, initially zeroed, preserved
/// across steps. No Zend pointer is ever passed to or retained by Rust.
#[unsafe(no_mangle)]
pub(crate) unsafe extern "C" fn swr_v1_phpcoroutines_options(
    state: *mut OptionState,
    observation: i64,
    default_max: i64,
) -> OptionPlan {
    // SAFETY: per this function's `# Safety` contract, `state` is live, aligned and exclusive.
    let state = unsafe { &mut *state };
    loop {
        match state.stage {
            0 => {
                if let Some(option) = OPTIONS.get(state.index as usize) {
                    state.stage = 1;
                    return OptionPlan {
                        action: 1,
                        key: option.key.as_ptr().cast(),
                        key_length: option.key.len() - 1,
                        value: 0,
                    };
                }
                state.stage = 4;
                return OptionPlan::action(11);
            }
            1 => {
                let option = &OPTIONS[state.index as usize];
                state.index += 1;
                state.stage = 0;
                if observation == 0 {
                    continue;
                }
                if option.skip_alias {
                    state.index += 1;
                }
                state.stage = match option.action {
                    2 => 2,
                    8 => 3,
                    _ => 0,
                };
                return OptionPlan::action(option.action);
            }
            2 => {
                state.stage = 0;
                let mut plan = OptionPlan::action(3);
                plan.value = if observation <= 0 {
                    default_max
                } else {
                    observation
                };
                return plan;
            }
            3 => {
                state.stage = 0;
                return OptionPlan::action(if observation != 0 { 9 } else { 10 });
            }
            4 => {
                state.stage = 5;
                return OptionPlan::action(if observation != 0 { 12 } else { 13 });
            }
            _ => return OptionPlan::action(0),
        }
    }
}
