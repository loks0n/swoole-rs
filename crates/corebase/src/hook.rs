// SPDX-License-Identifier: Apache-2.0
//! Hook-list insertion policy. The caller owns the live C++ list and callbacks.

const CREATE_LIST_FRONT: u32 = 1;
const CREATE_LIST_BACK: u32 = 2;
const PUSH_FRONT: u32 = 3;
const PUSH_BACK: u32 = 4;

/// Choose the next native hook-list effect without retaining the list or callback.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_corebase_hook_add_action(list_present: u8, push_back: i32) -> u32 {
    if list_present == 0 {
        if push_back != 0 {
            CREATE_LIST_BACK
        } else {
            CREATE_LIST_FRONT
        }
    } else if push_back != 0 {
        PUSH_BACK
    } else {
        PUSH_FRONT
    }
}
