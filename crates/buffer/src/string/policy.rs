//! Pure checked String growth/format/random-storage policy. Native performs IO.
use super::{INVALID, OK, OVERFLOW, StringState, aligned};

const EMPTY_STATE: StringState = StringState {
    data: std::ptr::null_mut(),
    length: 0,
    capacity: 0,
    offset: 0,
};

#[repr(C)]
pub struct StringTransition {
    pub state: StringState,
    pub owner: StringState,
}
impl StringTransition {
    const EMPTY: Self = Self {
        state: EMPTY_STATE,
        owner: EMPTY_STATE,
    };
}

/// Plan take (1) without accessing allocation contents.
/// Public metadata is copied verbatim, including offset and opaque data pointer;
/// this is not a byte-storage validator. Native retains allocator-token custody.
/// # Safety
/// Source/output are valid, aligned and disjoint PODs. No allocator, callback,
/// byte access, retained borrow or allocation occurs. On error output is empty.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_string_transition(
    source: *const StringState,
    operation: u32,
    output: *mut StringTransition,
) -> i32 {
    if output.is_null() {
        return INVALID;
    }
    let mut result = StringTransition::EMPTY;
    let status = if source.is_null() {
        INVALID
    } else {
        // SAFETY: non-null (checked above), valid, aligned POD.
        let source = unsafe { *source };
        match operation {
            1 => {
                result.owner = source;
                OK
            }
            _ => INVALID,
        }
    };
    // SAFETY: `output` is non-null (checked above), aligned, writable and disjoint.
    unsafe { output.write(result) };
    status
}

fn grown(current: usize, minimum: usize, alignment: usize) -> Result<usize, i32> {
    if minimum > isize::MAX as usize {
        return Err(OVERFLOW);
    }
    let mut capacity = aligned(current.checked_mul(2).ok_or(OVERFLOW)?, alignment)?;
    if capacity == 0 && minimum != 0 {
        capacity = alignment;
    }
    while capacity < minimum {
        capacity = capacity
            .checked_mul(2)
            .filter(|&n| n <= isize::MAX as usize)
            .ok_or(OVERFLOW)?;
    }
    Ok(capacity)
}
unsafe fn output<T: Default>(out: *mut T, calculate: impl FnOnce() -> Result<T, i32>) -> i32 {
    if out.is_null() {
        return INVALID;
    }
    // SAFETY: `out` is non-null (checked above), aligned, writable and disjoint.
    unsafe { out.write(T::default()) };
    match calculate() {
        Ok(value) => {
            // SAFETY: as above.
            unsafe { out.write(value) };
            OK
        }
        Err(status) => status,
    }
}

/// # Safety
/// Output is aligned, writable and disjoint. No allocation or callbacks run.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_string_capacity(
    current: usize,
    minimum: usize,
    alignment: usize,
    out: *mut usize,
) -> i32 {
    // SAFETY: forwards the caller's aligned, writable, disjoint output.
    unsafe { output(out, || grown(current, minimum, alignment)) }
}

/// Plan legacy grow metadata, returning 1 when equality requests native reserve.
/// # Safety
/// Both outputs are valid/aligned/disjoint. No byte access or allocation occurs.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_string_grow(
    length: usize,
    capacity: usize,
    increment: usize,
    next: *mut usize,
    reserve: *mut usize,
) -> i32 {
    if !next.is_null() {
        // SAFETY: non-null (checked above), aligned, writable and disjoint.
        unsafe { next.write(0) };
    }
    if !reserve.is_null() {
        // SAFETY: as above.
        unsafe { reserve.write(0) };
    }
    if next.is_null() || reserve.is_null() {
        return INVALID;
    }
    let Some(length) = length
        .checked_add(increment)
        .filter(|&n| n <= isize::MAX as usize)
    else {
        return OVERFLOW;
    };
    let requested = if length == capacity {
        let Some(size) = capacity
            .checked_mul(2)
            .filter(|&n| n <= isize::MAX as usize)
        else {
            return OVERFLOW;
        };
        size
    } else {
        capacity
    };
    // SAFETY: both are non-null (checked above), aligned, writable and disjoint.
    unsafe { next.write(length) };
    // SAFETY: as above.
    unsafe { reserve.write(requested) };
    i32::from(length == capacity)
}

#[repr(C)]
#[derive(Default)]
pub struct StringFormatPlan {
    pub capacity: usize,
    pub offset: usize,
}
pub(super) fn formatting(
    length: usize,
    capacity: usize,
    formatted: usize,
    flags: u32,
    alignment: usize,
) -> Result<StringFormatPlan, i32> {
    if length > capacity {
        return Err(INVALID);
    }
    if formatted == 0 {
        return Ok(StringFormatPlan {
            capacity,
            offset: length,
        });
    }
    let offset = if flags & 1 != 0 { length } else { 0 };
    let needed = formatted
        .checked_add(1)
        .and_then(|n| n.checked_add(offset))
        .filter(|&n| n <= isize::MAX as usize)
        .ok_or(OVERFLOW)?;
    let desired = if flags & 2 != 0 {
        grown(capacity, needed, alignment)?
    } else {
        aligned(needed, alignment)?
    };
    Ok(StringFormatPlan {
        capacity: if needed > capacity { desired } else { capacity },
        offset,
    })
}
/// # Safety
/// Output is valid/aligned/disjoint. Formatting itself remains native.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_string_format_plan(
    length: usize,
    capacity: usize,
    formatted: usize,
    flags: u32,
    alignment: usize,
    out: *mut StringFormatPlan,
) -> i32 {
    // SAFETY: forwards the caller's aligned, writable, disjoint output.
    unsafe {
        output(out, || {
            formatting(length, capacity, formatted, flags, alignment)
        })
    }
}

#[repr(C)]
#[derive(Default)]
pub struct StringRandomPlan {
    pub capacity: usize,
    pub encoded_capacity: usize,
}
pub(super) fn random_storage(
    length: usize,
    capacity: usize,
    count: usize,
    base64: u32,
    alignment: usize,
    page: usize,
) -> Result<StringRandomPlan, i32> {
    if length > capacity || base64 > 1 {
        return Err(INVALID);
    }
    let encoded_capacity = if base64 != 0 {
        count
            .checked_add(2)
            .and_then(|n| (n / 3).checked_mul(4))
            .and_then(|n| n.checked_add(1))
            .ok_or(OVERFLOW)?
    } else {
        0
    };
    let needed = length
        .checked_add(count)
        .and_then(|n| n.checked_add(encoded_capacity))
        .filter(|&n| n <= isize::MAX as usize)
        .ok_or(OVERFLOW)?;
    let capacity = if needed > capacity {
        aligned(
            aligned(needed.checked_mul(2).ok_or(OVERFLOW)?, page)?,
            alignment,
        )?
    } else {
        capacity
    };
    Ok(StringRandomPlan {
        capacity,
        encoded_capacity,
    })
}
/// # Safety
/// Output is valid/aligned/disjoint. Entropy and encoding are invoked natively.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_string_random_plan(
    length: usize,
    capacity: usize,
    count: usize,
    base64: u32,
    alignment: usize,
    page: usize,
    out: *mut StringRandomPlan,
) -> i32 {
    // SAFETY: forwards the caller's aligned, writable, disjoint output.
    unsafe {
        output(out, || {
            random_storage(length, capacity, count, base64, alignment, page)
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn metadata_transfers_opaque_custody_without_touching_bytes() {
        fn fields(state: StringState) -> (*mut u8, usize, usize, i64) {
            (state.data, state.length, state.capacity, state.offset)
        }
        let mut bytes = [91u8; 64];
        for capacity in [0, 1, 7, 8, 33, 64] {
            for length in [0, capacity / 2, capacity] {
                for offset in [-1, 0, i64::try_from(length).unwrap()] {
                    let source = StringState {
                        data: bytes.as_mut_ptr(),
                        length,
                        capacity,
                        offset,
                    };
                    let original = fields(source);
                    let mut result = StringTransition::EMPTY;
                    assert_eq!(
                        unsafe { swr_v1_string_transition(&raw const source, 1, &raw mut result) },
                        OK
                    );
                    assert_eq!(fields(result.state), fields(EMPTY_STATE));
                    assert_eq!(fields(result.owner), original);
                    assert_eq!(fields(source), original);
                    assert_eq!(bytes, [91; 64]);
                }
            }
        }
        let mut result = StringTransition {
            state: EMPTY_STATE,
            owner: EMPTY_STATE,
        };
        assert_eq!(
            unsafe { swr_v1_string_transition(&EMPTY_STATE, 0, &raw mut result) },
            INVALID
        );
        assert_eq!(fields(result.owner), fields(EMPTY_STATE));
        assert_eq!(
            unsafe { swr_v1_string_transition(std::ptr::null(), 1, &raw mut result) },
            INVALID
        );
        assert_eq!(
            unsafe { swr_v1_string_transition(&EMPTY_STATE, 1, std::ptr::null_mut()) },
            INVALID
        );
    }

    #[test]
    fn growth_matches_bounded_native_doubling_model() {
        for current in [0, 1, 8, 15, 16, 127, 4096] {
            for minimum in 0..8192 {
                let mut expected = (current * 2 + 7) & !7;
                if expected == 0 && minimum != 0 {
                    expected = 8;
                }
                while expected < minimum {
                    expected *= 2;
                }
                assert_eq!(grown(current, minimum, 8), Ok(expected));
            }
        }
        assert_eq!(grown(usize::MAX, 1, 8), Err(OVERFLOW));
    }
    #[test]
    fn formatting_and_random_reservation_preserve_capacity_rules() {
        let format = formatting(10, 16, 9, 1, 8).unwrap();
        assert_eq!((format.capacity, format.offset), (24, 10));
        let format = formatting(10, 16, 9, 3, 8).unwrap();
        assert_eq!((format.capacity, format.offset), (32, 10));
        for count in 0..100 {
            let random = random_storage(7, 8, count, 1, 8, 4096).unwrap();
            assert_eq!(random.encoded_capacity, count.div_ceil(3) * 4 + 1);
            assert_eq!(random.capacity, if count == 0 { 8 } else { 4096 });
        }
        assert_eq!(formatting(0, 8, usize::MAX, 0, 8).err(), Some(OVERFLOW));
        assert_eq!(
            random_storage(0, 8, usize::MAX, 1, 8, 4096).err(),
            Some(OVERFLOW)
        );
    }
}
