use super::*;
#[test]
fn mapping_bounds_exclude_header_and_limit_shrinking_copies() {
    unsafe {
        let mut size = 99;
        assert_eq!(swr_v1_memory_mapping_size(0, &mut size), 0);
        assert_eq!(size, 8);
        assert_eq!(swr_v1_memory_mapping_size(9, &mut size), 0);
        assert_eq!(size, 24);
        assert_eq!(swr_v1_memory_mapping_size(usize::MAX, &mut size), -1);
        assert_eq!(size, 0);
        assert_eq!(swr_v1_memory_mapping_product(usize::MAX, 2, &mut size), -1);
        assert_eq!(size, 0);
        assert_eq!(swr_v1_memory_mapping_product(usize::MAX, 0, &mut size), 0);
        assert_eq!(size, 0);
        assert_eq!(swr_v1_memory_mapping_copy(65544, 16, &mut size), 0);
        assert_eq!(size, 8);
        assert_eq!(swr_v1_memory_mapping_copy(16, 65544, &mut size), 0);
        assert_eq!(size, 8);
        assert_eq!(swr_v1_memory_mapping_copy(0, 16, &mut size), -1);
        assert_eq!(size, 0);
    }
}

#[test]
fn actual_mapping_headers_and_payload_relocation_remain_in_their_live_arenas() {
    for old_size in [8usize, 16, 24, 80, 1032] {
        for new_size in [8usize, 16, 32, 88, 2056] {
            let mut old = vec![0xa5a5_a5a5_a5a5_a5a5u64; old_size / 8 + 1];
            let mut new = vec![0u64; new_size / 8 + 1];
            new[new_size / 8] = 0xfeed_face_dead_beef;
            unsafe {
                let source = swr_v1_memory_mapping_initialize(old.as_mut_ptr().cast(), old_size);
                let destination =
                    swr_v1_memory_mapping_initialize(new.as_mut_ptr().cast(), new_size);
                assert_eq!(source, old.as_mut_ptr().cast::<u8>().add(8));
                assert_eq!(destination, new.as_mut_ptr().cast::<u8>().add(8));
                for i in 0..old_size - 8 {
                    source.add(i).write((i * 37 + 11) as u8);
                }
                let original = old.clone();
                assert_eq!(swr_v1_memory_mapping_relocate(source, destination), 0);
                assert_eq!(old, original);
                let mut view = Extent::default();
                assert_eq!(swr_v1_memory_mapping_extent(destination, &mut view), 0);
                assert_eq!((view.base, view.total), (new.as_mut_ptr().cast(), new_size));
                assert_eq!(new[0] as usize, new_size);
                let copied = old_size.min(new_size) - 8;
                let data = std::slice::from_raw_parts(destination, new_size - 8);
                for (i, &byte) in data.iter().enumerate() {
                    assert_eq!(byte, if i < copied { (i * 37 + 11) as u8 } else { 0 });
                }
                assert_eq!(new[new_size / 8], 0xfeed_face_dead_beef);
            }
        }
    }
}
