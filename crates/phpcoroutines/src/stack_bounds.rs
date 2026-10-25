//! Stack-bound selection/unsigned reserve scaling; Native projects real pointers.
#[repr(C)]
pub struct BoundsState {
    stage: u32,
    reserve: usize,
}
#[repr(C)]
pub struct BoundsPlan {
    pub action: u32,
    pub reserve: usize,
}

/// # Safety
/// State is exclusive zero-initialized local POD. Kind/caps are fixed, with caps
/// bit0 Native thread-context mode and bit1 Native Apple scaling. Observations
/// answer only requested reserve/presence facts. No stack/context/Zend pointer
/// enters Rust; original pointer projection/validity remain Native.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_bounds(
    state: *mut BoundsState,
    kind: u32,
    caps: u8,
    observation: usize,
) -> BoundsPlan {
    let state = unsafe { &mut *state };
    let current = state.stage;
    state.stage = current.saturating_add(1);
    let action = if current == 0 && caps & 1 != 0 {
        1
    } else if kind == 0 {
        match current {
            0 => 2,
            1 => {
                state.reserve = observation.wrapping_mul(if caps & 2 != 0 { 2 } else { 1 });
                3
            }
            2 if observation != 0 => 4,
            _ => 1,
        }
    } else {
        match current {
            0 => 3,
            1 if observation != 0 => 5,
            _ => 1,
        }
    };
    BoundsPlan {
        action,
        reserve: state.reserve,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn native_capabilities_short_circuit_and_unsigned_scaling_order() {
        for caps in 0..4 {
            for kind in 0..2 {
                for reserve in [0, 1, 1024, usize::MAX / 2 + 1, usize::MAX] {
                    for present in [0, 1] {
                        let mut state = BoundsState {
                            stage: 0,
                            reserve: 0,
                        };
                        unsafe {
                            let first = swr_v1_phpcoroutines_bounds(&mut state, kind, caps, 0);
                            if caps & 1 != 0 {
                                assert_eq!(first.action, 1);
                                continue;
                            }
                            if kind == 0 {
                                assert_eq!(first.action, 2);
                                let co =
                                    swr_v1_phpcoroutines_bounds(&mut state, kind, caps, reserve);
                                assert_eq!(co.action, 3);
                                assert_eq!(
                                    co.reserve,
                                    reserve.wrapping_mul(if caps & 2 != 0 { 2 } else { 1 })
                                );
                            } else {
                                assert_eq!(first.action, 3);
                            }
                            assert_eq!(
                                swr_v1_phpcoroutines_bounds(&mut state, kind, caps, present).action,
                                if present == 0 {
                                    1
                                } else if kind == 0 {
                                    4
                                } else {
                                    5
                                }
                            );
                        }
                    }
                }
            }
        }
    }
}
