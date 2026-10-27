use super::*;
use crate::allocation_tests::FAIL_AFTER;

struct NativeColumn {
    index: usize,
    width: u32,
    kind: u32,
    id: usize,
}

unsafe fn declare(
    owner: *mut OwnedColumns,
    item: &mut usize,
    created: &u8,
    name: &[u8],
    id: usize,
) -> *mut NativeColumn {
    let mut state = Declaration {
        owner,
        item_size: item,
        created,
        name: name.as_ptr(),
        length: name.len(),
        kind: 1,
        ..Declaration::default()
    };
    unsafe {
        assert_eq!(swr_v1_memory_columns_v2_declare_step(&raw mut state), 1);
    }
    let mut column = Box::new(NativeColumn {
        index: usize::MAX,
        width: 8,
        kind: 1,
        id,
    });
    state.column = (&raw mut *column).cast();
    state.column_index = &raw mut column.index;
    state.column_width = &raw const column.width;
    unsafe {
        assert_eq!(swr_v1_memory_columns_v2_declare_step(&raw mut state), 0);
        assert_eq!(swr_v1_memory_columns_v2_declare_step(&raw mut state), -1);
    }
    Box::into_raw(column)
}

#[test]
fn owned_columns_preserve_actual_order_duplicate_lookup_and_native_deletion_custody() {
    assert_eq!(mem::size_of::<Declaration>(), 104);
    assert_eq!(mem::size_of::<Cursor>(), 40);
    for count in [0usize, 1, 3, 17, 65, 257] {
        unsafe {
            let mut owner = ptr::null_mut();
            assert_eq!(swr_v1_memory_columns_v2_open(&raw mut owner), 0);
            let mut item = 0;
            let created = 0;
            let mut columns = Vec::new();
            for i in 0..count {
                let name = if i < 3 {
                    b"duplicate\0name".to_vec()
                } else {
                    format!("column{i}").into_bytes()
                };
                let column = declare(owner, &mut item, &created, &name, i);
                assert_eq!((*column).index, i * 8);
                columns.push(column);
            }
            assert_eq!(item, count * 8);
            if count > 0 {
                assert_eq!(
                    swr_v1_memory_columns_v2_get(owner, b"duplicate\0name".as_ptr(), 14),
                    columns[0].cast()
                );
            }
            let mut cursor = Cursor::default();
            assert_eq!(
                swr_v1_memory_columns_v2_cursor_open(owner, &raw mut cursor),
                0
            );
            assert_eq!(
                (cursor.count, cursor.unique_count),
                (count, if count <= 3 { count.min(1) } else { count - 2 })
            );
            for &column in &columns {
                assert_eq!(
                    swr_v1_memory_columns_v2_cursor_next(owner, &raw mut cursor),
                    1
                );
                assert_eq!(cursor.column, column.cast());
                // A native caller reads current object facts after return, not a cached metadata shadow.
                (*column).kind = 2;
                assert_eq!((*cursor.column.cast::<NativeColumn>()).kind, 2);
            }
            assert_eq!(
                swr_v1_memory_columns_v2_cursor_next(owner, &raw mut cursor),
                0
            );
            assert!(cursor.column.is_null());
            let mut token = ptr::null_mut();
            // Drain is allocation-free and transfers each token before native deletion.
            FAIL_AFTER.set(Some(0));
            for (i, &column) in columns.iter().enumerate() {
                assert_eq!(
                    swr_v1_memory_columns_v2_close_step(&raw mut owner, &raw mut token),
                    1
                );
                assert_eq!(token, column.cast());
                assert_eq!((*token.cast::<NativeColumn>()).id, i);
                drop(Box::from_raw(token.cast::<NativeColumn>()));
                assert!(
                    swr_v1_memory_columns_v2_get(owner, b"duplicate\0name".as_ptr(), 14).is_null()
                );
                assert_eq!(
                    swr_v1_memory_columns_v2_cursor_next(owner, &raw mut cursor),
                    -1
                );
            }
            assert_eq!(
                swr_v1_memory_columns_v2_close_step(&raw mut owner, &raw mut token),
                0
            );
            let no_allocation = FAIL_AFTER.replace(None);
            assert_eq!(no_allocation, Some(0));
            assert!(owner.is_null() && token.is_null());
            assert_eq!(
                swr_v1_memory_columns_v2_close_step(&raw mut owner, &raw mut token),
                0
            );
        }
    }
}

#[test]
fn declaration_oom_retains_native_token_and_never_publishes_partial_schema() {
    unsafe {
        for nth in 0..=3 {
            let mut owner = ptr::null_mut();
            assert_eq!(swr_v1_memory_columns_v2_open(&raw mut owner), 0);
            let mut item = 0;
            let created = 0;
            let mut state = Declaration {
                owner,
                item_size: &raw mut item,
                created: &raw const created,
                name: b"binary\0field".as_ptr(),
                length: 12,
                kind: 1,
                ..Declaration::default()
            };
            assert_eq!(swr_v1_memory_columns_v2_declare_step(&raw mut state), 1);
            let mut column = Box::new(NativeColumn {
                index: 99,
                width: 8,
                kind: 1,
                id: nth,
            });
            let token = (&raw mut *column).cast();
            state.column = token;
            state.column_index = &raw mut column.index;
            state.column_width = &raw const column.width;
            FAIL_AFTER.set(Some(nth));
            let result = swr_v1_memory_columns_v2_declare_step(&raw mut state);
            FAIL_AFTER.set(None);
            if nth < 3 {
                assert_eq!(result, -1);
                assert_eq!((item, column.index), (0, 99));
                let mut cursor = Cursor::default();
                assert_eq!(
                    swr_v1_memory_columns_v2_cursor_open(owner, &raw mut cursor),
                    0
                );
                assert_eq!((cursor.count, cursor.unique_count), (0, 0));
                assert!(
                    swr_v1_memory_columns_v2_get(owner, b"binary\0field".as_ptr(), 12).is_null()
                );
                drop(column); // native RAII, never transferred
            } else {
                assert_eq!(result, 0);
                assert_eq!((item, column.index), (8, 0));
                let column = Box::into_raw(column);
                let mut output = ptr::null_mut();
                assert_eq!(
                    swr_v1_memory_columns_v2_close_step(&raw mut owner, &raw mut output),
                    1
                );
                assert_eq!(output, column.cast());
                drop(Box::from_raw(column));
            }
            let mut output = ptr::null_mut();
            assert_eq!(
                swr_v1_memory_columns_v2_close_step(&raw mut owner, &raw mut output),
                0
            );
            assert!(owner.is_null());
        }
    }
}

#[test]
fn owned_columns_refuse_postcreate_or_stale_cursor_before_native_effects() {
    unsafe {
        let mut owner = ptr::null_mut();
        assert_eq!(swr_v1_memory_columns_v2_open(&raw mut owner), 0);
        let mut item = 0;
        let mut created = 0;
        let first = declare(owner, &mut item, &created, b"one", 1);
        let mut cursor = Cursor::default();
        assert_eq!(
            swr_v1_memory_columns_v2_cursor_open(owner, &raw mut cursor),
            0
        );
        let second = declare(owner, &mut item, &created, b"two", 2);
        assert_eq!(
            swr_v1_memory_columns_v2_cursor_next(owner, &raw mut cursor),
            -1
        );
        assert!(cursor.column.is_null());
        created = 1;
        let mut state = Declaration {
            owner,
            item_size: &raw mut item,
            created: &raw const created,
            name: b"three".as_ptr(),
            length: 5,
            kind: 1,
            ..Declaration::default()
        };
        assert_eq!(swr_v1_memory_columns_v2_declare_step(&raw mut state), -1);
        assert_eq!(item, 16);
        let mut token = ptr::null_mut();
        for column in [first, second] {
            assert_eq!(
                swr_v1_memory_columns_v2_close_step(&raw mut owner, &raw mut token),
                1
            );
            assert_eq!(token, column.cast());
            drop(Box::from_raw(column));
        }
        assert_eq!(
            swr_v1_memory_columns_v2_close_step(&raw mut owner, &raw mut token),
            0
        );
        FAIL_AFTER.set(Some(0));
        let result = swr_v1_memory_columns_v2_open(&raw mut owner);
        FAIL_AFTER.set(None);
        assert_eq!(result, -1);
        assert!(owner.is_null());
    }
}
