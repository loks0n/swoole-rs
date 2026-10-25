use super::*;
use crate::allocation_tests::FAIL_AFTER;

unsafe fn add(owner: *mut Records, item: &mut usize, bytes: &[u8], kind: u32, width: usize) -> i32 {
    unsafe {
        swr_v1_memory_records_declare(owner, item, &0, bytes.as_ptr(), bytes.len(), kind, width)
    }
}
#[test]
fn records_own_names_metadata_duplicates_and_copied_views() {
    assert_eq!(std::mem::size_of::<View>(), 40);
    assert_eq!(std::mem::size_of::<Cursor>(), 32);
    for count in [0usize, 1, 3, 17, 65, 257] {
        unsafe {
            let mut owner = ptr::null_mut();
            assert_eq!(swr_v1_memory_records_open(&mut owner), 0);
            let mut item = 0;
            for i in 0..count {
                let name = if i < 3 {
                    b"duplicate\0name".to_vec()
                } else {
                    format!("column{i}").into_bytes()
                };
                assert_eq!(add(owner, &mut item, &name, 1, 0), 0);
                // Native input lifetime ends here; both metadata and names are Rust-owned.
            }
            let mut cursor = Cursor::default();
            assert_eq!(swr_v1_memory_records_cursor_open(owner, &mut cursor), 0);
            assert_eq!(
                (item, cursor.count, cursor.unique_count),
                (
                    count * 8,
                    count,
                    count.saturating_sub(2).max(usize::from(count > 0))
                )
            );
            let mut view = View::default();
            for i in 0..count {
                assert_eq!(
                    swr_v1_memory_records_cursor_next(owner, &mut cursor, &mut view),
                    1
                );
                assert_eq!(
                    (view.ordinal, view.index, view.width, view.kind),
                    (i, i * 8, 8, 1)
                );
                let mut native_scratch = vec![0xa5; view.name_length + 2];
                assert_eq!(
                    swr_v1_memory_records_copy_name(
                        owner,
                        &view,
                        native_scratch.as_mut_ptr(),
                        native_scratch.len()
                    ),
                    0
                );
                let expected = if i < 3 {
                    b"duplicate\0name".to_vec()
                } else {
                    format!("column{i}").into_bytes()
                };
                assert_eq!(&native_scratch[..view.name_length], expected);
                assert_eq!(&native_scratch[view.name_length..], &[0xa5, 0xa5]);
            }
            assert_eq!(
                swr_v1_memory_records_cursor_next(owner, &mut cursor, &mut view),
                0
            );
            assert_eq!(view, View::default());
            let result =
                swr_v1_memory_records_get(owner, b"duplicate\0name".as_ptr(), 14, &mut view);
            assert_eq!(result, if count == 0 { 0 } else { 1 });
            assert_eq!(view.ordinal, 0);
            FAIL_AFTER.set(Some(0));
            let closed = swr_v1_memory_records_close(&mut owner);
            let untouched = FAIL_AFTER.replace(None);
            assert_eq!((closed, untouched), (0, Some(0)));
            assert!(owner.is_null());
            assert_eq!(swr_v1_memory_records_close(&mut owner), 0);
        }
    }
}
#[test]
fn records_allocation_failures_never_publish_partial_schema() {
    unsafe {
        let mut owner = ptr::dangling_mut();
        FAIL_AFTER.set(Some(0));
        let result = swr_v1_memory_records_open(&mut owner);
        FAIL_AFTER.set(None);
        assert_eq!(result, -1);
        assert!(owner.is_null());
        for nth in 0..=4 {
            assert_eq!(swr_v1_memory_records_open(&mut owner), 0);
            let mut item = 0;
            FAIL_AFTER.set(Some(nth));
            let result = add(owner, &mut item, b"field", 1, 0);
            FAIL_AFTER.set(None);
            let mut cursor = Cursor::default();
            assert_eq!(swr_v1_memory_records_cursor_open(owner, &mut cursor), 0);
            if nth < 4 {
                assert_eq!(
                    (result, item, cursor.count, cursor.unique_count),
                    (-1, 0, 0, 0)
                );
            } else {
                assert_eq!(
                    (result, item, cursor.count, cursor.unique_count),
                    (0, 8, 1, 1)
                );
            }
            assert_eq!(swr_v1_memory_records_close(&mut owner), 0);
        }
    }
}
#[test]
fn records_checked_copy_generation_and_postcreate_refusal() {
    unsafe {
        let mut owner = ptr::null_mut();
        assert_eq!(swr_v1_memory_records_open(&mut owner), 0);
        let mut item = 0;
        assert_eq!(add(owner, &mut item, b"first", 1, 0), 0);
        let mut view = View::default();
        assert_eq!(
            swr_v1_memory_records_get(owner, b"first".as_ptr(), 5, &mut view),
            1
        );
        let mut scratch = [0xa5; 5];
        let mut forged = view;
        forged.width = 9;
        assert_eq!(
            swr_v1_memory_records_copy_name(owner, &forged, scratch.as_mut_ptr(), 5),
            -1
        );
        assert_eq!(
            swr_v1_memory_records_copy_name(owner, &view, scratch.as_mut_ptr(), 4),
            -1
        );
        assert_eq!(scratch, [0xa5; 5]);
        let mut cursor = Cursor::default();
        assert_eq!(swr_v1_memory_records_cursor_open(owner, &mut cursor), 0);
        for (kind, requested, created) in [(99, 0, 0), (3, usize::MAX, 0), (1, 0, 1)] {
            assert!(
                swr_v1_memory_records_declare(
                    owner,
                    &mut item,
                    &created,
                    b"bad".as_ptr(),
                    3,
                    kind,
                    requested
                ) < 0
            );
            assert_eq!(item, 8);
        }
        assert_eq!(add(owner, &mut item, b"second", 3, 5), 0);
        assert_eq!(item, 17);
        assert_eq!(
            swr_v1_memory_records_copy_name(owner, &view, scratch.as_mut_ptr(), 5),
            -1
        );
        assert_eq!(scratch, [0xa5; 5]);
        assert_eq!(
            swr_v1_memory_records_cursor_next(owner, &mut cursor, &mut view),
            -1
        );
        assert_eq!(swr_v1_memory_records_close(&mut owner), 0);
    }
}
#[test]
fn records_clear_uses_authoritative_offsets_and_preserves_string_payload() {
    unsafe {
        let mut owner = ptr::null_mut();
        assert_eq!(swr_v1_memory_records_open(&mut owner), 0);
        let mut item = 0;
        for (name, kind, size) in [
            (b"int".as_slice(), 1, 0),
            (b"string".as_slice(), 3, 5),
            (b"float".as_slice(), 2, 0),
        ] {
            assert_eq!(add(owner, &mut item, name, kind, size), 0);
        }
        assert_eq!(item, 25);
        let mut row = vec![0xa5u64; (std::mem::size_of::<Row>() + item).div_ceil(8)];
        let data = row
            .as_mut_ptr()
            .cast::<u8>()
            .add(std::mem::size_of::<Row>());
        ptr::write_bytes(data, 0x5a, item);
        assert_eq!(
            swr_v1_memory_records_clear(owner, row.as_mut_ptr().cast()),
            0
        );
        assert_eq!(std::slice::from_raw_parts(data, 12), [0; 12]);
        assert_eq!(std::slice::from_raw_parts(data.add(12), 5), [0x5a; 5]);
        assert_eq!(std::slice::from_raw_parts(data.add(17), 8), [0; 8]);
        assert_eq!(swr_v1_memory_records_close(&mut owner), 0);
    }
}
