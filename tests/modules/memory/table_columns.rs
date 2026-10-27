use super::*;
#[test]
fn byte_keys_first_duplicate_lookup_and_native_token_custody() {
    unsafe {
        let mut columns = ptr::null_mut();
        assert_eq!(swr_v1_memory_table_columns_create(&raw mut columns), 0);
        let first = ptr::without_provenance_mut::<c_void>(101);
        let second = ptr::without_provenance_mut::<c_void>(202);
        assert_eq!(
            swr_v1_memory_table_columns_insert(columns, b"binary\0name".as_ptr(), 11, first),
            0
        );
        assert_eq!(
            swr_v1_memory_table_columns_insert(columns, b"binary\0name".as_ptr(), 11, second),
            1
        );
        assert_eq!(
            swr_v1_memory_table_columns_get(columns, b"binary\0name".as_ptr(), 11),
            first
        );
        assert_eq!(
            swr_v1_memory_table_columns_get(columns, b"binary".as_ptr(), 6),
            ptr::null_mut()
        );
        assert_eq!(swr_v1_memory_table_columns_count(columns), 1);
        assert_eq!(swr_v1_memory_table_columns_release(columns), -1);
        assert_eq!(
            swr_v1_memory_table_columns_insert(columns, ptr::null(), 1, second),
            -1
        );
        assert_eq!(
            swr_v1_memory_table_columns_insert(columns, ptr::null(), 0, second),
            0
        );
        assert_eq!(
            swr_v1_memory_table_columns_get(columns, ptr::null(), 0),
            second
        );
        let mut taken = vec![
            swr_v1_memory_table_columns_pop(columns).addr(),
            swr_v1_memory_table_columns_pop(columns).addr(),
        ];
        taken.sort_unstable();
        assert_eq!(taken, vec![101, 202]);
        assert!(swr_v1_memory_table_columns_pop(columns).is_null());
        assert_eq!(swr_v1_memory_table_columns_release(columns), 0);
    }
}

#[test]
fn binary_prefixes_and_every_hash_word_tail_retain_first_token_through_growth() {
    unsafe {
        let mut columns = ptr::null_mut();
        assert_eq!(swr_v1_memory_table_columns_create(&raw mut columns), 0);
        let mut names = Vec::new();
        for length in 0..=256usize {
            let name: Vec<u8> = (0..length)
                .map(|i| (i.wrapping_mul(37) ^ length) as u8)
                .collect();
            names.push(name);
        }
        // Equal prefixes followed by binary zeros distinguish key length from
        // content, and neighboring words differ near both endpoints.
        names.extend((1..=256usize).map(|length| vec![0; length]));
        for suffix in 1..=255u8 {
            let mut name = vec![0; 32];
            name[0] = suffix;
            name[31] = suffix;
            names.push(name);
        }
        for (index, name) in names.iter().enumerate() {
            let token = ptr::without_provenance_mut(index + 1);
            assert_eq!(
                swr_v1_memory_table_columns_insert(columns, name.as_ptr(), name.len(), token),
                0
            );
        }
        assert_eq!(swr_v1_memory_table_columns_count(columns), names.len());
        for (index, name) in names.iter().enumerate() {
            let token = ptr::without_provenance_mut(index + 1);
            assert_eq!(
                swr_v1_memory_table_columns_get(columns, name.as_ptr(), name.len()),
                token
            );
            assert_eq!(
                swr_v1_memory_table_columns_insert(
                    columns,
                    name.as_ptr(),
                    name.len(),
                    ptr::dangling_mut()
                ),
                1
            );
            assert_eq!(
                swr_v1_memory_table_columns_get(columns, name.as_ptr(), name.len()),
                token
            );
        }
        assert_eq!(swr_v1_memory_table_columns_count(columns), names.len());
        assert_eq!(swr_v1_memory_table_columns_discard(columns), 0);
    }
}
