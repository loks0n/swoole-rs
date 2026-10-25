//! Initialized local arena/effect witnesses only. No OS mapping, File, failure,
//! callback, fork, thread or resource-lifetime operation executes here.
use super::*;

unsafe fn allocate(
    storage: &mut [u64],
    requested: usize,
    anonymous: bool,
    descriptor: i32,
) -> *mut u8 {
    let mut state = MappingOperation {
        requested,
        anonymous: u32::from(anonymous),
        flags: 0x10,
        anonymous_flags: 0x20,
        ..MappingOperation::default()
    };
    let mut output = MappingEffect::default();
    assert_eq!(
        unsafe { swr_v2_memory_mapping_step(&mut state, &mut output) },
        1
    );
    if !anonymous {
        assert_eq!(output.action, 1); // Inert successful File-constructor result.
        state.descriptor = descriptor;
        state.result = 1;
        assert_eq!(
            unsafe { swr_v2_memory_mapping_step(&mut state, &mut output) },
            1
        );
    }
    assert_eq!(output.action, 2);
    let total = requested.div_ceil(8) * 8 + 8;
    assert_eq!(output.size, total);
    assert_eq!(output.flags, if anonymous { 0x30 } else { 0x10 });
    assert_eq!(output.descriptor, if anonymous { -1 } else { descriptor });
    assert!(storage.len() * 8 >= total + 8);
    state.memory = storage.as_mut_ptr().cast();
    state.result = 1; // Initialized local backing stands in for a successful map.
    assert_eq!(
        unsafe { swr_v2_memory_mapping_step(&mut state, &mut output) },
        0
    );
    assert_eq!(storage[0] as usize, total);
    assert_eq!(output.memory, unsafe {
        storage.as_mut_ptr().cast::<u8>().add(8).cast()
    });
    assert!(
        storage[1..]
            .iter()
            .all(|&value| value == 0xa5a5_a5a5_a5a5_a5a5)
    );
    output.memory.cast()
}

unsafe fn release(payload: *mut u8, base: *mut u8, total: usize) {
    let mut state = MappingOperation {
        kind: RELEASE,
        source: payload,
        ..MappingOperation::default()
    };
    let mut output = MappingEffect::default();
    assert_eq!(
        unsafe { swr_v2_memory_mapping_step(&mut state, &mut output) },
        1
    );
    assert_eq!(
        (output.action, output.memory, output.size),
        (4, base.cast(), total)
    );
    state.result = 0; // No actual munmap or lifetime transition.
    assert_eq!(
        unsafe { swr_v2_memory_mapping_step(&mut state, &mut output) },
        0
    );
}

#[test]
fn mapping_operations_preserve_normal_effect_parameters_and_publication() {
    assert_eq!(std::mem::size_of::<MappingOperation>(), 64);
    assert_eq!(std::mem::size_of::<MappingEffect>(), 32);
    for requested in [1, 7, 8, 9, 63, 256] {
        for (anonymous, descriptor) in [(true, -1), (false, 0), (false, 3), (false, 19)] {
            let mut storage = [0xa5a5_a5a5_a5a5_a5a5u64; 40];
            let payload = unsafe { allocate(&mut storage, requested, anonymous, descriptor) };
            let before = storage;
            let mut state = MappingOperation {
                kind: PROTECT,
                source: payload,
                flags: 3,
                ..MappingOperation::default()
            };
            let mut output = MappingEffect::default();
            assert_eq!(
                unsafe { swr_v2_memory_mapping_step(&mut state, &mut output) },
                1
            );
            assert_eq!(
                (output.action, output.memory, output.size, output.flags),
                (6, storage.as_mut_ptr().cast(), storage[0] as usize, 3)
            );
            state.result = 0; // No actual mprotect.
            assert_eq!(
                unsafe { swr_v2_memory_mapping_step(&mut state, &mut output) },
                0
            );
            assert_eq!(output.result, 0);
            assert_eq!(storage, before);
            unsafe { release(payload, storage.as_mut_ptr().cast(), storage[0] as usize) };
            assert_eq!(storage, before);
        }
    }
}

#[test]
fn mapping_growth_uses_complete_nested_success_effects_before_publication() {
    for previous in [8, 24, 64] {
        for requested in [128, 256] {
            let mut old = [0xa5a5_a5a5_a5a5_a5a5u64; 40];
            let mut new = old;
            let source = unsafe { allocate(&mut old, previous, true, -1) };
            for i in 0..old[0] as usize - 8 {
                unsafe { source.add(i).write((i * 37 + 11) as u8) };
            }
            let before = old;
            let mut state = MappingOperation {
                kind: REALLOCATE,
                source,
                requested,
                ..MappingOperation::default()
            };
            let mut output = MappingEffect::default();
            assert_eq!(
                unsafe { swr_v2_memory_mapping_step(&mut state, &mut output) },
                1
            );
            assert_eq!((output.action, output.size), (8, requested));
            let destination = unsafe { allocate(&mut new, requested, true, -1) };
            state.memory = destination;
            assert_eq!(
                unsafe { swr_v2_memory_mapping_step(&mut state, &mut output) },
                1
            );
            assert_eq!((output.action, output.memory), (10, source.cast()));
            let copied = old[0] as usize - 8;
            for i in 0..new[0] as usize - 8 {
                assert_eq!(
                    unsafe { destination.add(i).read() },
                    if i < copied {
                        (i * 37 + 11) as u8
                    } else {
                        0xa5
                    }
                );
            }
            unsafe { release(source, old.as_mut_ptr().cast(), old[0] as usize) };
            assert_eq!(
                unsafe { swr_v2_memory_mapping_step(&mut state, &mut output) },
                0
            );
            assert_eq!(output.memory, destination.cast());
            assert_eq!(old, before);
            assert_eq!(new[39], 0xa5a5_a5a5_a5a5_a5a5);
        }
    }
}
