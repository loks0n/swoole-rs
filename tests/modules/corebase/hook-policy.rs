// SPDX-License-Identifier: Apache-2.0
// Stateless policy only; the native caller owns list storage and callbacks.
#[path = "../../../crates/corebase/src/hook.rs"]
mod hook;

#[test]
fn absent_list_is_created_before_native_callback_insertion() {
    assert_eq!(hook::swr_v1_corebase_hook_add_action(0, 0), 1);
    assert_eq!(hook::swr_v1_corebase_hook_add_action(0, 1), 2);
}

#[test]
fn existing_list_selects_native_front_or_back_insertion() {
    assert_eq!(hook::swr_v1_corebase_hook_add_action(1, 0), 3);
    assert_eq!(hook::swr_v1_corebase_hook_add_action(1, 1), 4);
    assert_eq!(hook::swr_v1_corebase_hook_add_action(1, -1), 4);
}
