//! Whole entropy/codec/append workflow decisions. Every native effect completes
//! before fresh scalar observations select the next phase; no byte borrow lives here.
use super::{INVALID, OK, OVERFLOW, policy};

#[repr(C)]
#[derive(Clone, Copy, Default)]
pub struct StringRandomStep {
    pub capacity: usize,
    pub encoded_capacity: usize,
    pub length: usize,
    /// Low byte first: reserve1, entropy2, encoded owner3, codec4,
    /// append encoded5, publish length6, return false7, return true8, release encoded owner9.
    pub actions: u64,
}
fn packed(actions: &[u8]) -> u64 {
    actions.iter().enumerate().fold(0, |value, (i, action)| {
        value | (u64::from(*action) << (i * 8))
    })
}
/// Phase0 plans reserve/entropy. Phase1 consumes the native entropy result;
/// short reads stop before any encoded-owner/codec/append effect. Existing zero
/// encoded domain is not changed or qualified by this protocol.
/// # Safety
/// Output is aligned/writable/disjoint. All pointers/owners/entropy/codec/native
/// effects remain outside Rust; no allocation, callback or retained state occurs.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_string_random_step(
    phase: u32,
    length: usize,
    capacity: usize,
    requested: usize,
    read: usize,
    encoded: u32,
    alignment: usize,
    page: usize,
    output: *mut StringRandomStep,
) -> i32 {
    if output.is_null() {
        return INVALID;
    }
    let calculate = || {
        if phase > 2 || encoded > 1 {
            return Err(INVALID);
        }
        if phase == 2 {
            if encoded == 0 || length > capacity || capacity > isize::MAX as usize {
                return Err(INVALID);
            }
            let length = length
                .checked_add(read)
                .filter(|&n| n <= isize::MAX as usize)
                .ok_or(OVERFLOW)?;
            if length > capacity {
                return Err(INVALID);
            }
            return Ok(StringRandomStep {
                length,
                actions: packed(&[6, 8]),
                ..Default::default()
            });
        }
        if phase == 1 && read != requested {
            return Ok(StringRandomStep {
                actions: packed(&[7]),
                ..Default::default()
            });
        }
        let storage =
            policy::random_storage(length, capacity, requested, encoded, alignment, page)?;
        let actions = if phase == 0 {
            if storage.capacity > capacity {
                packed(&[1, 2])
            } else {
                packed(&[2])
            }
        } else if encoded != 0 {
            packed(&[3, 4, 5, 9])
        } else {
            packed(&[6, 8])
        };
        let length = if phase == 1 && encoded == 0 {
            let length = length
                .checked_add(read)
                .filter(|&n| n <= isize::MAX as usize)
                .ok_or(OVERFLOW)?;
            if length > capacity {
                return Err(INVALID);
            }
            length
        } else {
            length
        };
        Ok(StringRandomStep {
            capacity: storage.capacity,
            encoded_capacity: storage.encoded_capacity,
            length,
            actions,
        })
    };
    let (status, result) = match calculate() {
        Ok(result) => (OK, result),
        Err(status) => (status, StringRandomStep::default()),
    };
    // SAFETY: `output` is non-null (checked above), aligned, writable and disjoint.
    unsafe { output.write(result) };
    status
}

#[cfg(test)]
mod tests {
    use super::*;
    fn step(
        phase: u32,
        length: usize,
        capacity: usize,
        count: usize,
        read: usize,
        encoded: u32,
    ) -> StringRandomStep {
        let mut out = StringRandomStep::default();
        assert_eq!(
            unsafe {
                swr_v1_string_random_step(
                    phase,
                    length,
                    capacity,
                    count,
                    read,
                    encoded,
                    8,
                    4096,
                    &raw mut out,
                )
            },
            OK
        );
        out
    }
    #[test]
    fn positive_entire_workflow_matches_native_size_and_effect_model() {
        for count in [1usize, 2, 3, 4, 7, 16, 63, 1024] {
            for length in [0, 3, 31] {
                for encoded in 0..2 {
                    let extra = if encoded != 0 {
                        4 * count.div_ceil(3) + 1
                    } else {
                        0
                    };
                    let needed = length + count + extra;
                    let expected = if needed > 32 {
                        (needed * 2 + 4095) & !4095
                    } else {
                        32
                    };
                    let request = step(0, length, 32, count, 0, encoded);
                    assert_eq!(
                        (request.capacity, request.encoded_capacity),
                        (expected, extra)
                    );
                    assert_eq!(
                        request.actions,
                        if expected > 32 {
                            packed(&[1, 2])
                        } else {
                            packed(&[2])
                        }
                    );
                    let complete = step(1, length, expected, count, count, encoded);
                    assert_eq!(
                        complete.actions,
                        if encoded != 0 {
                            packed(&[3, 4, 5, 9])
                        } else {
                            packed(&[6, 8])
                        }
                    );
                    if encoded == 0 {
                        assert_eq!(complete.length, length + count);
                    } else {
                        assert_eq!(
                            step(2, length, expected, count, 4 * count.div_ceil(3), encoded).length,
                            length + 4 * count.div_ceil(3)
                        );
                    }
                    for read in [0, count - 1, count + 1] {
                        if read != count {
                            assert_eq!(
                                step(1, length, expected, count, read, encoded).actions,
                                packed(&[7])
                            );
                        }
                    }
                }
            }
        }
    }
    #[test]
    fn invalid_or_unrepresentable_metadata_clears_output() {
        assert_eq!(step(2, 2, 4096, 7, 12, 1).length, 14);
        let mut out = StringRandomStep {
            actions: 99,
            ..Default::default()
        };
        for (phase, length, capacity, count, encoded) in [
            (9, 0, 32, 1, 0),
            (0, 0, 32, 1, 2),
            (0, 33, 32, 1, 0),
            (0, 0, 32, usize::MAX, 1),
            (1, 31, 32, 7, 0),
        ] {
            assert!(
                unsafe {
                    swr_v1_string_random_step(
                        phase,
                        length,
                        capacity,
                        count,
                        count,
                        encoded,
                        8,
                        4096,
                        &raw mut out,
                    )
                } < 0
            );
            assert_eq!((out.actions, out.capacity, out.length), (0, 0, 0));
        }
        assert_eq!(
            unsafe { swr_v1_string_random_step(0, 0, 32, 1, 0, 0, 8, 4096, std::ptr::null_mut()) },
            INVALID
        );
    }
}
