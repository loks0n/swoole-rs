use super::*;

#[test]
fn sizing_and_invalid_plans_fail_closed() {
    unsafe {
        assert_eq!(mem::size_of::<Row>(), 88);
        assert_eq!(mem::offset_of!(Row, next), 16);
        assert_eq!(mem::offset_of!(Row, key), 24);
        let (mut rows, mut conflict) = (0, 0.0);
        assert_eq!(
            swr_v1_memory_table_config(65, 0.0, &mut rows, &mut conflict),
            0
        );
        assert_eq!((rows, conflict), (128, 0.2));
        assert_eq!(
            swr_v1_memory_table_config(u32::MAX, 2.0, &mut rows, &mut conflict),
            0
        );
        assert_eq!((rows, conflict), (0x8000_0000, 1.0));
        assert_eq!(
            swr_v1_memory_table_config(64, f32::NAN, &mut rows, &mut conflict),
            -1
        );
        let mut layout = Layout::default();
        assert_eq!(
            swr_v1_memory_table_layout(64, usize::MAX, 0.2, &mut layout),
            -1
        );
        assert_eq!(swr_v1_memory_table_layout(64, 23, 0.2, &mut layout), 0);
        let count = (64.0f32 * 1.2) as usize;
        assert_eq!(layout.total, count * 111 + 48 + (count - 64) * 24 + 64 * 8);
        let mut bytes = vec![0u64; layout.total.div_ceil(8)];
        assert_eq!(
            swr_v1_memory_table_arena(bytes.as_mut_ptr().cast(), &layout),
            0
        );
        let row = bytes.as_ptr().cast::<*mut Row>().add(1).read();
        assert_eq!(row.addr() % 8, 7); // Intentionally packed odd-width native rows.
        assert_eq!(
            swr_v1_memory_table_init(row, b"binary\0key".as_ptr(), 10),
            0
        );
        assert_eq!(
            swr_v1_memory_table_get(row, b"binary\0key".as_ptr(), 10),
            row
        );
        assert_eq!(
            swr_v1_memory_table_get(row, b"binary".as_ptr(), 6),
            ptr::null_mut()
        );
        layout.pool_offset = 1;
        assert_eq!(
            swr_v1_memory_table_arena(bytes.as_mut_ptr().cast(), &layout),
            -1
        );
        let mut width = 0;
        assert_eq!(
            swr_v1_memory_table_column_size(3, usize::MAX, &mut width),
            -1
        );
        assert_eq!(swr_v1_memory_table_column_size(3, 7, &mut width), 0);
        assert_eq!(width, 11);
    }
}

#[test]
fn collision_deletion_iteration_and_unaligned_values() {
    unsafe {
        let mut bytes = vec![0u8; (88 + 23) * 4 + 1];
        let root = bytes.as_mut_ptr().add(1).cast::<Row>();
        let second = root.cast::<u8>().add(111).cast::<Row>();
        let third = second.cast::<u8>().add(111).cast::<Row>();
        assert_eq!(swr_v1_memory_table_init(root, b"a".as_ptr(), 1), 0);
        let mut plan = Plan::default();
        assert_eq!(
            swr_v1_memory_table_set_plan(root, b"b".as_ptr(), 1, &mut plan),
            1
        );
        assert_eq!((plan.parent, plan.level, plan.flags), (root.cast(), 1, 1));
        assert_eq!(swr_v1_memory_table_init(second, b"b".as_ptr(), 1), 0);
        ptr::addr_of_mut!((*root).next).write_unaligned(second);
        assert_eq!(swr_v1_memory_table_init(third, b"c".as_ptr(), 1), 0);
        ptr::addr_of_mut!((*second).next).write_unaligned(third);
        assert_eq!(
            swr_v1_memory_table_set_plan(root, b"c".as_ptr(), 1, &mut plan),
            0
        );
        assert_eq!((plan.row, plan.level, plan.flags), (third.cast(), 3, 2));
        let number = 123456i64;
        assert_eq!(
            swr_v1_memory_table_set_value(second, 0, 8, 1, (&number as *const i64).cast(), 0),
            0
        );
        assert_eq!(
            swr_v1_memory_table_set_value(second, 8, 11, 3, b"123456789".as_ptr().cast(), 9),
            0
        );
        let mut removed = ptr::null_mut();
        assert_eq!(
            swr_v1_memory_table_delete(root, b"a".as_ptr(), 1, 23, &mut removed),
            0
        );
        assert_eq!(removed, second.cast());
        assert_eq!(swr_v1_memory_table_get(root, b"b".as_ptr(), 1), root);
        let mut output = 0i64;
        assert_eq!(
            swr_v1_memory_table_get_number(root, 0, (&mut output as *mut i64).cast()),
            0
        );
        assert_eq!(output, number);
        let (mut string, mut length) = (ptr::null_mut(), 0);
        assert_eq!(
            swr_v1_memory_table_get_string(root, 8, 11, &mut string, &mut length),
            0
        );
        assert_eq!(slice::from_raw_parts(string, length as usize), b"1234567");
        let current = third.cast::<u8>().add(111).cast::<Row>();
        let (mut index, mut advance) = (0, 0);
        assert_eq!(
            swr_v1_memory_table_next(root, 1, current, 111, &mut index, &mut advance),
            0
        );
        assert_eq!((index, advance), (2, 0));
        assert_eq!(swr_v1_memory_table_get(current, b"c".as_ptr(), 1), current);
        assert_eq!(
            swr_v1_memory_table_next(root, 2, current, 111, &mut index, &mut advance),
            1
        );
        assert_eq!(index, 0);
        assert_eq!(
            swr_v1_memory_table_delete(root, b"c".as_ptr(), 1, 23, &mut removed),
            0
        );
        assert_eq!(removed, third.cast());
        assert_eq!(
            swr_v1_memory_table_next(root, 9, current, 111, &mut index, &mut advance),
            0
        );
        assert_eq!((index, advance), (9, 1)); // Preserve native single-row iterator behavior.
    }
}

#[test]
fn typed_column_clear_preserves_header_string_payload_and_invalid_input() {
    unsafe {
        for (kind, width, cleared) in [(1, 8, 8), (2, 8, 8), (3, 11, 4)] {
            let mut storage = [0xa5u8; 160];
            let row = storage.as_mut_ptr().add(1).cast::<Row>();
            let mut expected = storage;
            let start = 1 + mem::size_of::<Row>() + 4;
            expected[start..start + cleared].fill(0);
            assert_eq!(swr_v1_memory_table_clear_value(row, 4, width, kind), 0);
            assert_eq!(storage, expected);
            for (bad_kind, bad_width) in [(0, 8), (1, 7), (2, 9), (3, 3), (4, 8)] {
                assert_eq!(
                    swr_v1_memory_table_clear_value(row, 4, bad_width, bad_kind),
                    -1
                );
                assert_eq!(storage, expected);
            }
            assert_eq!(
                swr_v1_memory_table_clear_value(row, usize::MAX, width, kind),
                -1
            );
            assert_eq!(
                swr_v1_memory_table_clear_value(ptr::null_mut(), 4, width, kind),
                -1
            );
            assert_eq!(storage, expected);
        }
    }
}

#[test]
fn native_storage_stride_alignment_preserves_frozen_logical_plan_and_header() {
    unsafe {
        assert_eq!(mem::size_of::<Row>(), 88);
        assert_eq!(mem::align_of::<Row>(), 8);
        for rows in [64, 128] {
            for item in 0..=128usize {
                let mut logical = Layout::default();
                let mut storage = Layout::default();
                assert_eq!(swr_v1_memory_table_layout(rows, item, 0.2, &mut logical), 0);
                assert_eq!(
                    swr_v1_memory_table_storage_layout(rows, item, 0.2, &mut storage),
                    0
                );
                assert_eq!(logical.row_size, 88 + item);
                assert_eq!(storage.row_size, (88 + item).next_multiple_of(8));
                let all_rows = (rows as f32 * 1.2) as usize;
                assert_eq!(
                    storage.total - logical.total,
                    all_rows * (storage.row_size - logical.row_size)
                );
                if item % 8 == 0 {
                    assert_eq!(storage.total, logical.total);
                    assert_eq!(storage.pool_size, logical.pool_size);
                }
                let mut arena = vec![0u64; storage.total.div_ceil(8)];
                assert_eq!(
                    swr_v1_memory_table_arena(arena.as_mut_ptr().cast(), &storage),
                    0
                );
                let pointers = arena.as_ptr().cast::<*mut Row>();
                for index in 0..rows as usize {
                    let row = pointers.add(index).read();
                    assert!(row.addr().is_multiple_of(mem::align_of::<Row>()));
                    assert_eq!(
                        row.addr() - pointers.read().addr(),
                        index * storage.row_size
                    );
                }
                // A fixed slice header precedes every conflict row; both its
                // storage base and every complete slice stride stay aligned.
                assert!(storage.pool_offset.is_multiple_of(8));
                assert!(
                    (storage.row_size + mem::size_of::<crate::fixed::Slice>()).is_multiple_of(8)
                );
            }
        }
        for item in [usize::MAX, usize::MAX - 88] {
            let mut storage = Layout::default();
            assert_eq!(
                swr_v1_memory_table_storage_layout(64, item, 0.2, &mut storage),
                -1
            );
            assert_eq!(
                (
                    storage.total,
                    storage.row_size,
                    storage.pool_offset,
                    storage.pool_size,
                    storage.rows
                ),
                (0, 0, 0, 0, 0)
            );
        }
    }
}

#[test]
fn binary_key_equality_checks_every_byte_without_reading_beyond_either_span() {
    unsafe {
        for length in 0..=63usize {
            for shift in [0usize, 1, 3, 7] {
                let mut storage = vec![0u8; mem::size_of::<Row>() + shift];
                let row = storage.as_mut_ptr().add(shift).cast::<Row>();
                let mut input = vec![0u8; length + shift].into_boxed_slice();
                let key = &mut input[shift..];
                for (index, byte) in key.iter_mut().enumerate() {
                    *byte = (index as u8).wrapping_mul(73); // Includes binary NUL.
                }
                assert_eq!(
                    swr_v1_memory_table_init(row, key.as_ptr(), length as u16),
                    0
                );
                assert_eq!(
                    swr_v1_memory_table_get(row, key.as_ptr(), length as u16),
                    row
                );
                for index in 0..length {
                    key[index] ^= 0x80;
                    assert!(swr_v1_memory_table_get(row, key.as_ptr(), length as u16).is_null());
                    let mut plan = Plan::default();
                    assert_eq!(
                        swr_v1_memory_table_set_plan(row, key.as_ptr(), length as u16, &mut plan),
                        1
                    );
                    assert_eq!(plan.parent, row.cast());
                    let mut removed = ptr::null_mut();
                    assert_eq!(
                        swr_v1_memory_table_delete(
                            row,
                            key.as_ptr(),
                            length as u16,
                            0,
                            &mut removed
                        ),
                        1
                    );
                    assert!(removed.is_null());
                    key[index] ^= 0x80;
                }
                assert_eq!(
                    swr_v1_memory_table_get(row, key.as_ptr(), length as u16),
                    row
                );
                if length != 0 {
                    assert!(
                        swr_v1_memory_table_get(row, key.as_ptr(), (length - 1) as u16).is_null()
                    );
                }
            }
        }
    }
}

#[test]
fn descriptor_batches_clear_only_values_and_reject_any_invalid_batch_before_writes() {
    assert_eq!(mem::size_of::<Column>(), 16);
    for shift in [0usize, 1, 7] {
        let mut bytes = vec![0xa5u8; shift + 88 + 64 + 1];
        let row = unsafe { bytes.as_mut_ptr().add(shift).cast::<Row>() };
        // Deliberately unsorted and overlapping, as public native descriptors
        // may change after declaration; only the supplied snapshot controls it.
        let columns = [
            Column {
                index: 32,
                width: 13,
                kind: 3,
            },
            Column {
                index: 0,
                width: 8,
                kind: 1,
            },
            Column {
                index: 8,
                width: 8,
                kind: 2,
            },
            Column {
                index: 1,
                width: 8,
                kind: 1,
            },
            Column {
                index: 16,
                width: 4,
                kind: 3,
            },
        ];
        let unchanged = bytes.clone();
        unsafe {
            assert_eq!(
                swr_v1_memory_table_clear_columns(row, columns.as_ptr(), columns.len(), 64),
                0
            );
        }
        let mut expected = unchanged.clone();
        expected[shift + 88..shift + 108].fill(0);
        expected[shift + 120..shift + 124].fill(0);
        assert_eq!(bytes, expected);
        for bad in [
            Column {
                index: 63,
                width: 8,
                kind: 1,
            },
            Column {
                index: usize::MAX,
                width: 8,
                kind: 1,
            },
            Column {
                index: 0,
                width: 7,
                kind: 1,
            },
            Column {
                index: 0,
                width: 3,
                kind: 3,
            },
            Column {
                index: 0,
                width: 8,
                kind: 0,
            },
        ] {
            bytes.copy_from_slice(&unchanged);
            let batch = [
                Column {
                    index: 0,
                    width: 8,
                    kind: 1,
                },
                bad,
            ];
            unsafe {
                assert_eq!(
                    swr_v1_memory_table_clear_columns(row, batch.as_ptr(), 2, 64),
                    -1
                );
            }
            assert_eq!(bytes, unchanged);
        }
        unsafe {
            assert_eq!(
                swr_v1_memory_table_clear_columns(row, ptr::null(), 0, 64),
                0
            );
            assert_eq!(
                swr_v1_memory_table_clear_columns(row, ptr::null(), 1, 64),
                -1
            );
            assert_eq!(
                swr_v1_memory_table_clear_columns(row, columns.as_ptr(), usize::MAX, 64),
                -1
            );
            assert_eq!(
                swr_v1_memory_table_clear_columns(row, columns.as_ptr(), columns.len(), usize::MAX),
                -1
            );
            assert_eq!(
                swr_v1_memory_table_clear_columns(ptr::null_mut(), ptr::null(), 0, 0),
                -1
            );
        }
        assert_eq!(bytes, unchanged);
    }
}

#[test]
fn iterator_resume_owns_bucket_and_collision_progress_with_native_observations() {
    unsafe {
        assert_eq!(mem::size_of::<IteratorFields>(), 32);
        let mut arena = vec![0u64; 12 * 5];
        let rows: Vec<*mut Row> = (0..5)
            .map(|i| arena.as_mut_ptr().add(i * 12).cast())
            .collect();
        for (index, row) in rows.iter().enumerate().skip(1) {
            assert_eq!(
                swr_v1_memory_table_init(*row, &[b'a' + index as u8 - 1][0], 1),
                0
            );
            row.cast::<u8>().add(88).write_bytes(index as u8, 8);
        }
        let root = rows[1];
        let second = rows[2];
        ptr::addr_of_mut!((*root).next).write(second);
        ptr::addr_of_mut!((*second).next).write(rows[3]);
        let buckets = [rows[0], rows[1], rows[4]];
        let mut current = [0xabab_abab_abab_ababu64; 12];
        let (mut absolute, mut collision) = (99u32, 99u32);
        let fields = IteratorFields {
            absolute: &mut absolute,
            collision: &mut collision,
            current: current.as_mut_ptr().cast(),
            row_size: 96,
        };
        assert_eq!(swr_v1_memory_table_iterator_reset(&fields), 0);
        assert_eq!((absolute, collision), (0, 0));
        assert_eq!(current, [0; 12]);
        let mut observed = Vec::new();
        let mut cursor_states = Vec::new();
        for _ in 0..5 {
            let mut index = 999;
            let mut status =
                swr_v1_memory_table_iterator_step(&fields, 3, ptr::null_mut(), 0, &mut index);
            while status == 1 {
                // This models the native activity observation and lock effect;
                // Rust receives a locked root or NULL, never an unlocked header.
                let row = buckets[index as usize];
                let locked = if active(row) { row } else { ptr::null_mut() };
                status = swr_v1_memory_table_iterator_step(&fields, 3, locked, 1, &mut index);
            }
            assert_eq!(status, 0);
            cursor_states.push((absolute, collision));
            if active(fields.current) {
                observed.push(ptr::addr_of!((*fields.current).key).cast::<u8>().read());
            }
        }
        assert_eq!(observed, b"abcd");
        assert_eq!(cursor_states, [(1, 1), (1, 2), (1, 3), (3, 0), (3, 0)]);
        assert!(
            slice::from_raw_parts(fields.current.cast::<u8>(), 88)
                .iter()
                .all(|v| *v == 0)
        );
        assert_eq!(
            slice::from_raw_parts(fields.current.cast::<u8>().add(88), 8),
            [4; 8]
        );
        // Empty/end forward clears only the header; rewind clears the full row.
        assert_eq!(swr_v1_memory_table_iterator_reset(&fields), 0);
        assert_eq!(current, [0; 12]);
        let mut index = 999;
        assert_eq!(
            swr_v1_memory_table_iterator_step(&fields, 0, ptr::null_mut(), 0, &mut index),
            0
        );
        assert_eq!((absolute, collision, index), (0, 0, 0));
    }
}

#[test]
fn iterator_invalid_scalar_contracts_reject_without_cursor_or_current_publication() {
    let (mut absolute, mut collision) = (7u32, 9u32);
    let mut current = [0xabab_abab_abab_ababu64; 12];
    let mut fields = IteratorFields {
        absolute: &mut absolute,
        collision: &mut collision,
        current: current.as_mut_ptr().cast(),
        row_size: 96,
    };
    for phase in [2, u32::MAX] {
        let mut index = 999;
        assert_eq!(
            unsafe {
                swr_v1_memory_table_iterator_step(&fields, 8, ptr::null_mut(), phase, &mut index)
            },
            -1
        );
        assert_eq!(index, 0);
    }
    fields.row_size = 87;
    assert_eq!(unsafe { swr_v1_memory_table_iterator_reset(&fields) }, -1);
    let mut index = 999;
    assert_eq!(
        unsafe { swr_v1_memory_table_iterator_step(&fields, 8, ptr::null_mut(), 0, &mut index) },
        -1
    );
    fields.row_size = 96;
    fields.absolute = ptr::null_mut();
    assert_eq!(unsafe { swr_v1_memory_table_iterator_reset(&fields) }, -1);
    assert_eq!(
        unsafe { swr_v1_memory_table_iterator_step(&fields, 8, ptr::null_mut(), 0, &mut index) },
        -1
    );
    assert_eq!((absolute, collision), (7, 9));
    assert_eq!(current, [0xabab_abab_abab_abab; 12]);
}

#[derive(Default)]
struct CounterStore {
    rows: AtomicU32,
    inserted: AtomicI64,
    deleted: AtomicI64,
    updated: AtomicI64,
    conflicts: AtomicUsize,
    max_conflict: AtomicU32,
}
impl CounterStore {
    fn fields(&self) -> CounterFields {
        CounterFields {
            rows: self.rows.as_ptr(),
            inserted: self.inserted.as_ptr(),
            deleted: self.deleted.as_ptr(),
            updated: self.updated.as_ptr(),
            conflicts: self.conflicts.as_ptr(),
            max_conflict: self.max_conflict.as_ptr(),
        }
    }
    fn values(&self) -> (u32, i64, i64, i64, usize, u32) {
        (
            self.rows.load(Ordering::SeqCst),
            self.inserted.load(Ordering::SeqCst),
            self.deleted.load(Ordering::SeqCst),
            self.updated.load(Ordering::SeqCst),
            self.conflicts.load(Ordering::SeqCst),
            self.max_conflict.load(Ordering::SeqCst),
        )
    }
}
fn mutation(store: &CounterStore, root: *mut Row, key: &[u8], mode: u32) -> Mutation {
    Mutation {
        counters: store.fields(),
        root,
        key: key.as_ptr(),
        key_length: key.len() as u16,
        mode,
        item_size: 8,
        ..Mutation::default()
    }
}
#[test]
fn mutation_owns_real_links_and_counters_around_native_pool_effect_boundaries() {
    assert_eq!(mem::size_of::<CounterFields>(), 48);
    assert_eq!(mem::size_of::<Mutation>(), 144);
    let counters = CounterStore::default();
    let mut arena = [0u64; 12 * 3];
    let root = arena.as_mut_ptr().cast::<Row>();
    let second = unsafe { arena.as_mut_ptr().add(12).cast::<Row>() };
    let third = unsafe { arena.as_mut_ptr().add(24).cast::<Row>() };
    let mut flags = 717;
    unsafe {
        let mut first = mutation(&counters, root, b"a", 0);
        first.out_flags = &mut flags;
        assert_eq!(swr_v1_memory_table_mutation_step(&mut first), 0);
        assert_eq!((first.row, first.phase, flags), (root, 2, 1));
        assert_eq!(counters.values(), (1, 1, 0, 0, 0, 0));
        let mut update = mutation(&counters, root, b"a", 0);
        update.out_flags = &mut flags;
        assert_eq!(swr_v1_memory_table_mutation_step(&mut update), 0);
        assert_eq!(flags, 0);
        assert_eq!(counters.values(), (1, 1, 0, 1, 0, 0));

        flags = 717;
        let mut aborted = mutation(&counters, root, b"b", 0);
        aborted.out_flags = &mut flags;
        assert_eq!(swr_v1_memory_table_mutation_step(&mut aborted), 1);
        assert_eq!(
            (aborted.phase, aborted.row, flags),
            (1, ptr::null_mut(), 717)
        );
        assert_eq!(counters.values(), (1, 1, 0, 1, 1, 1));
        assert!(next(root).is_null());
        // A failed pool allocation does not resume; first conflict observation
        // remains counted, exactly at the original before-allocation boundary.
        assert_eq!(swr_v1_memory_table_mutation_step(&mut aborted), -1);
        assert_eq!(counters.values(), (1, 1, 0, 1, 1, 1));

        let mut add = mutation(&counters, root, b"b", 0);
        add.out_flags = &mut flags;
        assert_eq!(swr_v1_memory_table_mutation_step(&mut add), 1);
        add.row = second;
        assert_eq!(swr_v1_memory_table_mutation_step(&mut add), 0);
        assert_eq!((next(root), flags), (second, 1));
        assert_eq!(counters.values(), (2, 2, 0, 1, 2, 1));
        let mut add = mutation(&counters, root, b"c", 0);
        add.out_flags = &mut flags;
        assert_eq!(swr_v1_memory_table_mutation_step(&mut add), 1);
        add.row = third;
        assert_eq!(swr_v1_memory_table_mutation_step(&mut add), 0);
        third.cast::<u8>().add(88).write_bytes(0xcc, 8);
        assert_eq!((next(second), flags), (third, 3));
        assert_eq!(counters.values(), (3, 3, 0, 1, 3, 2));

        let key = vec![b'b'];
        let mut delete = mutation(&counters, root, &key, 1);
        assert_eq!(swr_v1_memory_table_mutation_step(&mut delete), 1);
        drop(key); // Delete resume does not borrow its already-consumed key token.
        assert_eq!(
            (delete.phase, delete.removed, next(root)),
            (1, second, third)
        );
        assert_eq!(counters.values(), (3, 3, 0, 1, 3, 2));
        assert_eq!(swr_v1_memory_table_clear(second, 1), 0); // simulated native pool effect
        assert_eq!(swr_v1_memory_table_mutation_step(&mut delete), 0);
        assert_eq!(counters.values(), (2, 3, 1, 1, 3, 2));
        let mut delete = mutation(&counters, root, b"a", 1);
        assert_eq!(swr_v1_memory_table_mutation_step(&mut delete), 1);
        assert_eq!(delete.removed, third);
        assert_eq!(
            slice::from_raw_parts(root.cast::<u8>().add(88), 8),
            [0xcc; 8]
        );
        assert_eq!(swr_v1_memory_table_clear(third, 1), 0);
        assert_eq!(swr_v1_memory_table_mutation_step(&mut delete), 0);
        assert_eq!(counters.values(), (1, 3, 2, 1, 3, 2));
        let mut absent = mutation(&counters, root, b"absent", 1);
        assert_eq!(swr_v1_memory_table_mutation_step(&mut absent), 2);
        assert_eq!(counters.values(), (1, 3, 2, 1, 3, 2));
        let mut last = mutation(&counters, root, b"c", 1);
        assert_eq!(swr_v1_memory_table_mutation_step(&mut last), 0);
        assert_eq!(counters.values(), (0, 3, 3, 1, 3, 2));
        assert!(!active(root));
        assert_eq!(swr_v1_memory_table_mutation_step(&mut last), -1); // completed tokens cannot replay
    }
}

#[test]
fn mutation_rejects_invalid_scalar_context_before_row_or_counter_writes() {
    let counters = CounterStore::default();
    let mut row = [0u64; 12];
    let mut flags = 717;
    for case in 0..5 {
        let mut m = mutation(&counters, row.as_mut_ptr().cast(), b"valid", 0);
        m.out_flags = &mut flags;
        match case {
            0 => m.mode = 2,
            1 => m.phase = 2,
            2 => m.counters.rows = ptr::null_mut(),
            3 => m.root = ptr::null_mut(),
            4 => m.key_length = 64,
            _ => unreachable!(),
        }
        assert_eq!(unsafe { swr_v1_memory_table_mutation_step(&mut m) }, -1);
        assert_eq!(flags, 717);
        assert_eq!(row, [0; 12]);
        assert_eq!(counters.values(), (0, 0, 0, 0, 0, 0));
    }
}

#[test]
fn rust_only_independent_root_mutations_share_atomic_statistics_without_native_race_oracle() {
    use std::sync::Arc;
    let counters = Arc::new(CounterStore::default());
    let workers: Vec<_> = (0..4)
        .map(|_| {
            let counters = Arc::clone(&counters);
            std::thread::spawn(move || {
                for _ in 0..64 {
                    let mut row = [0u64; 24];
                    let root = row.as_mut_ptr().cast::<Row>();
                    let second = unsafe { row.as_mut_ptr().add(12).cast::<Row>() };
                    unsafe {
                        let mut a = mutation(&counters, root, b"a", 0);
                        assert_eq!(swr_v1_memory_table_mutation_step(&mut a), 0);
                        let mut b = mutation(&counters, root, b"b", 0);
                        assert_eq!(swr_v1_memory_table_mutation_step(&mut b), 1);
                        b.row = second;
                        assert_eq!(swr_v1_memory_table_mutation_step(&mut b), 0);
                        let mut update = mutation(&counters, root, b"a", 0);
                        assert_eq!(swr_v1_memory_table_mutation_step(&mut update), 0);
                        let mut b = mutation(&counters, root, b"b", 1);
                        assert_eq!(swr_v1_memory_table_mutation_step(&mut b), 1);
                        assert_eq!(swr_v1_memory_table_clear(b.removed, 1), 0);
                        assert_eq!(swr_v1_memory_table_mutation_step(&mut b), 0);
                        let mut a = mutation(&counters, root, b"a", 1);
                        assert_eq!(swr_v1_memory_table_mutation_step(&mut a), 0);
                    }
                }
            })
        })
        .collect();
    for worker in workers {
        worker.join().unwrap();
    }
    assert_eq!(counters.values(), (0, 512, 512, 256, 256, 1));
}

#[test]
fn teardown_preserves_duplicate_declaration_order_and_real_field_lifetimes() {
    unsafe {
        assert_eq!(std::mem::size_of::<Teardown>(), 88);
        assert_eq!(std::mem::size_of::<TeardownEffect>(), 16);
        for created in [false, true] {
            let columns: Vec<*mut c_void> = (0..if created { 3 } else { 0 })
                .map(|i| Box::into_raw(Box::new(i as u64)).cast())
                .collect();
            let list = Box::into_raw(Box::new(columns.clone()));
            let mut index = ptr::null_mut();
            assert_eq!(
                crate::table_columns::swr_v1_memory_table_columns_create(&mut index),
                0
            );
            if created {
                for (name, token, status) in [
                    (b"same".as_slice(), columns[0], 0),
                    (b"same".as_slice(), columns[1], 1),
                    (b"other".as_slice(), columns[2], 0),
                ] {
                    assert_eq!(
                        crate::table_columns::swr_v1_memory_table_columns_insert(
                            index,
                            name.as_ptr(),
                            name.len(),
                            token
                        ),
                        status
                    );
                }
            }
            let memory = if created {
                Box::into_raw(Box::new([42u64; 8])).cast::<c_void>()
            } else {
                ptr::null_mut()
            };
            // Model actual Table-owned field. Its address becomes dangling at the
            // final native owner effect; terminal resume must not read it again.
            let owner = Box::into_raw(Box::new(memory));
            let iterator = if created {
                Box::into_raw(Box::new(3u8)).cast::<c_void>()
            } else {
                ptr::null_mut()
            };
            let pool = if created {
                Box::into_raw(Box::new(4u8)).cast::<c_void>()
            } else {
                ptr::null_mut()
            };
            let mutex = Box::into_raw(Box::new(6u8)).cast::<c_void>();
            let mut state = Teardown {
                index,
                columns: (*list).as_ptr(),
                count: (*list).len(),
                position: 0,
                list: list.cast(),
                iterator,
                pool,
                memory: owner,
                mutex,
                table: owner.cast(),
                phase: 0,
            };
            let mut effect = TeardownEffect::default();
            let mut actions = Vec::new();
            let mut deleted = Vec::new();
            loop {
                let status = swr_v1_memory_table_teardown_step(&mut state, &mut effect);
                if status == 0 {
                    break;
                }
                assert_eq!(status, 1);
                assert!(state.index.is_null());
                actions.push(effect.action);
                match effect.action {
                    1 => {
                        deleted.push(effect.token);
                        drop(Box::from_raw(effect.token.cast::<u64>()));
                    }
                    2 => {
                        assert_eq!(deleted, columns);
                        drop(Box::from_raw(effect.token.cast::<Vec<*mut c_void>>()));
                    }
                    3 | 4 => {
                        if !effect.token.is_null() {
                            drop(Box::from_raw(effect.token.cast::<u8>()));
                        }
                    }
                    5 => {
                        assert_eq!(*owner, effect.token);
                        drop(Box::from_raw(effect.token.cast::<[u64; 8]>()));
                    }
                    6 => {
                        assert!((*owner).is_null());
                        drop(Box::from_raw(effect.token.cast::<u8>()));
                    }
                    7 => {
                        assert!((*owner).is_null());
                        drop(Box::from_raw(effect.token.cast::<*mut c_void>()));
                    }
                    _ => panic!("unexpected effect"),
                }
            }
            assert_eq!(
                actions,
                if created {
                    vec![1, 1, 1, 2, 3, 4, 5, 6, 7]
                } else {
                    vec![2, 3, 4, 6, 7]
                }
            );
            assert_eq!((state.phase, effect.action), (8, 0));
            assert!(effect.token.is_null());
            assert_eq!(
                swr_v1_memory_table_teardown_step(&mut state, &mut effect),
                0
            );
        }
    }
}

#[test]
fn teardown_invalid_scalar_cursor_rejects_before_acquiring_resources() {
    unsafe {
        let mut memory = ptr::null_mut();
        let mut state = Teardown {
            index: ptr::null_mut(),
            columns: ptr::null(),
            count: 1,
            position: 0,
            list: ptr::null_mut(),
            iterator: ptr::null_mut(),
            pool: ptr::null_mut(),
            memory: &mut memory,
            mutex: ptr::null_mut(),
            table: ptr::null_mut(),
            phase: 0,
        };
        let mut effect = TeardownEffect {
            token: ptr::dangling_mut(),
            action: 7,
        };
        assert_eq!(
            swr_v1_memory_table_teardown_step(&mut state, &mut effect),
            -1
        );
        assert_eq!((state.phase, state.position, effect.action), (0, 0, 0));
        assert!(effect.token.is_null());
        state.count = 0;
        state.phase = 9;
        assert_eq!(
            swr_v1_memory_table_teardown_step(&mut state, &mut effect),
            -1
        );
        state.phase = 0;
        state.memory = ptr::null_mut();
        assert_eq!(
            swr_v1_memory_table_teardown_step(&mut state, &mut effect),
            -1
        );
        assert_eq!(
            swr_v1_memory_table_teardown_step(ptr::null_mut(), &mut effect),
            -1
        );
    }
}

#[derive(Default)]
struct MetadataStore {
    size: usize,
    mask: usize,
    item: usize,
    memory_size: usize,
    conflict: f32,
    created: u8,
    rows: *mut *mut Row,
    pool: *mut c_void,
    iterator: *mut c_void,
    memory: *mut c_void,
}
impl MetadataStore {
    fn fields(&mut self, counters: &CounterStore) -> MetadataFields {
        MetadataFields {
            size: &mut self.size,
            mask: &mut self.mask,
            item_size: &mut self.item,
            memory_size: &mut self.memory_size,
            conflict: &mut self.conflict,
            created: &mut self.created,
            rows: &mut self.rows,
            pool: &mut self.pool,
            iterator: &mut self.iterator,
            memory: &mut self.memory,
            counters: counters.fields(),
        }
    }
}

#[test]
fn metadata_initialization_validates_before_writes_and_owns_real_scalar_targets() {
    unsafe {
        assert_eq!(mem::size_of::<MetadataFields>(), 128);
        assert_eq!(mem::size_of::<Creation>(), 112);
        let counters = CounterStore::default();
        counters.rows.store(7, Ordering::SeqCst);
        let mut storage = MetadataStore {
            size: 997,
            mask: 31,
            item: 11,
            memory_size: 77,
            conflict: 0.5,
            created: 1,
            ..MetadataStore::default()
        };
        let mut fields = storage.fields(&counters);
        assert_eq!(
            swr_v1_memory_table_metadata_initialize(&fields, 101, f32::NAN),
            -1
        );
        assert_eq!(
            (
                storage.size,
                storage.mask,
                storage.item,
                storage.memory_size,
                storage.created
            ),
            (997, 31, 11, 77, 1)
        );
        assert_eq!(counters.rows.load(Ordering::SeqCst), 7);
        let valid = fields.mask;
        fields.mask = ptr::null_mut();
        assert_eq!(
            swr_v1_memory_table_metadata_initialize(&fields, 101, 0.5),
            -1
        );
        assert_eq!(storage.size, 997);
        fields.mask = valid;
        assert_eq!(
            swr_v1_memory_table_metadata_initialize(&fields, 101, 0.5),
            0
        );
        assert_eq!(
            (
                storage.size,
                storage.mask,
                storage.item,
                storage.memory_size,
                storage.created
            ),
            (128, 127, 0, 0, 0)
        );
        assert_eq!(storage.conflict, 0.5);
        assert!(
            storage.rows.is_null()
                && storage.pool.is_null()
                && storage.iterator.is_null()
                && storage.memory.is_null()
        );
        assert_eq!(counters.values(), (0, 0, 0, 0, 0, 0));
    }
}

#[test]
fn creation_publishes_only_validated_ready_storage_and_preserves_logical_accounting() {
    unsafe {
        let counters = CounterStore::default();
        let mut storage = MetadataStore::default();
        let fields = storage.fields(&counters);
        assert_eq!(swr_v1_memory_table_metadata_initialize(&fields, 64, 0.5), 0);
        storage.item = 1;
        let mut state = Creation::default();
        assert_eq!(swr_v1_memory_table_creation_step(&fields, &mut state), 1);
        assert_eq!(
            (state.phase, state.logical.row_size, state.physical.row_size),
            (1, 89, 96)
        );
        assert_eq!(storage.created, 0);
        assert!(storage.memory.is_null());
        assert_eq!(swr_v1_memory_table_creation_step(&fields, &mut state), -1);
        let mut arena = vec![0u64; state.physical.total.div_ceil(8)];
        state.memory = arena.as_mut_ptr().cast();
        assert_eq!(swr_v1_memory_table_arena(state.memory, &state.physical), 0);
        let mut pool = 1u64;
        let mut iterator = 2u64;
        state.pool = (&mut pool as *mut u64).cast();
        state.iterator = (&mut iterator as *mut u64).cast();
        let expected = state.physical;
        state.physical.row_size += 8;
        assert_eq!(swr_v1_memory_table_creation_step(&fields, &mut state), -1);
        assert_eq!(storage.created, 0);
        assert!(storage.memory.is_null());
        state.physical = expected;
        storage.item = 2;
        assert_eq!(swr_v1_memory_table_creation_step(&fields, &mut state), -1);
        assert_eq!(storage.created, 0);
        storage.item = 1;
        assert_eq!(swr_v1_memory_table_creation_step(&fields, &mut state), 0);
        assert_eq!((state.phase, storage.created), (2, 1));
        assert_eq!(
            (storage.memory, storage.pool, storage.iterator),
            (state.memory, state.pool, state.iterator)
        );
        assert_eq!(storage.rows, state.memory.cast::<*mut Row>());
        assert_eq!(storage.memory_size, state.logical.pool_size);
        assert_ne!(storage.memory_size, state.physical.pool_size);
        assert_eq!(
            *storage.rows,
            state
                .memory
                .cast::<u8>()
                .add(64 * mem::size_of::<*mut Row>())
                .cast()
        );
        assert_eq!(swr_v1_memory_table_creation_step(&fields, &mut state), -1);
        let mut repeated = Creation::default();
        assert_eq!(
            swr_v1_memory_table_creation_step(&fields, &mut repeated),
            -1
        );
        assert_eq!(storage.created, 1);
    }
}

#[repr(C)]
struct DeclarationColumn {
    width: u32,
    index: usize,
}
#[test]
fn declaration_couples_real_offsets_duplicate_index_and_native_owned_tokens() {
    unsafe {
        assert_eq!(mem::size_of::<Declaration>(), 96);
        let mut index = ptr::null_mut();
        assert_eq!(
            crate::table_columns::swr_v1_memory_table_columns_create(&mut index),
            0
        );
        let mut item_size = 0;
        let mut public_list = Vec::new();
        for (name, kind, requested, width, offset) in [
            (b"same".as_slice(), 1, 0, 8, 0),
            (b"same".as_slice(), 3, 5, 9, 8),
            (b"n\0x".as_slice(), 2, 0, 8, 17),
        ] {
            let mut state = Declaration {
                index,
                item_size: &mut item_size,
                name: name.as_ptr(),
                length: name.len(),
                kind,
                requested,
                ..Declaration::default()
            };
            assert_eq!(swr_v1_memory_table_declaration_step(&mut state), 1);
            assert_eq!((state.width, item_size), (width, offset));
            let column = Box::into_raw(Box::new(DeclarationColumn {
                width,
                index: usize::MAX,
            }));
            state.column = column.cast();
            state.column_index = &mut (*column).index;
            state.column_width = &mut (*column).width;
            assert_eq!(swr_v1_memory_table_declaration_step(&mut state), 2);
            assert_eq!(((*column).index, item_size), (offset, offset));
            public_list.push(column);
            assert_eq!(swr_v1_memory_table_declaration_step(&mut state), 0);
            assert_eq!(item_size, offset + width as usize);
            assert_eq!(swr_v1_memory_table_declaration_step(&mut state), -1);
        }
        assert_eq!(item_size, 25);
        assert_eq!(
            crate::table_columns::swr_v1_memory_table_columns_count(index),
            2
        );
        assert_eq!(
            crate::table_columns::swr_v1_memory_table_columns_get(index, b"same".as_ptr(), 4),
            public_list[0].cast()
        );
        assert_eq!(
            crate::table_columns::swr_v1_memory_table_columns_discard(index),
            0
        );
        for token in public_list {
            drop(Box::from_raw(token));
        }
    }
}

#[test]
fn declaration_oom_requests_native_append_rollback_without_publishing() {
    unsafe {
        let mut index = ptr::null_mut();
        assert_eq!(
            crate::table_columns::swr_v1_memory_table_columns_create(&mut index),
            0
        );
        let mut item_size = 19;
        let name = b"new";
        let mut state = Declaration {
            index,
            item_size: &mut item_size,
            name: name.as_ptr(),
            length: name.len(),
            kind: 1,
            ..Declaration::default()
        };
        assert_eq!(swr_v1_memory_table_declaration_step(&mut state), 1);
        let mut column = Box::new(DeclarationColumn { width: 8, index: 0 });
        state.column = (&mut *column as *mut DeclarationColumn).cast();
        state.column_index = &mut column.index;
        state.column_width = &mut column.width;
        assert_eq!(swr_v1_memory_table_declaration_step(&mut state), 2);
        let mut public_list = vec![state.column];
        crate::allocation_tests::FAIL_AFTER.set(Some(0));
        let status = swr_v1_memory_table_declaration_step(&mut state);
        crate::allocation_tests::FAIL_AFTER.set(None);
        assert_eq!(status, 3);
        assert_eq!(public_list.pop(), Some(state.column));
        assert_eq!((item_size, column.index, state.phase), (19, 19, 3));
        assert_eq!(
            crate::table_columns::swr_v1_memory_table_columns_count(index),
            0
        );
        drop(column);
        assert_eq!(swr_v1_memory_table_declaration_step(&mut state), -1);
        assert_eq!(
            crate::table_columns::swr_v1_memory_table_columns_discard(index),
            0
        );
    }
}

#[test]
fn declaration_rejects_type_overflow_and_changed_width_before_publication() {
    unsafe {
        let mut index = ptr::null_mut();
        assert_eq!(
            crate::table_columns::swr_v1_memory_table_columns_create(&mut index),
            0
        );
        let mut item_size = usize::MAX - 3;
        let mut state = Declaration {
            index,
            item_size: &mut item_size,
            kind: 9,
            ..Declaration::default()
        };
        assert_eq!(swr_v1_memory_table_declaration_step(&mut state), -2);
        state.kind = 1;
        assert_eq!(swr_v1_memory_table_declaration_step(&mut state), -1);
        assert_eq!((item_size, state.phase), (usize::MAX - 3, 0));
        item_size = 0;
        assert_eq!(swr_v1_memory_table_declaration_step(&mut state), 1);
        let mut column = DeclarationColumn {
            width: 8,
            index: 99,
        };
        state.column = (&mut column as *mut DeclarationColumn).cast();
        state.column_index = &mut column.index;
        state.column_width = &mut column.width;
        assert_eq!(swr_v1_memory_table_declaration_step(&mut state), 2);
        column.width = 9;
        assert_eq!(swr_v1_memory_table_declaration_step(&mut state), 3);
        assert_eq!((item_size, state.phase, column.width), (0, 3, 9));
        assert_eq!(swr_v1_memory_table_declaration_step(&mut state), -1);
        assert_eq!(
            crate::table_columns::swr_v1_memory_table_columns_discard(index),
            0
        );
    }
}

#[test]
fn lookup_preserves_full_u16_normalization_and_native_callback_fact_boundary() {
    unsafe {
        assert_eq!(mem::size_of::<Lookup>(), 56);
        let mut arena = [0u64; 24];
        let roots = [
            arena.as_mut_ptr().cast::<Row>(),
            arena.as_mut_ptr().add(12).cast::<Row>(),
        ];
        for length in 0..=u16::MAX {
            let mut state = Lookup {
                rows: roots.as_ptr(),
                count: 2,
                mask: 1,
                length,
                ..Lookup::default()
            };
            assert_eq!(swr_v1_memory_table_lookup_step(&mut state), 1);
            assert_eq!(state.length, if length < 64 { length } else { 63 });
            assert!(state.row.is_null());
            // Represents the completed native callback result, not a Rust callback.
            state.hash = u64::from(length);
            assert_eq!(swr_v1_memory_table_lookup_step(&mut state), 0);
            assert_eq!(
                (state.index, state.row, state.phase),
                ((length & 1) as usize, roots[(length & 1) as usize], 2)
            );
            assert_eq!(swr_v1_memory_table_lookup_step(&mut state), -1);
        }
    }
}

#[test]
fn lookup_rejects_invalid_scalar_span_before_pointer_array_access() {
    unsafe {
        let mut state = Lookup::default();
        assert_eq!(swr_v1_memory_table_lookup_step(&mut state), -1);
        let root = ptr::null_mut();
        state.rows = &root;
        state.count = 1;
        state.mask = usize::MAX;
        state.length = 64;
        assert_eq!(swr_v1_memory_table_lookup_step(&mut state), 1);
        state.hash = 1;
        assert_eq!(swr_v1_memory_table_lookup_step(&mut state), -1);
        assert_eq!((state.index, state.phase), (1, 1));
        assert!(state.row.is_null());
    }
}

#[test]
fn clear_cursor_uses_live_facts_in_order_across_batch_boundaries() {
    assert_eq!(mem::size_of::<Clear>(), 240);
    for count in [0usize, 1, 7, 8, 9, 17] {
        let mut columns: Vec<Column> = (0..count)
            .map(|i| Column {
                index: i * 16,
                width: 16,
                kind: 3,
            })
            .collect();
        // These are native object tokens in production, never dereferenced by
        // Rust policy. The model copies scalar facts only after each return.
        let tokens: Vec<*mut c_void> = columns
            .iter_mut()
            .map(|c| (c as *mut Column).cast())
            .collect();
        let mut bytes = vec![0xa5u8; 88 + count * 16];
        let mut state = Clear {
            row: bytes.as_mut_ptr().cast(),
            columns: tokens.as_ptr(),
            count,
            item_size: count * 16,
            ..Clear::default()
        };
        let mut seen = Vec::new();
        unsafe {
            loop {
                let status = swr_v1_memory_table_clear_step(&mut state);
                if status == 0 {
                    break;
                }
                assert_eq!(status, 1);
                assert_eq!(state.take as usize, (count - seen.len()).min(8));
                for i in 0..state.take as usize {
                    let column = &mut *state.tokens[i].cast::<Column>();
                    // Public metadata may be mutated after declaration; no
                    // cached copy may override the fresh native descriptor.
                    if seen.len() % 2 == 0 {
                        column.kind = 1;
                        column.width = 8;
                    }
                    state.batch[i] = *column;
                    seen.push(column.index);
                }
            }
            assert_eq!(swr_v1_memory_table_clear_step(&mut state), 0);
        }
        assert_eq!(seen, (0..count).map(|i| i * 16).collect::<Vec<_>>());
        let mut expected = vec![0xa5u8; bytes.len()];
        for i in 0..count {
            let size = if i % 2 == 0 { 8 } else { 4 };
            expected[88 + i * 16..88 + i * 16 + size].fill(0);
        }
        assert_eq!(bytes, expected); // row header/string payload/padding preserved
    }
    let mut empty = Clear::default();
    unsafe {
        assert_eq!(swr_v1_memory_table_clear_step(&mut empty), 0);
    }
}

#[test]
fn clear_cursor_failure_preserves_prior_batches_and_refuses_restart() {
    let mut fact = Column {
        index: 0,
        width: 8,
        kind: 1,
    };
    let token = (&mut fact as *mut Column).cast::<c_void>();
    // Duplicate tokens retain their exact order; they do not become owners.
    let tokens = [token; 9];
    let mut bytes = vec![0xa5u8; 104];
    let mut state = Clear {
        row: bytes.as_mut_ptr().cast(),
        columns: tokens.as_ptr(),
        count: 9,
        item_size: 16,
        ..Clear::default()
    };
    unsafe {
        assert_eq!(swr_v1_memory_table_clear_step(&mut state), 1);
        assert_eq!(state.tokens, [token; 8]);
        state.batch.fill(fact);
        assert_eq!(swr_v1_memory_table_clear_step(&mut state), 1);
        assert_eq!((state.position, state.take), (8, 1));
        assert_eq!(&bytes[88..96], &[0; 8]);
        state.batch[0] = Column { index: 16, ..fact };
        let before = bytes.clone();
        assert_eq!(swr_v1_memory_table_clear_step(&mut state), -1);
        assert_eq!(bytes, before);
        state.batch[0] = fact;
        assert_eq!(swr_v1_memory_table_clear_step(&mut state), -1);
        assert_eq!(bytes, before);
        let null_tokens = [ptr::null_mut()];
        let mut invalid = Clear {
            row: bytes.as_mut_ptr().cast(),
            columns: null_tokens.as_ptr(),
            count: 1,
            item_size: 16,
            ..Clear::default()
        };
        assert_eq!(swr_v1_memory_table_clear_step(&mut invalid), -1);
        assert_eq!(bytes, before);
    }
}

#[test]
fn value_warning_precedes_any_write_and_normal_values_complete_in_one_call() {
    assert_eq!(mem::size_of::<Value>(), 48);
    for kind in [1, 2, 3] {
        for length in [0, 1, 4, 8, 16] {
            for null in [false, true] {
                if null && kind != 3 {
                    continue;
                }
                let mut bytes = vec![0xa5u8; 104];
                let value = vec![0x5au8; 16];
                let mut state = Value {
                    row: bytes.as_mut_ptr().cast(),
                    value: if null {
                        ptr::null()
                    } else {
                        value.as_ptr().cast()
                    },
                    length,
                    index: 3,
                    width: 8,
                    kind,
                    phase: 0,
                };
                let before = bytes.clone();
                unsafe {
                    let status = swr_v1_memory_table_value_step(&mut state);
                    if kind == 3 && length > 4 {
                        assert_eq!(status, 1);
                        assert_eq!(bytes, before); // warning effect BEFORE writes
                        assert_eq!(swr_v1_memory_table_value_step(&mut state), 0);
                    } else {
                        assert_eq!(status, 0);
                    }
                    let mut expected = before;
                    if kind == 3 {
                        let n = if null { 0 } else { length.min(4) };
                        expected[91..95].copy_from_slice(&(n as u32).to_ne_bytes());
                        expected[95..95 + n].fill(0x5a);
                    } else {
                        expected[91..99].fill(0x5a);
                    }
                    assert_eq!(bytes, expected);
                    drop(value); // terminal replay must not access input storage
                    assert_eq!(swr_v1_memory_table_value_step(&mut state), -1);
                    assert_eq!(bytes, expected);
                }
            }
        }
    }
}

#[test]
fn iterator_release_preserves_null_skip_and_native_effect_order_without_borrows() {
    assert_eq!(mem::size_of::<IteratorRelease>(), 24);
    unsafe {
        let mut row = Some(Box::new([0xa5u8; 32]));
        let mut mutex = Some(Box::new(7u8));
        let mut replacement = Some(Box::new(9u8));
        let mut state = IteratorRelease {
            current: row.as_mut().unwrap().as_mut_ptr().cast(),
            mutex: (&mut **mutex.as_mut().unwrap() as *mut u8).cast(),
            phase: 0,
        };
        let mut effect = TeardownEffect::default();
        assert_eq!(
            swr_v1_memory_table_iterator_release_step(&mut state, &mut effect),
            1
        );
        assert_eq!((effect.token, effect.action), (state.current, 1));
        drop(row.take());
        // Native refreshes actual mutex field after custom free callback; Rust
        // does not hold the earlier native token as hidden shadow ownership.
        state.mutex = (&mut **replacement.as_mut().unwrap() as *mut u8).cast();
        assert_eq!(
            swr_v1_memory_table_iterator_release_step(&mut state, &mut effect),
            1
        );
        assert_eq!((effect.token, effect.action), (state.mutex, 2));
        drop(replacement.take());
        drop(mutex.take());
        assert_eq!(
            swr_v1_memory_table_iterator_release_step(&mut state, &mut effect),
            0
        );
        assert!(effect.token.is_null() && effect.action == 0);
        assert_eq!(
            swr_v1_memory_table_iterator_release_step(&mut state, &mut effect),
            0
        );
        let mut null = IteratorRelease::default();
        assert_eq!(
            swr_v1_memory_table_iterator_release_step(&mut null, &mut effect),
            1
        );
        assert!(effect.token.is_null() && effect.action == 2); // delete-null effect
        assert_eq!(
            swr_v1_memory_table_iterator_release_step(&mut null, &mut effect),
            0
        );
        null.phase = 3;
        assert_eq!(
            swr_v1_memory_table_iterator_release_step(&mut null, &mut effect),
            -1
        );
    }
}

#[test]
fn collection_free_core_teardown_preserves_real_resource_effects_without_column_owner() {
    unsafe {
        for created in [false, true] {
            let arena = if created {
                Box::into_raw(Box::new([17u64; 8])).cast::<c_void>()
            } else {
                ptr::null_mut()
            };
            let owner = Box::into_raw(Box::new(arena));
            let iterator = if created {
                Box::into_raw(Box::new(3u8)).cast::<c_void>()
            } else {
                ptr::null_mut()
            };
            let pool = if created {
                Box::into_raw(Box::new(4u8)).cast::<c_void>()
            } else {
                ptr::null_mut()
            };
            let mutex = Box::into_raw(Box::new(6u8)).cast::<c_void>();
            let mut state = Teardown {
                index: ptr::null_mut(),
                columns: ptr::null(),
                count: 0,
                position: 0,
                list: ptr::null_mut(),
                iterator,
                pool,
                memory: owner,
                mutex,
                table: owner.cast(),
                phase: 0,
            };
            let mut effect = TeardownEffect::default();
            let mut actions = Vec::new();
            loop {
                crate::allocation_tests::FAIL_AFTER.set(Some(0));
                let status = swr_v1_memory_table_core_teardown_step(&mut state, &mut effect);
                let unchanged = crate::allocation_tests::FAIL_AFTER.replace(None);
                assert_eq!(unchanged, Some(0));
                if status == 0 {
                    break;
                }
                assert_eq!(status, 1);
                actions.push(effect.action);
                match effect.action {
                    3 | 4 | 6 if !effect.token.is_null() => {
                        drop(Box::from_raw(effect.token.cast::<u8>()))
                    }
                    3 | 4 => {}
                    5 => drop(Box::from_raw(effect.token.cast::<[u64; 8]>())),
                    7 => {
                        assert!((*owner).is_null());
                        drop(Box::from_raw(owner));
                    }
                    _ => panic!("unexpected collection effect"),
                }
            }
            assert_eq!(
                actions,
                if created {
                    vec![3, 4, 5, 6, 7]
                } else {
                    vec![3, 4, 6, 7]
                }
            );
            // Actual owner/memory field is already freed; terminal scratch resume
            // remains valid and does not inspect that released allocation.
            assert_eq!(
                swr_v1_memory_table_core_teardown_step(&mut state, &mut effect),
                0
            );
        }
    }
}

#[test]
fn collection_free_core_refuses_legacy_or_mixed_collection_custody() {
    unsafe {
        let mut memory = ptr::null_mut();
        for case in 0..7 {
            let mut state = Teardown {
                index: ptr::null_mut(),
                columns: ptr::null(),
                count: 0,
                position: 0,
                list: ptr::null_mut(),
                iterator: ptr::null_mut(),
                pool: ptr::null_mut(),
                memory: &mut memory,
                mutex: ptr::null_mut(),
                table: ptr::null_mut(),
                phase: 0,
            };
            match case {
                0 => state.index = ptr::dangling_mut(),
                1 => state.columns = ptr::dangling(),
                2 => state.list = ptr::dangling_mut(),
                3 => state.count = 1,
                4 => state.position = 1,
                5 => state.phase = 1,
                6 => state.phase = 2,
                _ => unreachable!(),
            }
            let mut effect = TeardownEffect {
                token: ptr::dangling_mut(),
                action: 99,
            };
            assert_eq!(
                swr_v1_memory_table_core_teardown_step(&mut state, &mut effect),
                -1
            );
            assert!(effect.token.is_null());
            assert_eq!(effect.action, 0);
        }
    }
}

#[test]
fn construction_sequences_normal_storage_effects_before_single_publication() {
    unsafe {
        assert_eq!(mem::size_of::<Construction>(), 120);
        assert_eq!(mem::size_of::<ConstructionEffect>(), 32);
        for rows in [64, 128, 256] {
            for item in [8, 16, 24] {
                for conflict in [0.2, 0.5, 1.0] {
                    let counters = CounterStore::default();
                    let mut metadata = MetadataStore::default();
                    let fields = metadata.fields(&counters);
                    assert_eq!(
                        swr_v1_memory_table_metadata_initialize(&fields, rows, conflict),
                        0
                    );
                    metadata.item = item;
                    let mut state = Construction::default();
                    let mut effect = ConstructionEffect::default();
                    assert_eq!(
                        swr_v1_memory_table_construction_step(&fields, &mut state, &mut effect),
                        1
                    );
                    assert_eq!(
                        (effect.action, effect.size),
                        (1, state.storage.physical.total)
                    );
                    assert!(effect.memory.is_null());
                    let mut arena = vec![0x5a5a5a5a5a5a5a5au64; effect.size.div_ceil(8)];
                    state.storage.memory = arena.as_mut_ptr().cast();
                    assert_eq!(
                        swr_v1_memory_table_construction_step(&fields, &mut state, &mut effect),
                        1
                    );
                    assert_eq!(
                        (effect.action, effect.size, effect.row_size),
                        (
                            2,
                            state.storage.physical.pool_size,
                            state.storage.physical.row_size
                        )
                    );
                    assert_eq!(
                        effect.memory,
                        state
                            .storage
                            .memory
                            .cast::<u8>()
                            .add(state.storage.physical.pool_offset)
                            .cast()
                    );
                    // All row headers/pointers initialized, payload and pool bytes untouched.
                    let pointers = state.storage.memory.cast::<*mut Row>();
                    for index in 0..rows as usize {
                        let row = pointers.add(index).read();
                        assert_eq!(
                            row.cast::<u8>(),
                            state
                                .storage
                                .memory
                                .cast::<u8>()
                                .add(rows as usize * 8 + index * effect.row_size)
                        );
                        assert!(
                            slice::from_raw_parts(row.cast::<u8>(), mem::size_of::<Row>())
                                .iter()
                                .all(|&byte| byte == 0)
                        );
                        assert_eq!(*row.cast::<u8>().add(mem::size_of::<Row>()), 0x5a);
                    }
                    assert_eq!(*effect.memory.cast::<u8>(), 0x5a);
                    let mut pool_token = 7u64;
                    state.storage.pool = (&mut pool_token as *mut u64).cast();
                    assert_eq!(
                        swr_v1_memory_table_construction_step(&fields, &mut state, &mut effect),
                        1
                    );
                    assert_eq!(
                        (effect.action, effect.size),
                        (3, state.storage.physical.row_size)
                    );
                    assert_eq!(metadata.created, 0);
                    assert!(
                        metadata.memory.is_null()
                            && metadata.pool.is_null()
                            && metadata.iterator.is_null()
                    );
                    let mut iterator_token = 9u64;
                    state.storage.iterator = (&mut iterator_token as *mut u64).cast();
                    assert_eq!(
                        swr_v1_memory_table_construction_step(&fields, &mut state, &mut effect),
                        0
                    );
                    assert_eq!(effect.action, 0);
                    assert_eq!(metadata.created, 1);
                    assert_eq!(metadata.rows, pointers);
                    assert_eq!(metadata.memory, state.storage.memory);
                    assert_eq!(metadata.pool, state.storage.pool);
                    assert_eq!(metadata.iterator, state.storage.iterator);
                    assert_eq!(metadata.memory_size, state.storage.logical.pool_size);
                }
            }
        }
    }
}

#[test]
fn factory_sequences_actual_modes_and_initializes_only_after_native_tokens() {
    unsafe {
        assert_eq!(mem::size_of::<Factory>(), 48);
        for legacy in [0, 1] {
            for requested in [64, 101, 256] {
                let counters = CounterStore::default();
                let mut metadata = MetadataStore::default();
                let fields = metadata.fields(&counters);
                let mut state = Factory {
                    rows: requested,
                    conflict: 0.5,
                    legacy,
                    ..Default::default()
                };
                assert_eq!(swr_v1_memory_table_factory_step(ptr::null(), &mut state), 1);
                let mut table_token = 1u64;
                state.table = (&mut table_token as *mut u64).cast();
                assert_eq!(swr_v1_memory_table_factory_step(ptr::null(), &mut state), 2);
                let mut mutex_token = 2u64;
                state.mutex = (&mut mutex_token as *mut u64).cast();
                let mut list_token = 3u64;
                if legacy == 1 {
                    assert_eq!(swr_v1_memory_table_factory_step(ptr::null(), &mut state), 3);
                    state.list = (&mut list_token as *mut u64).cast();
                }
                assert_eq!(metadata.size, 0);
                assert_eq!(swr_v1_memory_table_factory_step(&fields, &mut state), 0);
                assert_eq!(metadata.size, requested.next_power_of_two() as usize);
                assert_eq!(metadata.mask, metadata.size - 1);
                assert_eq!(metadata.conflict, 0.5);
                assert_eq!(metadata.created, 0);
                assert!(metadata.memory.is_null() && metadata.rows.is_null());
                assert_eq!(state.index.is_null(), legacy == 0);
                if legacy == 1 {
                    assert_eq!(
                        crate::table_columns::swr_v1_memory_table_columns_count(state.index),
                        0
                    );
                    assert_eq!(
                        crate::table_columns::swr_v1_memory_table_columns_discard(state.index),
                        0
                    );
                }
            }
        }
    }
}
