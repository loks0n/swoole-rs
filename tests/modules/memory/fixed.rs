use super::*;
#[test]
fn fixed_pool_preserves_lifo_reuse_at_aligned_and_odd_table_widths() {
    for width in [1u32, 7, 8, 31, 256] {
        let stride = mem::size_of::<Slice>() + width as usize;
        let mut memory = vec![0u64; (stride * 17).div_ceil(8)];
        let base = memory.as_mut_ptr().cast::<u8>();
        let mut p = Fixed {
            memory: base,
            size: stride * 17,
            head: ptr::null_mut(),
            tail: ptr::null_mut(),
            slice_num: 17,
            slice_use: 0,
            slice_size: width,
            shared: 1,
            allocated: 0,
        };
        unsafe {
            assert_eq!(swr_v1_memory_fixed_init(&mut p), 0);
            let mut entries = Vec::new();
            for index in (0..17).rev() {
                let data = swr_v1_memory_fixed_alloc(&mut p);
                assert_eq!(
                    data.cast::<u8>(),
                    base.add(index * stride + mem::size_of::<Slice>())
                );
                ptr::write_bytes(data, index as u8, width as usize);
                entries.push(data);
            }
            assert!(swr_v1_memory_fixed_alloc(&mut p).is_null());
            assert_eq!(p.slice_use, 17);
            for &i in &[3, 10, 0] {
                assert_eq!(swr_v1_memory_fixed_free(&mut p, entries[i]), 0);
            }
            assert_eq!(swr_v1_memory_fixed_free(&mut p, entries[0]), -1);
            assert_eq!(
                swr_v1_memory_fixed_free(&mut p, entries[0].cast::<u8>().add(1).cast()),
                -1
            );
            for &i in &[0, 10, 3] {
                assert_eq!(swr_v1_memory_fixed_alloc(&mut p), entries[i]);
            }
            assert_eq!(p.slice_use, 17);
        }
    }
}

#[test]
fn fixed_construction_plans_own_alignment_and_borrowed_floor_counts() {
    for width in [0u32, 1, 7, 8, 31, 256] {
        let mut plan = Layout::default();
        unsafe {
            assert_eq!(swr_v1_memory_fixed_layout(17, width, 0, 1, &mut plan), 0);
        }
        let aligned = (width + 7) & !7;
        assert_eq!(plan.width, aligned);
        assert_eq!(plan.slices, 17);
        assert_eq!(plan.usable, 17 * (24 + aligned as usize));
        assert_eq!(plan.total, 48 + plan.usable);
        let borrowed = 48 + 17 * (24 + width as usize) + 3;
        unsafe {
            assert_eq!(
                swr_v1_memory_fixed_layout(0, width, borrowed, 0, &mut plan),
                0
            );
        }
        assert_eq!(
            (plan.total, plan.usable, plan.slices, plan.width),
            (borrowed, borrowed - 48, 17, width)
        );
    }
    // Scalar invalid/overflow plans are rejected without requesting an arena.
    for (count, width, available, owned) in [
        (0, 8, 0, 1),
        (1, 8, 0, 1),
        (2, u32::MAX, 0, 1),
        (2, 8, 1, 1),
        (0, 8, 0, 0),
        (0, 8, usize::MAX, 0),
        (2, 8, 0, 2),
        (1, 8, 128, 0),
    ] {
        let mut plan = Layout {
            total: 1,
            usable: 1,
            slices: 1,
            width: 1,
        };
        unsafe {
            assert_eq!(
                swr_v1_memory_fixed_layout(count, width, available, owned, &mut plan),
                -1
            );
        }
        assert_eq!(plan, Layout::default());
    }
}

#[test]
fn fixed_constructs_complete_real_header_and_links_without_touching_payload_or_tail() {
    for owned in [0u32, 1] {
        for shared in [0u32, 1] {
            for width in [0u32, 1, 7, 8, 31, 256] {
                let mut plan = Layout::default();
                let available = if owned == 0 {
                    48 + 17 * (24 + width as usize) + 3
                } else {
                    0
                };
                unsafe {
                    assert_eq!(
                        swr_v1_memory_fixed_layout(
                            if owned == 1 { 17 } else { 0 },
                            width,
                            available,
                            owned,
                            &mut plan
                        ),
                        0
                    );
                }
                let mut memory = vec![0xa5a5_a5a5_a5a5_a5a5u64; plan.total.div_ceil(8) + 1];
                let arena = memory.as_mut_ptr().cast::<Fixed>();
                unsafe {
                    assert_eq!(
                        swr_v1_memory_fixed_construct(arena, &plan, shared, owned),
                        0
                    );
                    let pool = &*arena;
                    assert_eq!(pool.memory, arena.cast::<u8>().add(48));
                    assert_eq!(
                        (
                            pool.size,
                            pool.slice_num,
                            pool.slice_use,
                            pool.slice_size,
                            pool.shared,
                            pool.allocated
                        ),
                        (plan.usable, 17, 0, plan.width, shared as u8, owned as u8)
                    );
                    let stride = 24 + plan.width as usize;
                    for index in (0..17).rev() {
                        let data = swr_v1_memory_fixed_alloc(arena).cast::<u8>();
                        assert_eq!(data, arena.cast::<u8>().add(48 + index * stride + 24));
                        assert!(
                            std::slice::from_raw_parts(data, plan.width as usize)
                                .iter()
                                .all(|&b| b == 0xa5)
                        );
                        assert_eq!(swr_v1_memory_fixed_free(arena, data.cast()), 0);
                        // Reuse consumes the same node; leave it live before the next allocation.
                        assert_eq!(swr_v1_memory_fixed_alloc(arena), data.cast());
                    }
                    assert!(swr_v1_memory_fixed_alloc(arena).is_null());
                    let end = 48 + 17 * stride;
                    assert!(
                        std::slice::from_raw_parts(
                            arena.cast::<u8>().add(end),
                            memory.len() * 8 - end
                        )
                        .iter()
                        .all(|&b| b == 0xa5)
                    );
                }
            }
        }
    }
}

#[test]
fn fixed_construction_rejects_inconsistent_plan_before_publication() {
    let mut plan = Layout::default();
    unsafe {
        assert_eq!(swr_v1_memory_fixed_layout(2, 8, 0, 1, &mut plan), 0);
    }
    let mut memory = [0xa5a5_a5a5_a5a5_a5a5u64; 32];
    let before = memory;
    plan.usable += 1;
    unsafe {
        assert_eq!(
            swr_v1_memory_fixed_construct(memory.as_mut_ptr().cast(), &plan, 1, 1),
            -1
        );
    }
    assert_eq!(memory, before);
}

#[test]
fn ownership_actions_preserve_owned_borrowed_heap_shared_order() {
    for shared in 0..=1 {
        for owned in 0..=1 {
            for phase in 0..=1 {
                assert_eq!(
                    swr_v1_memory_arena_lifecycle(shared, owned, phase),
                    if owned == 0 {
                        0
                    } else {
                        (1 + shared + 2 * phase) as i32
                    }
                );
            }
        }
    }
    for (shared, owned, phase) in [(2, 1, 0), (0, 2, 0), (0, 1, 2)] {
        assert_eq!(swr_v1_memory_arena_lifecycle(shared, owned, phase), -1);
    }
}

#[test]
fn diagnostic_cursor_matches_live_odd_links_and_original_postprint_limit() {
    unsafe {
        assert_eq!(mem::size_of::<DebugCursor>(), 16);
        assert_eq!(mem::size_of::<DebugRecord>(), 48);
        for width in [1u32, 8, 31] {
            let mut plan = Layout::default();
            let total = mem::size_of::<Fixed>() + 5 * (mem::size_of::<Slice>() + width as usize);
            assert_eq!(swr_v1_memory_fixed_layout(0, width, total, 0, &mut plan), 0);
            let mut arena = vec![0u64; total.div_ceil(8)];
            let pool = arena.as_mut_ptr().cast::<Fixed>();
            assert_eq!(swr_v1_memory_fixed_construct(pool, &plan, 0, 0), 0);
            let allocated = swr_v1_memory_fixed_alloc(pool);
            assert!(!allocated.is_null());
            for (max, expected) in [(-2, 1), (-1, 1), (0, 2), (1, 3), (3, 5), (99, 5)] {
                let mut cursor = DebugCursor::default();
                let mut record = DebugRecord::default();
                let mut next = (*pool).head;
                for line in 0..expected {
                    let actual = next.read_unaligned();
                    assert_eq!(
                        swr_v1_memory_fixed_debug_step(pool, &mut cursor, max, &mut record),
                        1
                    );
                    assert_eq!(
                        (
                            record.slice,
                            record.prev,
                            record.next,
                            record.line,
                            record.lock
                        ),
                        (next, actual.prev, actual.next, line, actual.lock)
                    );
                    assert_eq!(record.data, next.cast::<u8>().add(mem::size_of::<Slice>()));
                    assert_eq!(record.self_link, 0);
                    next = actual.next;
                }
                assert_eq!(
                    swr_v1_memory_fixed_debug_step(pool, &mut cursor, max, &mut record),
                    0
                );
                assert!(record.slice.is_null());
            }
            // The original diagnostic explicitly marks self-links and bounds them.
            let head = (*pool).head;
            let original = head.read_unaligned();
            head.write_unaligned(Slice {
                next: head,
                ..original
            });
            let mut cursor = DebugCursor::default();
            let mut record = DebugRecord::default();
            for line in 0..2 {
                assert_eq!(
                    swr_v1_memory_fixed_debug_step(pool, &mut cursor, 0, &mut record),
                    1
                );
                assert_eq!(
                    (record.line, record.self_link, record.slice),
                    (line, 1, head)
                );
            }
            assert_eq!(
                swr_v1_memory_fixed_debug_step(pool, &mut cursor, 0, &mut record),
                0
            );
            head.write_unaligned(original);
        }
    }
}

#[test]
fn usage_snapshot_preserves_public_scalar_queries_and_unsigned_wrap() {
    unsafe {
        assert_eq!(mem::size_of::<Usage>(), 12);
        let mut pool = Fixed {
            memory: ptr::null_mut(),
            size: 0,
            head: ptr::null_mut(),
            tail: ptr::null_mut(),
            slice_num: 0,
            slice_use: 0,
            slice_size: 0,
            shared: 0,
            allocated: 0,
        };
        let mut usage = Usage::default();
        for total in [0u32, 5, u32::MAX] {
            for used in [0u32, 3, u32::MAX] {
                pool.slice_num = total;
                pool.slice_use = used;
                pool.slice_size = 31;
                assert_eq!(swr_v1_memory_fixed_usage(&pool, &mut usage), 0);
                assert_eq!(
                    (usage.spare, usage.total, usage.width),
                    (total.wrapping_sub(used), total, 31)
                );
            }
        }
        assert_eq!(swr_v1_memory_fixed_usage(ptr::null(), &mut usage), -1);
        assert_eq!((usage.spare, usage.total, usage.width), (0, 0, 0));
    }
}

#[test]
fn normal_queue_changes_publish_only_mutable_header_fields() {
    unsafe {
        for count in [2, 3, 8, 17] {
            let mut layout = Layout::default();
            assert_eq!(swr_v1_memory_fixed_layout(count, 16, 0, 1, &mut layout), 0);
            let mut arena = vec![0u64; layout.total.div_ceil(8)];
            let pool = arena.as_mut_ptr().cast::<Fixed>();
            assert_eq!(swr_v1_memory_fixed_construct(pool, &layout, 0, 1), 0);
            let original = pool.read();
            let mut live = Vec::new();
            for _ in 0..count {
                let value = swr_v1_memory_fixed_alloc(pool);
                assert!(!value.is_null());
                live.push(value);
                let current = pool.read();
                assert_eq!(
                    (
                        current.memory,
                        current.size,
                        current.slice_num,
                        current.slice_size,
                        current.shared,
                        current.allocated
                    ),
                    (original.memory, original.size, count, 16, 0, 1)
                );
                assert_eq!(current.slice_use, live.len() as u32);
            }
            for (index, value) in live.iter().enumerate() {
                assert_eq!(swr_v1_memory_fixed_free(pool, *value), 0);
                let current = pool.read();
                assert_eq!(
                    (
                        current.memory,
                        current.size,
                        current.slice_num,
                        current.slice_size,
                        current.shared,
                        current.allocated
                    ),
                    (original.memory, original.size, count, 16, 0, 1)
                );
                assert_eq!(current.slice_use, count - index as u32 - 1);
            }
        }
    }
}

/// Source-backed initialization regression. Only the repaired implementation is
/// executed: every observed byte has been explicitly initialized before reading.
#[test]
fn initialized_fixed_headers_keep_native_zero_padding_through_normal_operations() {
    for width in [1, 7, 8, 17] {
        for owned in [0, 1] {
            let layout = Layout::new(
                if owned == 1 { 3 } else { 0 },
                width,
                if owned == 0 {
                    48 + 3 * (24 + width as usize)
                } else {
                    0
                },
                owned,
            )
            .unwrap();
            let mut storage = vec![0xa5a5_a5a5_a5a5_a5a5u64; layout.total.div_ceil(8) + 2];
            let pool = storage.as_mut_ptr().cast::<Fixed>();
            unsafe {
                assert_eq!(swr_v1_memory_fixed_construct(pool, &layout, 0, owned), 0);
                let verify = || {
                    let base = pool.cast::<u8>();
                    for i in mem::offset_of!(Fixed, allocated) + 1..mem::size_of::<Fixed>() {
                        assert_eq!(base.add(i).read(), 0);
                    }
                    for i in 0..3 {
                        let header = base.add(
                            mem::size_of::<Fixed>()
                                + i * (mem::size_of::<Slice>() + layout.width as usize),
                        );
                        for j in mem::size_of::<u8>()..mem::offset_of!(Slice, next) {
                            assert_eq!(header.add(j).read(), 0);
                        }
                    }
                    let end = storage.as_ptr().cast::<u8>();
                    for i in layout.total..storage.len() * 8 {
                        assert_eq!(end.add(i).read(), 0xa5);
                    }
                };
                verify();
                let first = swr_v1_memory_fixed_alloc(pool);
                let second = swr_v1_memory_fixed_alloc(pool);
                assert!(!first.is_null() && !second.is_null());
                verify();
                assert_eq!(swr_v1_memory_fixed_free(pool, second), 0);
                assert_eq!(swr_v1_memory_fixed_free(pool, first), 0);
                verify();
            }
        }
    }
}
