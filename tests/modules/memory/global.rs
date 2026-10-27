use super::*;
#[test]
fn bump_pages_match_alignment_zeroing_capacity_and_custody_rules() {
    unsafe {
        let mut state = ptr::null_mut();
        assert_eq!(swr_v1_memory_global_create(64, &raw mut state), 0);
        let mut output = ptr::dangling_mut();
        assert_eq!(swr_v1_memory_global_alloc(state, 1, &raw mut output), 1);
        assert!(output.is_null());
        let mut page = [u64::MAX; 8];
        let page_ptr = page.as_mut_ptr().cast::<c_void>();
        assert_eq!(swr_v1_memory_global_add_page(state, page_ptr), 0);
        assert_eq!(swr_v1_memory_global_release(state), -1);
        for i in 0..4 {
            assert_eq!(swr_v1_memory_global_alloc(state, 1, &raw mut output), 0);
            assert_eq!(output.cast::<u8>(), page_ptr.cast::<u8>().add(i * 16 + 8));
            assert_eq!(output.cast::<u64>().read(), 0);
            output.cast::<u64>().write(42);
            assert_eq!(swr_v1_memory_global_capacity(state), 64 - (i + 1) * 16);
        }
        assert_eq!(swr_v1_memory_global_alloc(state, 1, &raw mut output), 1);
        assert!(output.is_null());
        assert_eq!(
            swr_v1_memory_global_alloc(state, u32::MAX, &raw mut output),
            -1
        );
        assert!(output.is_null());
        assert_eq!(swr_v1_memory_global_memory_size(state), 64);
        assert_eq!(swr_v1_memory_global_pop_page(state), page_ptr);
        assert!(swr_v1_memory_global_pop_page(state).is_null());
        assert_eq!(swr_v1_memory_global_release(state), 0);
    }
}

#[test]
fn native_page_size_and_forward_teardown_order_are_preserved() {
    unsafe {
        let mut page_size = 0;
        assert_eq!(
            swr_v1_memory_global_page_size(4096, 16384, &raw mut page_size),
            0
        );
        assert_eq!(page_size, 16384);
        assert_eq!(
            swr_v1_memory_global_page_size(u32::MAX, 16384, &raw mut page_size),
            -1
        );
        assert_eq!(page_size, 0);
        let mut state = ptr::null_mut();
        assert_eq!(swr_v1_memory_global_create(64, &raw mut state), 0);
        let mut pages = [[0u64; 8]; 2];
        let first = pages[0].as_mut_ptr().cast::<c_void>();
        let second = pages[1].as_mut_ptr().cast::<c_void>();
        assert_eq!(swr_v1_memory_global_add_page(state, first), 0);
        assert_eq!(swr_v1_memory_global_add_page(state, second), 0);
        assert_eq!(swr_v1_memory_global_pop_page(state), first);
        let mut out = ptr::dangling_mut();
        assert_eq!(swr_v1_memory_global_alloc(state, 1, &raw mut out), -1);
        assert!(out.is_null());
        assert_eq!(swr_v1_memory_global_release(state), -1);
        assert_eq!(swr_v1_memory_global_pop_page(state), second);
        assert!(swr_v1_memory_global_pop_page(state).is_null());
        assert_eq!(swr_v1_memory_global_release(state), 0);
    }
}

#[test]
fn owned_lifecycle_selects_effects_and_preserves_inherited_pages() {
    unsafe {
        assert_eq!(std::mem::size_of::<GlobalEffect>(), 24);
        for shared in 0..=1 {
            let mut state = ptr::null_mut();
            assert_eq!(
                swr_v1_memory_global_open(4097, 4096, shared, 41, &raw mut state),
                0
            );
            let mut effect = GlobalEffect::default();
            assert_eq!(
                swr_v1_memory_global_step(state, 0, 0, 0, &raw mut effect),
                0
            );
            assert_eq!((effect.page_size, effect.action), (8192, 1 + shared));
            let mut pages = [vec![u64::MAX; 1024], vec![u64::MAX; 1024]];
            let first = pages[0].as_mut_ptr().cast();
            let second = pages[1].as_mut_ptr().cast();
            assert_eq!(swr_v1_memory_global_add_page(state, first), 0);
            let mut output = ptr::null_mut();
            assert_eq!(swr_v1_memory_global_alloc(state, 9, &raw mut output), 0);
            output.cast::<u64>().write(0x1234);
            for current in [41, 42] {
                assert_eq!(
                    swr_v1_memory_global_step(state, 1, current, 9, &raw mut effect),
                    0
                );
                assert_eq!(effect.aligned, 16);
                assert_eq!(
                    effect.action,
                    if shared == 1 && current != 41 { 5 } else { 0 }
                );
                assert_eq!(swr_v1_memory_global_capacity(state), 8192 - 24);
                assert_eq!(output.cast::<u64>().read(), 0x1234);
            }
            // Validation precedes reset and does not detach any inherited page.
            assert_eq!(
                swr_v1_memory_global_step(state, 1, 42, 8192, &raw mut effect),
                -1
            );
            assert_eq!((effect.aligned, effect.action), (8192, 0));
            assert_eq!(swr_v1_memory_global_memory_size(state), 8192);
            assert_eq!(swr_v1_memory_global_add_page(state, second), 0);
            for page in [first, second] {
                assert_eq!(
                    swr_v1_memory_global_step(state, 2, 0, 0, &raw mut effect),
                    0
                );
                assert_eq!(effect.page, page);
                assert_eq!(effect.action, 3 + shared);
            }
            assert_eq!(
                swr_v1_memory_global_step(state, 2, 0, 0, &raw mut effect),
                0
            );
            assert_eq!(effect.action, 0);
            assert!(effect.page.is_null());
            assert_eq!(
                swr_v1_memory_global_step(state, 0, 0, 0, &raw mut effect),
                -1
            );
            assert_eq!(swr_v1_memory_global_release(state), 0);
        }
    }
}

#[test]
fn lifecycle_rejects_invalid_configuration_and_clears_effects() {
    unsafe {
        for (requested, page, shared) in [
            (4095, 4096, 0),
            (4096, 3, 0),
            (4096, 4096, 2),
            (u32::MAX, 4096, 1),
        ] {
            let mut state = ptr::dangling_mut();
            assert_eq!(
                swr_v1_memory_global_open(requested, page, shared, 1, &raw mut state),
                -2
            );
            assert!(state.is_null());
        }
        let mut effect = GlobalEffect {
            page: ptr::dangling_mut(),
            action: 5,
            ..GlobalEffect::default()
        };
        assert_eq!(
            swr_v1_memory_global_step(ptr::null_mut(), 0, 0, 0, &raw mut effect),
            -1
        );
        assert_eq!(effect.action, 0);
        assert!(effect.page.is_null());
        let mut state = ptr::null_mut();
        assert_eq!(swr_v1_memory_global_create(64, &raw mut state), 0);
        assert_eq!(
            swr_v1_memory_global_step(state, 99, 0, 0, &raw mut effect),
            -1
        );
        assert_eq!(swr_v1_memory_global_release(state), 0);
    }
}

#[test]
fn empty_drain_closes_registration_in_both_existing_apis() {
    unsafe {
        for effects in [false, true] {
            let mut state = ptr::null_mut();
            assert_eq!(swr_v1_memory_global_create(64, &raw mut state), 0);
            if effects {
                let mut effect = GlobalEffect::default();
                assert_eq!(
                    swr_v1_memory_global_step(state, 2, 0, 0, &raw mut effect),
                    0
                );
                assert_eq!(effect.action, 0);
                assert!(effect.page.is_null());
            } else {
                assert!(swr_v1_memory_global_pop_page(state).is_null());
            }
            // Live empty owner is in drain mode, before release; no stale token
            // or allocation failure is involved in these lifecycle refusals.
            let mut page = [0u64; 8];
            assert_eq!(
                swr_v1_memory_global_add_page(state, page.as_mut_ptr().cast()),
                -1
            );
            let mut result = ptr::null_mut();
            assert_eq!(swr_v1_memory_global_alloc(state, 8, &raw mut result), -1);
            assert!(result.is_null());
            assert_eq!(swr_v1_memory_global_memory_size(state), 0);
            assert_eq!(swr_v1_memory_global_release(state), 0);
        }
    }
}
