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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn absent_list_is_created_before_native_callback_insertion() {
        assert_eq!(swr_v1_corebase_hook_add_action(0, 0), CREATE_LIST_FRONT);
        assert_eq!(swr_v1_corebase_hook_add_action(0, 1), CREATE_LIST_BACK);
    }

    #[test]
    fn existing_list_selects_native_front_or_back_insertion() {
        assert_eq!(swr_v1_corebase_hook_add_action(1, 0), PUSH_FRONT);
        assert_eq!(swr_v1_corebase_hook_add_action(1, 1), PUSH_BACK);
        assert_eq!(swr_v1_corebase_hook_add_action(1, -1), PUSH_BACK);
    }
}
