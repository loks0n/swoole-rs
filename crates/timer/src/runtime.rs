//! Stateless native clock/backend adaptation; never calls clocks or foreign code.

const BILLION: i64 = 1_000_000_000;

#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct NativeTime {
    pub seconds: i64,
    pub fraction: i64,
}

/// Native init mode: manual=0, reactor=1, system=2. No worker-role inference.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_timer_backend(manual: u32, reactor: u32) -> u32 {
    if manual != 0 {
        0
    } else if reactor != 0 {
        1
    } else {
        2
    }
}

/// Nonpositive milliseconds disarm; positive values produce timeval microseconds.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_timer_system_interval(milliseconds: i64) -> NativeTime {
    if milliseconds <= 0 {
        NativeTime {
            seconds: 0,
            fraction: 0,
        }
    } else {
        NativeTime {
            seconds: milliseconds / 1000,
            fraction: milliseconds % 1000 * 1000,
        }
    }
}

/// Preserve truncation toward zero, including negative native epoch values.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_timer_realtime_split(nanoseconds: i64) -> NativeTime {
    NativeTime {
        seconds: nanoseconds / BILLION,
        fraction: nanoseconds % BILLION,
    }
}

/// Preserve native positive carry only: negative fractions are not floor-normalized.
/// Parity covers original defined signed arithmetic/conversion ranges.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_timer_realtime_add(
    seconds: i64,
    nanoseconds: i64,
    milliseconds: i64,
) -> NativeTime {
    let mut seconds = seconds.wrapping_add(milliseconds / 1000);
    let mut fraction = nanoseconds.wrapping_add(milliseconds % 1000 * 1_000_000);
    if fraction >= BILLION {
        // The native helper stores the quotient in int before its int product.
        #[expect(
            clippy::cast_possible_truncation,
            reason = "the native helper's int quotient"
        )]
        let carry = (fraction / BILLION) as i32;
        seconds = seconds.wrapping_add(i64::from(carry));
        #[expect(
            clippy::cast_possible_truncation,
            reason = "BILLION fits the native int product"
        )]
        let billion = BILLION as i32;
        fraction = fraction.wrapping_sub(i64::from(carry.wrapping_mul(billion)));
    }
    NativeTime { seconds, fraction }
}

/// Native clocks remain outside Rust; overflow was outside original defined input.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_timer_relative_msec(absolute: i64, base: i64) -> i64 {
    absolute.wrapping_sub(base)
}

/// Preserve the armed timeout unless an accepted add needs an earlier wakeup.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_timer_rearm_after_add(current: i64, delay: i64) -> i64 {
    if current < 0 || current > delay {
        delay
    } else {
        current
    }
}

/// # Safety
/// Deadline is aligned/writable; failure leaves it unchanged. No pointers retained.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_timer_delay_deadline(
    now: i64,
    previous: i64,
    delay: i64,
    deadline: *mut i64,
) -> i32 {
    let base = if now < 0 { previous } else { now };
    let Some(value) = base.checked_add(delay).filter(|value| *value >= 0) else {
        return 0;
    };
    if deadline.is_null() {
        return 0;
    }
    // SAFETY: non-null (checked above), aligned, writable output.
    unsafe { deadline.write(value) };
    1
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn native_modes_and_armed_timeout_are_independent_of_queue_state() {
        assert_eq!(swr_v1_timer_backend(1, 1), 0);
        assert_eq!(swr_v1_timer_backend(1, 0), 0);
        assert_eq!(swr_v1_timer_backend(0, 1), 1);
        assert_eq!(swr_v1_timer_backend(0, 0), 2);
        for current in [-1, 0, 1, 999, i64::MAX] {
            for delay in [1, 2, 999, i64::MAX] {
                assert_eq!(
                    swr_v1_timer_rearm_after_add(current, delay),
                    if current < 0 {
                        delay
                    } else {
                        current.min(delay)
                    }
                );
            }
        }
    }

    #[test]
    fn split_keeps_signed_native_remainders_and_disarm() {
        for value in [i64::MIN, -BILLION - 1, -1, 0, 1, BILLION + 1, i64::MAX] {
            let split = swr_v1_timer_realtime_split(value);
            assert_eq!(
                i128::from(split.seconds) * i128::from(BILLION) + i128::from(split.fraction),
                i128::from(value)
            );
            assert!(split.fraction.abs() < BILLION);
            let interval = swr_v1_timer_system_interval(value);
            if value <= 0 {
                assert_eq!(
                    interval,
                    NativeTime {
                        seconds: 0,
                        fraction: 0
                    }
                );
            } else {
                assert_eq!(interval.seconds * 1000 + interval.fraction / 1000, value);
                assert!((0..1_000_000).contains(&interval.fraction));
            }
        }
    }

    #[test]
    fn negative_timed_lock_addition_does_not_floor_normalize() {
        assert_eq!(
            swr_v1_timer_realtime_add(10, 100, -1),
            NativeTime {
                seconds: 10,
                fraction: -999_900
            }
        );
        assert_eq!(
            swr_v1_timer_realtime_add(10, 100, -1001),
            NativeTime {
                seconds: 9,
                fraction: -999_900
            }
        );
        assert_eq!(
            swr_v1_timer_realtime_add(10, 999_999_999, 1),
            NativeTime {
                seconds: 11,
                fraction: 999_999
            }
        );
        assert_eq!(
            swr_v1_timer_realtime_add(10, 1_999_999_999, 1),
            NativeTime {
                seconds: 12,
                fraction: 999_999
            }
        );
    }

    #[test]
    fn realtime_add_preserves_native_int_carry_narrowing() {
        for (fraction, expected_seconds) in [
            (4_294_967_295_000_000_000, 9),
            (4_294_967_296_000_000_000, 10),
            (4_294_967_297_000_000_000, 11),
        ] {
            assert_eq!(
                swr_v1_timer_realtime_add(10, fraction, 0),
                NativeTime {
                    seconds: expected_seconds,
                    fraction: 4_294_967_296_000_000_000
                }
            );
        }
    }

    #[test]
    fn delay_checks_limits_before_writing_and_keeps_native_clock_fallback() {
        let mut result = 77;
        unsafe {
            assert_eq!(swr_v1_timer_delay_deadline(-1, 20, -5, &mut result), 1);
            assert_eq!(result, 15);
            for (now, old, delay) in [(i64::MAX, 0, 1), (-1, i64::MIN, -1), (0, 0, -1)] {
                result = 77;
                assert_eq!(swr_v1_timer_delay_deadline(now, old, delay, &mut result), 0);
                assert_eq!(result, 77);
            }
            assert_eq!(
                swr_v1_timer_delay_deadline(10, 0, 5, std::ptr::null_mut()),
                0
            );
        }
    }
}
