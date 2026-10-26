//! Variadic formatting continuation. Native printf/reserve effects run after
//! each step; fresh scalar observations determine the next destination/commit.
use super::{INVALID, OK, OVERFLOW, policy};

#[repr(C)]
#[derive(Clone, Copy, Default)]
pub struct StringFormatStep {
    pub capacity: usize,
    pub offset: usize,
    pub available: usize,
    pub length: usize,
    pub result: usize,
    /// Done=0, native reserve=1, native rendering printf=2, publish length=3.
    pub action: u32,
    pub next: u32,
}

fn write(length: usize, capacity: usize, flags: u32) -> Result<StringFormatStep, i32> {
    if length > capacity || capacity > isize::MAX as usize {
        return Err(INVALID);
    }
    let offset = if flags & 1 != 0 { length } else { 0 };
    Ok(StringFormatStep {
        capacity,
        offset,
        available: capacity - offset,
        action: 2,
        next: 2,
        ..Default::default()
    })
}

/// Phase0 consumes sizing printf; phase1 consumes successful reserve; phase2
/// consumes rendering printf. Empty sizing returns immediately without touching
/// storage/metadata. Native retains all variadic arguments, pointers and effects.
/// # Safety
/// Output is aligned/writable/disjoint. No allocation, pointer access, callback,
/// formatting or retained state occurs in Rust. On error output is empty.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_string_format_step(
    phase: u32,
    length: usize,
    capacity: usize,
    formatted: usize,
    rendered: usize,
    flags: u32,
    alignment: usize,
    output: *mut StringFormatStep,
) -> i32 {
    if output.is_null() {
        return INVALID;
    }
    let calculate = || match phase {
        0 if formatted == 0 => Ok(StringFormatStep::default()),
        0 => {
            let plan = policy::formatting(length, capacity, formatted, flags, alignment)?;
            if plan.capacity != capacity {
                Ok(StringFormatStep {
                    capacity: plan.capacity,
                    action: 1,
                    next: 1,
                    ..Default::default()
                })
            } else {
                write(length, capacity, flags)
            }
        }
        1 => write(length, capacity, flags),
        2 => {
            let next_length = if flags & 1 != 0 {
                length.checked_add(rendered).ok_or(OVERFLOW)?
            } else {
                rendered
            };
            if next_length > isize::MAX as usize {
                return Err(OVERFLOW);
            }
            if next_length > capacity {
                return Err(INVALID);
            }
            Ok(StringFormatStep {
                length: next_length,
                result: rendered,
                action: 3,
                ..Default::default()
            })
        }
        _ => Err(INVALID),
    };
    let (status, result) = match calculate() {
        Ok(result) => (OK, result),
        Err(status) => (status, StringFormatStep::default()),
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
        formatted: usize,
        rendered: usize,
        flags: u32,
    ) -> StringFormatStep {
        let mut out = StringFormatStep::default();
        assert_eq!(
            unsafe {
                swr_v1_string_format_step(
                    phase, length, capacity, formatted, rendered, flags, 8, &mut out,
                )
            },
            OK
        );
        out
    }
    #[test]
    fn entire_flag_capacity_workflow_matches_independent_native_policy() {
        for flags in 0..4 {
            for capacity in [8, 16, 32, 64] {
                for length in [0, 1, 7] {
                    for formatted in [1, 3, 8, 17, 65] {
                        let mut s = step(0, length, capacity, formatted, 0, flags);
                        let start = if flags & 1 != 0 { length } else { 0 };
                        let needed = start + formatted + 1;
                        let expected = if needed > capacity {
                            if flags & 2 != 0 {
                                let mut n = (capacity * 2 + 7) & !7;
                                while n < needed {
                                    n *= 2;
                                }
                                n
                            } else {
                                (needed + 7) & !7
                            }
                        } else {
                            capacity
                        };
                        if expected != capacity {
                            assert_eq!((s.action, s.next, s.capacity), (1, 1, expected));
                            s = step(s.next, length, s.capacity, formatted, 0, flags);
                        }
                        assert_eq!(
                            (s.action, s.next, s.offset, s.available),
                            (2, 2, start, expected - start)
                        );
                        s = step(s.next, length, expected, formatted, formatted, flags);
                        assert_eq!(
                            (s.action, s.length, s.result),
                            (3, start + formatted, formatted)
                        );
                    }
                }
            }
        }
    }
    #[test]
    fn effects_are_reobserved_and_empty_sizing_does_not_publish() {
        let empty = step(0, 99, 1, 0, 0, 1);
        assert_eq!((empty.action, empty.length, empty.result), (0, 0, 0));
        let request = step(0, 7, 8, 8, 0, 1);
        assert_eq!(request.action, 1);
        let render = step(request.next, 2, 24, 8, 0, 1);
        assert_eq!((render.offset, render.available), (2, 22));
        let commit = step(render.next, 3, 24, 8, 8, 1);
        assert_eq!((commit.length, commit.result), (11, 8));
        assert_eq!(step(2, 3, 24, 8, 0, 0).length, 0);
    }
    #[test]
    fn invalid_or_unrepresentable_results_refuse_before_publication() {
        let mut out = StringFormatStep {
            action: 99,
            ..Default::default()
        };
        for (phase, length, capacity, formatted, rendered) in [
            (9, 0, 8, 1, 0),
            (0, 9, 8, 1, 0),
            (1, 9, 8, 1, 0),
            (2, 8, 8, 1, 1),
            (2, usize::MAX, usize::MAX, 1, 1),
            (0, 0, 8, usize::MAX, 0),
        ] {
            assert!(
                unsafe {
                    swr_v1_string_format_step(
                        phase, length, capacity, formatted, rendered, 1, 8, &mut out,
                    )
                } < 0
            );
            assert_eq!(
                (out.action, out.capacity, out.length, out.result),
                (0, 0, 0, 0)
            );
        }
        assert_eq!(
            unsafe { swr_v1_string_format_step(0, 0, 8, 1, 0, 0, 8, std::ptr::null_mut()) },
            INVALID
        );
    }
}
