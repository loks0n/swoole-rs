// SPDX-License-Identifier: Apache-2.0
// Copied-fact policy checks only; real native filesystem/publication parity is separate.
#[path = "../../../crates/corebase/src/lifecycle.rs"]
mod lifecycle;
use lifecycle::{LifecycleState, swr_v1_corebase_task_tmp_next};

fn trace(first: u8, accessible: bool, created: bool, published: u64) -> Vec<u32> {
    let mut cursor = LifecycleState::default();
    let mut observed = 0;
    let mut actions = Vec::new();
    for _ in 0..12 {
        let action = unsafe { swr_v1_corebase_task_tmp_next(&mut cursor, observed, 256) };
        actions.push(action);
        observed = match action {
            47 => u64::from(first),
            49 => u64::from(accessible),
            50 => u64::from(created),
            53 => published,
            55 | 56 => return actions,
            _ => 0,
        };
    }
    panic!("policy did not terminate");
}

#[test]
fn relative_path_rejection_precedes_access_and_publication() {
    assert_eq!(trace(b'a', true, true, 0), [47, 48, 55]);
}
#[test]
fn access_success_bypasses_mkdir_and_observes_after_publication() {
    assert_eq!(trace(b'/', true, false, 255), [47, 49, 52, 53, 56]);
}
#[test]
fn failed_access_requires_successful_mkdir_before_publication() {
    assert_eq!(trace(b'/', false, true, 255), [47, 49, 50, 52, 53, 56]);
    assert_eq!(trace(b'/', false, false, 255), [47, 49, 50, 51, 55]);
}
#[test]
fn length_limit_rejects_only_after_native_publication() {
    assert_eq!(trace(b'/', true, false, 256), [47, 49, 52, 53, 54, 55]);
    assert_eq!(trace(b'/', true, false, u64::MAX), [47, 49, 52, 53, 54, 55]);
}
