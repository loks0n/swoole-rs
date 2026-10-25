// SPDX-License-Identifier: Apache-2.0
// Pure Rust policy witnesses, not native-effect or initialization parity proof.
#[path = "../../../crates/corebase/src/lifecycle.rs"]
mod lifecycle;
use lifecycle::{LifecycleState, swr_v1_corebase_init_next};

fn trace(
    initialized: bool,
    logger: bool,
    limit: Option<u32>,
    first_cpu_below_one: bool,
) -> (Vec<u32>, u32) {
    let mut state = LifecycleState::default();
    let mut observed = 0;
    let mut actions = Vec::new();
    for _ in 0..32 {
        let action = unsafe { swr_v1_corebase_init_next(&mut state, observed, 1_048_576) };
        actions.push(action);
        match action {
            0 => {
                // C repr has two u32 fields; the native effect reads index too.
                let index = unsafe {
                    (&state as *const LifecycleState as *const u32)
                        .add(1)
                        .read()
                };
                return (actions, index);
            }
            34 => observed = initialized as u64,
            57 => observed = first_cpu_below_one as u64,
            14 => observed = logger as u64,
            41 => observed = limit.map_or(0, |value| (u64::from(value) << 1) | 1),
            u32::MAX => panic!("valid init cursor rejected"),
            _ => {}
        }
    }
    panic!("init policy failed to terminate")
}

#[test]
fn initialized_guard_runs_no_native_effect() {
    assert_eq!(trace(true, false, None, false), (vec![34, 0], 0));
}

#[test]
fn original_order_and_final_limit_have_no_default_lower_clamp() {
    for limit in [0, 1, 1023, 1024, 1_048_576, 1_048_577, u32::MAX] {
        let (actions, result) = trace(false, false, Some(limit), false);
        assert_eq!(
            actions,
            vec![34, 35, 57, 59, 36, 14, 37, 38, 39, 26, 40, 41, 43, 44, 45, 46, 0]
        );
        assert_eq!(result, limit.min(1_048_576));
    }
}

#[test]
fn failed_rlimit_warns_then_continues_without_limit_publication() {
    assert_eq!(
        trace(false, false, None, true).0,
        vec![34, 35, 57, 58, 36, 14, 37, 38, 39, 26, 40, 41, 42, 44, 45, 46, 0]
    );
}

#[test]
fn logger_is_observed_after_host_defaults_and_existing_owner_not_replaced() {
    assert_eq!(
        trace(false, true, Some(7), false).0,
        vec![34, 35, 57, 59, 36, 14, 38, 39, 26, 40, 41, 43, 44, 45, 46, 0]
    );
}
