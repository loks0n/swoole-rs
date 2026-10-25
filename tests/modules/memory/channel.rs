use super::*;
use std::collections::VecDeque;
#[test]
fn channel_fifo_spill_wrap_peek_and_capacity_match_independent_model() {
    let mut memory = [0u8; 128 + 24 + 4];
    let mut c = Channel {
        head: 0,
        tail: 0,
        size: 128,
        head_tag: 0,
        tail_tag: 0,
        num: 0,
        max_num: 0,
        bytes: 0,
        flags: 0,
        maxlen: 24,
        mem: memory.as_mut_ptr(),
    };
    let mut model = VecDeque::<Vec<u8>>::new();
    let mut seed = 42u64;
    for _ in 0..20000 {
        seed ^= seed << 13;
        seed ^= seed >> 7;
        seed ^= seed << 17;
        if seed & 3 != 0 {
            let bytes = vec![seed as u8; (seed % 25) as usize];
            if unsafe {
                swr_v1_memory_channel_in(&mut c, bytes.as_ptr().cast(), bytes.len() as i32)
            } == 0
            {
                model.push_back(bytes);
            }
        } else {
            let mut output = [0u8; 24];
            let consume = ((seed >> 2) & 1) as u32;
            let capacity = if seed & 32 != 0 { 24 } else { 0 };
            let status = unsafe {
                swr_v1_memory_channel_out(&mut c, output.as_mut_ptr().cast(), capacity, consume)
            };
            if let Some(front) = model.front() {
                if front.len() <= capacity as usize {
                    assert_eq!(status, front.len() as i32);
                    assert_eq!(&output[..front.len()], front);
                    if consume != 0 {
                        model.pop_front();
                    }
                } else {
                    assert_eq!(status, -1);
                }
            } else {
                assert_eq!(status, -1);
            }
        }
        assert_eq!(c.num as usize, model.len());
        assert_eq!(c.bytes, model.iter().map(Vec::len).sum());
    }
}

#[test]
fn invalid_wrap_tags_reject_push_peek_and_pop_without_writes() {
    fn state(c: &Channel) -> (i64, i64, u8, u8, i32, usize) {
        (c.head, c.tail, c.head_tag, c.tail_tag, c.num, c.bytes)
    }
    for head_tag in [0, 1, 2, u8::MAX] {
        for tail_tag in [0, 1, 2, u8::MAX] {
            if head_tag <= 1 && tail_tag <= 1 {
                continue;
            }
            let mut memory = [0xabu8; 16];
            let mut c = Channel {
                head: 0,
                tail: 7,
                size: 8,
                head_tag,
                tail_tag,
                num: 0,
                max_num: 0,
                bytes: 0,
                flags: 0,
                maxlen: 4,
                mem: memory.as_mut_ptr(),
            };
            let before = state(&c);
            let byte = 42u8;
            assert_eq!(
                unsafe { swr_v1_memory_channel_in(&mut c, ptr::from_ref(&byte).cast(), 1) },
                -1
            );
            assert_eq!(state(&c), before);
            assert_eq!(memory, [0xab; 16]);

            // An otherwise readable record crosses the logical end, exercising
            // both the peek path and the consuming head-tag wrap path.
            c.head = 7;
            c.tail = 0;
            c.num = 1;
            c.bytes = 1;
            memory[7..11].copy_from_slice(&1i32.to_ne_bytes());
            memory[11] = byte;
            let before_memory = memory;
            let before = state(&c);
            for consume in [0, 1] {
                let mut output = [0xcdu8; 4];
                assert_eq!(
                    unsafe {
                        swr_v1_memory_channel_out(&mut c, output.as_mut_ptr().cast(), 4, consume)
                    },
                    -1
                );
                assert_eq!(state(&c), before);
                assert_eq!(memory, before_memory);
                assert_eq!(output, [0xcd; 4]);
            }
        }
    }
}

#[test]
fn invalid_configuration_is_rejected_before_accessing_queue_storage() {
    for case in 0..12 {
        let mut memory = [0xabu8; 16];
        // Valid for both push and output before corrupting one boundary.
        memory[..4].copy_from_slice(&1i32.to_ne_bytes());
        let mut c = Channel {
            head: 0,
            tail: 5,
            size: 8,
            head_tag: 0,
            tail_tag: 0,
            num: 1,
            max_num: 0,
            bytes: 1,
            flags: 0,
            maxlen: 4,
            mem: memory.as_mut_ptr(),
        };
        match case {
            0 => c.mem = ptr::null_mut(),
            1 => c.size = 0,
            2 => c.size = usize::MAX,
            3 => c.size = isize::MAX as usize,
            4 => c.head = -1,
            5 => c.tail = -1,
            6 => c.head = 8,
            7 => c.tail = 8,
            8 => c.num = -1,
            9 => c.maxlen = -1,
            10 => c.maxlen = 9,
            11 => c.head = i64::MIN,
            _ => unreachable!(),
        }
        let before_memory = memory;
        let before = (c.head, c.tail, c.head_tag, c.tail_tag, c.num, c.bytes);
        let input = 42u8;
        assert_eq!(
            unsafe { swr_v1_memory_channel_in(&mut c, ptr::from_ref(&input).cast(), 1) },
            -1,
            "push boundary {case}"
        );
        for consume in [0, 1] {
            let mut output = [0xcdu8; 4];
            assert_eq!(
                unsafe {
                    swr_v1_memory_channel_out(&mut c, output.as_mut_ptr().cast(), 4, consume)
                },
                -1,
                "output boundary {case}"
            );
            assert_eq!(output, [0xcd; 4]);
        }
        assert_eq!(memory, before_memory);
        assert_eq!(
            (c.head, c.tail, c.head_tag, c.tail_tag, c.num, c.bytes),
            before
        );
    }
}

#[test]
fn every_short_copy_width_and_spilled_record_preserves_exact_payload_and_boundaries() {
    for length in 0..=256usize {
        // Exact input/output allocations let ASan detect endpoint overreads,
        // including lengths just below/above each fixed-width copy threshold.
        let input: Vec<u8> = (0..length)
            .map(|i| (i.wrapping_mul(37) ^ length) as u8)
            .collect();
        for cursor in [0usize, 3, 127] {
            let mut memory = vec![0xabu8; 128 + 256 + 4];
            let mut c = Channel {
                head: cursor as i64,
                tail: cursor as i64,
                size: 128,
                head_tag: 0,
                tail_tag: 0,
                num: 0,
                max_num: 0,
                bytes: 0,
                flags: 0,
                maxlen: 128,
                mem: memory.as_mut_ptr(),
            };
            // Native channels require maxlen <= logical size; use a larger
            // logical ring for large messages while retaining the end spill.
            if length > 128 {
                c.size = 256;
                c.maxlen = 256;
                c.head += 128;
                c.tail += 128;
                memory.resize(256 + 256 + 4, 0xab);
                c.mem = memory.as_mut_ptr();
            }
            let start = c.tail as usize;
            assert_eq!(
                unsafe { swr_v1_memory_channel_in(&mut c, input.as_ptr().cast(), length as i32) },
                0
            );
            assert_eq!(&memory[..start], vec![0xab; start]);
            assert_eq!(&memory[start + 4..start + 4 + length], input);
            assert!(
                memory[start + 4 + length..]
                    .iter()
                    .all(|byte| *byte == 0xab)
            );
            let before = (c.head, c.tail, c.head_tag, c.tail_tag, c.num, c.bytes);
            for consume in [0, 1] {
                let mut output = vec![0xcdu8; length];
                assert_eq!(
                    unsafe {
                        swr_v1_memory_channel_out(
                            &mut c,
                            output.as_mut_ptr().cast(),
                            length as i32,
                            consume,
                        )
                    },
                    length as i32
                );
                assert_eq!(output, input);
                if consume == 0 {
                    assert_eq!(
                        (c.head, c.tail, c.head_tag, c.tail_tag, c.num, c.bytes),
                        before
                    );
                }
            }
            assert_eq!(c.num, 0);
            assert_eq!(c.bytes, 0);
            assert_eq!(c.head, c.tail);
            assert_eq!(c.head_tag, c.tail_tag);
        }
    }
}

fn fields(c: &mut Channel) -> Fields {
    Fields {
        head: ptr::addr_of_mut!(c.head),
        tail: ptr::addr_of_mut!(c.tail),
        size: ptr::addr_of_mut!(c.size),
        head_tag: ptr::addr_of_mut!(c.head_tag),
        tail_tag: ptr::addr_of_mut!(c.tail_tag),
        num: ptr::addr_of_mut!(c.num),
        max_num: ptr::addr_of_mut!(c.max_num),
        bytes: ptr::addr_of_mut!(c.bytes),
        flags: ptr::addr_of_mut!(c.flags),
        maxlen: ptr::addr_of_mut!(c.maxlen),
        mem: ptr::addr_of_mut!(c.mem),
    }
}
fn empty_channel() -> Channel {
    Channel {
        head: 0,
        tail: 0,
        size: 0,
        head_tag: 0,
        tail_tag: 0,
        num: 0,
        max_num: 0,
        bytes: 0,
        flags: 0,
        maxlen: 0,
        mem: ptr::null_mut(),
    }
}
#[test]
fn field_storage_matches_frozen_snapshot_and_payload_for_twenty_thousand_operations() {
    assert_eq!(std::mem::size_of::<Fields>(), 88);
    let mut plan = StoragePlan::default();
    let mut current = empty_channel();
    let fields = fields(&mut current);
    let mut memory = [0xa5; 128 + 32 + 4];
    let mut old_memory = memory;
    unsafe {
        assert_eq!(
            swr_v1_memory_channel_storage_plan(128, 32, 6, 80, &mut plan),
            0
        );
        assert_eq!(
            swr_v1_memory_channel_storage_init(&fields, &plan, memory.as_mut_ptr().cast()),
            0
        );
        let mut snapshot = fields.load();
        snapshot.mem = old_memory.as_mut_ptr();
        let mut seed = 0x1234u64;
        for _ in 0..20000 {
            seed ^= seed << 13;
            seed ^= seed >> 7;
            seed ^= seed << 17;
            if seed & 3 != 0 {
                let data = vec![seed as u8; (seed % 33) as usize];
                assert_eq!(
                    swr_v1_memory_channel_storage_in(
                        &fields,
                        data.as_ptr().cast(),
                        data.len() as i32
                    ),
                    swr_v1_memory_channel_in(
                        &mut snapshot,
                        data.as_ptr().cast(),
                        data.len() as i32
                    )
                );
            } else {
                let mut output = [0xcd; 34];
                let mut old_output = output;
                let capacity = if seed & 32 == 0 { 32 } else { 0 };
                assert_eq!(
                    swr_v1_memory_channel_storage_out(
                        &fields,
                        output.as_mut_ptr().cast(),
                        capacity
                    ),
                    swr_v1_memory_channel_out(
                        &mut snapshot,
                        old_output.as_mut_ptr().cast(),
                        capacity,
                        1
                    )
                );
                assert_eq!(output, old_output);
            }
            let c = fields.load();
            assert_eq!(
                (c.head, c.tail, c.head_tag, c.tail_tag, c.num, c.bytes),
                (
                    snapshot.head,
                    snapshot.tail,
                    snapshot.head_tag,
                    snapshot.tail_tag,
                    snapshot.num,
                    snapshot.bytes
                )
            );
            assert_eq!(memory, old_memory);
            assert_eq!((c.size, c.maxlen, c.flags, c.max_num), (128, 32, 6, 0));
        }
    }
}
#[test]
fn field_constructor_validates_plan_and_scalar_addresses_before_initialization() {
    for (size, maxlen) in [(0, 0), (1, 0), (32, 32), (128, 32)] {
        let mut plan = StoragePlan::default();
        let mut c = empty_channel();
        let fields = fields(&mut c);
        let mut memory = vec![0xab; size + maxlen + 4];
        unsafe {
            assert_eq!(
                swr_v1_memory_channel_storage_plan(size, maxlen, -1, 80, &mut plan),
                0
            );
            assert_eq!(plan.total, 80 + size + maxlen + 4);
            assert_eq!(
                swr_v1_memory_channel_storage_init(&fields, &plan, memory.as_mut_ptr().cast()),
                0
            );
        }
        assert_eq!(
            (c.size, c.maxlen, c.flags, c.num, c.bytes),
            (size, maxlen as i32, -1, 0, 0)
        );
        assert_eq!(c.mem, memory.as_mut_ptr());
        assert_eq!(memory, vec![0xab; size + maxlen + 4]);
    }
    for (size, maxlen, header) in [
        (1, 2, 80),
        (usize::MAX, 1, 80),
        (isize::MAX as usize, 0, 80),
        (128, 32, 0),
    ] {
        let mut plan = StoragePlan::default();
        assert_eq!(
            unsafe { swr_v1_memory_channel_storage_plan(size, maxlen, 0, header, &mut plan) },
            -1
        );
        assert_eq!(
            (
                plan.total,
                plan.size,
                plan.header_size,
                plan.maxlen,
                plan.flags
            ),
            (0, 0, 0, 0, 0)
        );
    }
    let mut plan = StoragePlan::default();
    let mut c = empty_channel();
    let mut fields = fields(&mut c);
    let mut memory = [0xabu8; 164];
    unsafe {
        assert_eq!(
            swr_v1_memory_channel_storage_plan(128, 32, 0, 80, &mut plan),
            0
        );
        plan.total += 1;
        assert_eq!(
            swr_v1_memory_channel_storage_init(&fields, &plan, memory.as_mut_ptr().cast()),
            -1
        );
        assert_eq!(c.size, 0);
        plan.total -= 1;
        fields.head = ptr::null_mut();
        assert_eq!(
            swr_v1_memory_channel_storage_init(&fields, &plan, memory.as_mut_ptr().cast()),
            -1
        );
        assert_eq!(
            swr_v1_memory_channel_storage_in(&fields, memory.as_ptr().cast(), 1),
            -1
        );
        assert_eq!(
            swr_v1_memory_channel_storage_out(&fields, memory.as_mut_ptr().cast(), 32),
            -1
        );
    }
    assert_eq!(c.size, 0);
    assert_eq!(memory, [0xab; 164]);
}

#[test]
fn lifecycle_plans_preserve_native_effect_selection_and_release_order() {
    assert_eq!(std::mem::size_of::<Lifecycle>(), 20);
    let cases: &[(i32, &[u32], &[u32])] = &[
        (0, &[1, 3], &[8]),
        (2, &[1, 3, 4], &[6, 8]),
        (4, &[1, 3, 5], &[7, 8]),
        (6, &[1, 3, 4, 5], &[6, 7, 8]),
        (8, &[2, 3], &[9]),
        (10, &[2, 3, 4], &[6, 9]),
        (12, &[2, 3, 5], &[7, 9]),
        (14, &[2, 3, 4, 5], &[6, 7, 9]),
    ];
    for &(flags, constructor, teardown) in cases {
        // Unrelated bits do not create owners or alter teardown custody.
        for extra in [0, 1, i32::MIN] {
            for (phase, expected) in [(0, constructor), (1, teardown)] {
                let mut plan = Lifecycle::default();
                assert_eq!(
                    unsafe { swr_v1_memory_channel_lifecycle(flags | extra, phase, &mut plan) },
                    0
                );
                assert_eq!(plan.count as usize, expected.len());
                assert_eq!(&plan.actions[..expected.len()], expected);
                assert!(plan.actions[expected.len()..].iter().all(|a| *a == 0));
            }
        }
    }
    let mut invalid = Lifecycle {
        count: 4,
        actions: [9; 4],
    };
    assert_eq!(
        unsafe { swr_v1_memory_channel_lifecycle(14, 2, &mut invalid) },
        -1
    );
    assert_eq!((invalid.count, invalid.actions), (0, [0; 4]));
    assert_eq!(
        unsafe { swr_v1_memory_channel_lifecycle(14, 0, ptr::null_mut()) },
        -1
    );
}

#[test]
fn public_capacity_predicate_preserves_defined_modular_scalar_domain() {
    assert_eq!(std::mem::size_of::<CapacityState>(), 40);
    for head in [-1, 0, 1, i64::MAX] {
        for tail in [-1, 0, 1, i64::MAX] {
            for (head_tag, tail_tag) in [(0, 0), (0, 1), (1, 0), (127, 255), (255, 255)] {
                for bytes in [0, 1, 4, usize::MAX - 3, usize::MAX] {
                    for num in [0, 1, -1, i32::MIN, i32::MAX] {
                        let modular = ((bytes as u128 + (num as usize as u128) * 4)
                            & usize::MAX as u128) as usize;
                        for size in [0, 4, 16, usize::MAX, modular] {
                            let state = CapacityState {
                                head,
                                tail,
                                size,
                                bytes,
                                num,
                                head_tag,
                                tail_tag,
                            };
                            let expected =
                                (head == tail && head_tag != tail_tag) || modular == size;
                            assert_eq!(
                                unsafe { swr_v1_memory_channel_full(&state) },
                                i32::from(expected)
                            );
                        }
                    }
                }
            }
        }
    }
    assert_eq!(unsafe { swr_v1_memory_channel_full(ptr::null()) }, -1);
}
