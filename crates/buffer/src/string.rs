//! Owned String planning and byte mutation. Frozen planning APIs allocate nothing.
//! Only the additive system edit calls libc; custom/Zend allocation remains native.
use super::{INVALID, NOMEM, OK, OVERFLOW};
#[cfg(test)]
use std::mem::MaybeUninit;
use std::ptr;

pub const RESERVE: u32 = 0;
pub const APPEND: u32 = 1;
pub const WRITE: u32 = 2;
pub const REPEAT: u32 = 3;
pub const REDUCE: u32 = 4;
pub const POP: u32 = 5;
pub const DROP: u32 = 6;
pub const TERMINATE: u32 = 7;
pub const COPY: u32 = 8;
pub const APPEND_I32: u32 = 9;
const NO_SOURCE: usize = usize::MAX;

#[repr(C)]
#[derive(Clone, Copy)]
pub struct StringState {
    pub data: *mut u8,
    pub length: usize,
    pub capacity: usize,
    pub offset: i64,
}
#[repr(C)]
pub struct StringEdit {
    pub operation: u32,
    pub data: *const u8,
    pub length: usize,
    pub count: usize,
    pub offset: i64,
    pub alignment: usize,
    pub page: usize,
}
#[repr(C)]
#[derive(Clone, Copy, PartialEq, Eq)]
pub struct StringPlan {
    pub capacity: usize,
    pub length: usize,
    pub offset: i64,
    pub source_offset: usize,
    /// 0: no allocation, 1: malloc, 2: realloc. Native executes this request.
    pub allocation: u32,
}
impl StringPlan {
    const ZERO: Self = Self {
        capacity: 0,
        length: 0,
        offset: 0,
        source_offset: NO_SOURCE,
        allocation: 0,
    };
}
fn aligned(size: usize, alignment: usize) -> Result<usize, i32> {
    if !alignment.is_power_of_two() {
        return Err(INVALID);
    }
    let size = size.checked_add(alignment - 1).ok_or(OVERFLOW)? & !(alignment - 1);
    if size > isize::MAX as usize {
        Err(OVERFLOW)
    } else {
        Ok(size)
    }
}
impl StringState {
    fn validate(&self) -> Result<(), i32> {
        if self.length > self.capacity
            || self.capacity > isize::MAX as usize
            || (self.capacity != 0 && self.data.is_null())
        {
            return Err(INVALID);
        }
        Ok(())
    }
    fn input_offset(&self, data: *const u8, length: usize) -> Result<usize, i32> {
        if length > isize::MAX as usize {
            return Err(OVERFLOW);
        }
        if length != 0 && data.is_null() {
            return Err(INVALID);
        }
        let (input, base) = (data as usize, self.data as usize);
        if !self.data.is_null() && input >= base && input - base < self.capacity {
            let offset = input - base;
            if length > self.capacity - offset {
                return Err(INVALID);
            }
            Ok(offset)
        } else {
            Ok(NO_SOURCE)
        }
    }
    fn plan(&self, edit: &StringEdit) -> Result<StringPlan, i32> {
        if edit.operation == DROP {
            return Ok(StringPlan::ZERO);
        }
        self.validate()?;
        let mut plan = StringPlan {
            capacity: self.capacity,
            length: self.length,
            offset: self.offset,
            ..StringPlan::ZERO
        };
        if matches!(edit.operation, APPEND | WRITE | REPEAT | COPY) {
            plan.source_offset = self.input_offset(edit.data, edit.length)?;
        }
        match edit.operation {
            RESERVE => {
                plan.capacity = aligned(edit.length, edit.alignment)?;
                if plan.capacity < self.length {
                    return Err(INVALID);
                }
                plan.allocation = if self.data.is_null() || plan.capacity == 0 {
                    1
                } else {
                    2
                };
            }
            COPY => {
                // count is source capacity; page is the direct same-object fact.
                // Copy targets are initialized empty before native allocation.
                if !self.data.is_null()
                    || self.capacity != 0
                    || edit.page > 1
                    || edit.length > edit.count
                {
                    return Err(INVALID);
                }
                plan.capacity = aligned(edit.count, edit.alignment)?;
                plan.length = if edit.page == 0 { edit.length } else { 0 };
                plan.offset = if edit.page == 0 { edit.offset } else { 0 };
                plan.allocation = 1;
            }
            TERMINATE => {
                // count1 marks a borrowed writable span: only in-place NUL is legal.
                if edit.count > 1 || (edit.count == 1 && self.length == self.capacity) {
                    return Err(INVALID);
                }
                if self.length == self.capacity {
                    plan.capacity =
                        aligned(self.length.checked_add(1).ok_or(OVERFLOW)?, edit.alignment)?;
                    plan.allocation = if self.data.is_null() { 1 } else { 2 };
                }
            }
            APPEND | WRITE | REPEAT | APPEND_I32 => {
                let at = if edit.operation == WRITE {
                    usize::try_from(edit.offset).map_err(|_| INVALID)?
                } else {
                    self.length
                };
                let added = if edit.operation == REPEAT {
                    if edit.count == 0 {
                        return Err(INVALID);
                    }
                    edit.length.checked_mul(edit.count).ok_or(OVERFLOW)?
                } else if edit.operation == APPEND_I32 {
                    let value = i32::try_from(edit.offset).map_err(|_| INVALID)?;
                    itoa::Buffer::new().format(value).len()
                } else {
                    edit.length
                };
                let end = at.checked_add(added).ok_or(OVERFLOW)?;
                if end > isize::MAX as usize {
                    return Err(OVERFLOW);
                }
                plan.length = self.length.max(end);
                if end > self.capacity {
                    let capacity = if edit.operation == WRITE {
                        aligned(end.checked_mul(2).ok_or(OVERFLOW)?, edit.page)?
                    } else {
                        end
                    };
                    plan.capacity = aligned(capacity, edit.alignment)?;
                    plan.allocation = if self.data.is_null() { 1 } else { 2 };
                }
            }
            REDUCE => {
                let offset = usize::try_from(edit.offset).map_err(|_| INVALID)?;
                if offset > self.length {
                    return Err(INVALID);
                }
                if offset != 0 {
                    plan.length -= offset;
                    plan.offset = 0;
                }
            }
            POP => {
                let offset = usize::try_from(self.offset).map_err(|_| INVALID)?;
                plan.length = self.length.checked_sub(offset).ok_or(INVALID)?;
                plan.capacity = aligned(edit.length.max(plan.length), edit.alignment)?;
                plan.offset = 0;
                plan.allocation = 1;
            }
            _ => return Err(INVALID),
        }
        Ok(plan)
    }
}

/// Compute a request without allocation, byte mutation, or callbacks.
/// # Safety
/// PODs are valid/aligned/disjoint. Owned storage and input satisfy the local
/// String contract. State/edit remain unchanged until apply; plan is caller-owned.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_string_prepare(
    state: *const StringState,
    edit: *const StringEdit,
    output: *mut StringPlan,
) -> i32 {
    if output.is_null() {
        return INVALID;
    }
    let result = if state.is_null() || edit.is_null() {
        Err(INVALID)
    } else {
        unsafe { (&*state).plan(&*edit) }
    };
    match result {
        Ok(plan) => {
            unsafe { output.write(plan) };
            OK
        }
        Err(status) => {
            unsafe { output.write(StringPlan::ZERO) };
            status
        }
    }
}

/// Apply a validated request after native allocation succeeds.
/// # Safety
/// PODs, output and storage are disjoint/valid. Plan/state/edit match prepare.
/// Replacement is the requested allocation (with matching allocator provenance),
/// or the unchanged old pointer for allocation 0. A successful realloc may have
/// invalidated old data; apply reads only its metadata and rebases interior input.
/// Output transfers detached malloc/pop/drop storage, never realloc's old owner.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_string_apply(
    state: *mut StringState,
    edit: *const StringEdit,
    plan: *const StringPlan,
    replacement: *mut u8,
    detached: *mut *mut u8,
) -> i32 {
    if detached.is_null() {
        return INVALID;
    }
    unsafe {
        detached.write(ptr::null_mut());
    }
    if state.is_null() || edit.is_null() || plan.is_null() {
        return INVALID;
    }
    let (state, edit, plan) = unsafe { (&mut *state, &*edit, &*plan) };
    // Revalidation reads metadata only, including after successful native realloc.
    if !matches!(state.plan(edit), Ok(expected) if expected == *plan) {
        return INVALID;
    }
    unsafe { apply_plan(state, edit, plan, replacement, detached) }
}

unsafe fn apply_plan(
    state: &mut StringState,
    edit: &StringEdit,
    plan: &StringPlan,
    replacement: *mut u8,
    detached: *mut *mut u8,
) -> i32 {
    if plan.allocation != 0 && replacement.is_null() {
        return INVALID;
    }
    if plan.allocation == 0 && edit.operation != DROP && replacement != state.data {
        return INVALID;
    }
    let data = if plan.allocation == 0 {
        state.data
    } else {
        replacement
    };
    let source = if plan.source_offset == NO_SOURCE {
        edit.data
    } else {
        unsafe { data.add(plan.source_offset) }
    };
    unsafe {
        match edit.operation {
            APPEND | WRITE => {
                if edit.length != 0 {
                    let at = if edit.operation == WRITE {
                        edit.offset as usize
                    } else {
                        state.length
                    };
                    ptr::copy(source, data.add(at), edit.length);
                }
            }
            APPEND_I32 => {
                let mut buffer = itoa::Buffer::new();
                let text = buffer.format(edit.offset as i32);
                ptr::copy_nonoverlapping(text.as_ptr(), data.add(state.length), text.len());
            }
            COPY => {
                if plan.length != 0 {
                    ptr::copy_nonoverlapping(source, data, plan.length);
                }
            }
            TERMINATE => data.add(state.length).write(0),
            REPEAT => {
                let added = plan.length - state.length;
                if added != 0 {
                    let destination = data.add(state.length);
                    if edit.length == 1 {
                        ptr::write_bytes(destination, *source, added);
                    } else {
                        ptr::copy(source, destination, edit.length);
                        let mut filled = edit.length;
                        while filled < added {
                            let copied = filled.min(added - filled);
                            ptr::copy_nonoverlapping(destination, destination.add(filled), copied);
                            filled += copied;
                        }
                    }
                }
            }
            REDUCE => {
                if edit.offset != 0 && plan.length != 0 {
                    ptr::copy(data.add(edit.offset as usize), data, plan.length);
                }
            }
            POP if plan.length != 0 => {
                ptr::copy_nonoverlapping(state.data.add(state.offset as usize), data, plan.length);
            }
            _ => {}
        }
        if edit.operation == DROP || (plan.allocation == 1 && !state.data.is_null()) {
            detached.write(state.data);
        }
    }
    *state = StringState {
        data: if edit.operation == DROP {
            ptr::null_mut()
        } else {
            data
        },
        length: plan.length,
        capacity: plan.capacity,
        offset: plan.offset,
    };
    OK
}

/// Execute an edit immediately if no allocation is needed; otherwise return 1
/// with a plan and no mutation. Existing prepare/apply remain compatible.
/// # Safety
/// Same POD/input and ownership requirements as prepare/apply. Outputs are valid,
/// aligned and disjoint; no callbacks or allocation run during this function.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_string_edit_in_place(
    state: *mut StringState,
    edit: *const StringEdit,
    output: *mut StringPlan,
    detached: *mut *mut u8,
) -> i32 {
    if !detached.is_null() {
        unsafe {
            detached.write(ptr::null_mut());
        }
    }
    if state.is_null() || edit.is_null() || output.is_null() || detached.is_null() {
        if !output.is_null() {
            unsafe { output.write(StringPlan::ZERO) };
        }
        return INVALID;
    }
    let (state, edit) = unsafe { (&mut *state, &*edit) };
    let plan = match state.plan(edit) {
        Ok(plan) => plan,
        Err(status) => {
            unsafe { output.write(StringPlan::ZERO) };
            return status;
        }
    };
    unsafe { output.write(plan) };
    if plan.allocation != 0 {
        return 1;
    }
    unsafe { apply_plan(state, edit, &plan, state.data, detached) }
}

/// Execute an edit on uniquely owned standard-libc storage in one call.
/// # Safety
/// PODs, output and input satisfy prepare/apply disjointness and ownership rules.
/// Native must verify all four allocator function pointers against the actual C
/// malloc/calloc/realloc/free symbols on every call. No custom/Zend callback or
/// foreign exception/bailout may execute through these standard C symbols.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_string_edit_system(
    state: *mut StringState,
    edit: *const StringEdit,
    detached: *mut *mut u8,
) -> i32 {
    unsafe extern "C" {
        fn malloc(size: usize) -> *mut std::ffi::c_void;
        fn realloc(pointer: *mut std::ffi::c_void, size: usize) -> *mut std::ffi::c_void;
    }
    if detached.is_null() {
        return INVALID;
    }
    unsafe { detached.write(ptr::null_mut()) };
    if state.is_null() || edit.is_null() {
        return INVALID;
    }
    // These references borrow only disjoint POD metadata, never the allocation.
    let (state, edit) = unsafe { (&mut *state, &*edit) };
    let plan = match state.plan(edit) {
        Ok(plan) => plan,
        Err(status) => return status,
    };
    let replacement = match plan.allocation {
        1 => unsafe { malloc(plan.capacity).cast::<u8>() },
        2 => unsafe { realloc(state.data.cast(), plan.capacity).cast::<u8>() },
        _ => state.data,
    };
    if plan.allocation != 0 && replacement.is_null() {
        return NOMEM;
    }
    // No slice/borrow of old storage survived realloc. The private plan cannot
    // be changed by a caller between planning and apply; frozen apply still
    // independently validates external plans. Interior input is rebased here.
    unsafe { apply_plan(state, edit, &plan, replacement, detached) }
}

/// Append directly into existing capacity without a storage snapshot or plan.
/// Returns 1 (unchanged) if native allocation through the general edit is needed.
/// # Safety
/// Data/input are valid byte ranges, and length is aligned, writable, and disjoint
/// from both. Internal byte aliases are allowed; ownership remains with caller.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_string_append_in_place(
    data: *mut u8,
    length: *mut usize,
    capacity: usize,
    input: *const u8,
    count: usize,
) -> i32 {
    if length.is_null() {
        return INVALID;
    }
    let used = unsafe { *length };
    let state = StringState {
        data,
        length: used,
        capacity,
        offset: 0,
    };
    if let Err(status) = state
        .validate()
        .and_then(|()| state.input_offset(input, count).map(|_| ()))
    {
        return status;
    }
    let Some(end) = used
        .checked_add(count)
        .filter(|&end| end <= isize::MAX as usize)
    else {
        return OVERFLOW;
    };
    if end > capacity {
        return 1;
    }
    unsafe {
        if count != 0 {
            ptr::copy(input, data.add(used), count);
        }
        length.write(end);
    }
    OK
}

mod compatibility;
pub use compatibility::*;
mod random;
pub use random::*;
mod formatting;
pub use formatting::*;
mod allocation;
pub use allocation::*;
mod ownership;
pub use ownership::{StringOwnershipPlan, swr_v1_string_ownership_plan};
mod policy;
mod scan;
pub use policy::{
    StringFormatPlan, StringRandomPlan, StringTransition, swr_v1_string_capacity,
    swr_v1_string_format_plan, swr_v1_string_grow, swr_v1_string_random_plan,
    swr_v1_string_transition,
};
pub use scan::{
    StringSplitCursor, StringSplitPlan, StringSplitStep, swr_v1_string_match, swr_v1_string_range,
    swr_v1_string_split_next, swr_v1_string_split_plan,
};

/// Format an i32 without allocation, including a trailing NUL; return byte count.
/// Null output returns zero without mutation. All valid numbers use 1..=11 bytes.
/// # Safety
/// Non-null output must be writable for twelve bytes. No borrow escapes.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_string_format_i32(value: i32, output: *mut u8) -> usize {
    if output.is_null() {
        return 0;
    }
    let mut buffer = itoa::Buffer::new();
    let text = buffer.format(value);
    unsafe {
        ptr::copy_nonoverlapping(text.as_ptr(), output, text.len());
        output.add(text.len()).write(0);
    }
    text.len()
}

/// Format and append a decimal i32 without allocation. Existing append statuses:
/// zero succeeds, one requests native allocation with all bytes/length unchanged.
/// # Safety
/// Existing append pointer, ownership and disjointness rules apply.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_string_append_i32(
    data: *mut u8,
    length: *mut usize,
    capacity: usize,
    value: i32,
) -> i32 {
    let mut buffer = itoa::Buffer::new();
    let text = buffer.format(value);
    unsafe { swr_v1_string_append_in_place(data, length, capacity, text.as_ptr(), text.len()) }
}

#[cfg(test)]
mod number_tests {
    use super::*;
    #[test]
    fn integer_edit_preserves_capacity_offset_and_failure_prefix() {
        for value in [i32::MIN, -123456789, -1, 0, 1, i32::MAX] {
            let expected = value.to_string();
            for used in [0, 2, 11, 16, 31, 32] {
                let mut bytes = [b'x'; 64];
                let mut state = StringState {
                    data: bytes.as_mut_ptr(),
                    length: used,
                    capacity: 32,
                    offset: 1,
                };
                let edit = StringEdit {
                    operation: APPEND_I32,
                    data: ptr::null(),
                    length: 0,
                    count: 0,
                    offset: value as i64,
                    alignment: 8,
                    page: 4096,
                };
                let plan = state.plan(&edit).unwrap();
                let end = used + expected.len();
                assert_eq!(plan.length, end);
                assert_eq!(plan.capacity, if end > 32 { (end + 7) & !7 } else { 32 });
                assert_eq!(plan.offset, 1);
                if plan.allocation != 0 {
                    let mut detached = ptr::null_mut();
                    assert_eq!(
                        unsafe {
                            apply_plan(&mut state, &edit, &plan, ptr::null_mut(), &mut detached)
                        },
                        INVALID
                    );
                    assert_eq!((state.length, state.capacity, state.offset), (used, 32, 1));
                    assert_eq!(bytes, [b'x'; 64]);
                } else {
                    let data = state.data;
                    assert_eq!(
                        unsafe { apply_plan(&mut state, &edit, &plan, data, &mut ptr::null_mut()) },
                        OK
                    );
                    assert_eq!(&bytes[used..end], expected.as_bytes());
                    assert!(
                        bytes[..used]
                            .iter()
                            .chain(bytes[end..].iter())
                            .all(|b| *b == b'x')
                    );
                }
            }
        }
        let state = StringState {
            data: ptr::null_mut(),
            length: 0,
            capacity: 0,
            offset: 0,
        };
        let edit = StringEdit {
            operation: APPEND_I32,
            data: ptr::null(),
            length: 0,
            count: 0,
            offset: i32::MAX as i64 + 1,
            alignment: 8,
            page: 4096,
        };
        assert_eq!(state.plan(&edit).map(|_| ()), Err(INVALID));
    }
    #[test]
    fn integer_format_matches_display_without_overwriting_guards() {
        let mut seed = 731u32;
        for value in [i32::MIN, i32::MAX, -1, 0, 1]
            .into_iter()
            .chain((0..65536).map(|_| {
                seed ^= seed << 13;
                seed ^= seed >> 17;
                seed ^= seed << 5;
                seed as i32
            }))
        {
            let expected = value.to_string();
            let mut output = [255u8; 14];
            let length = unsafe { swr_v1_string_format_i32(value, output.as_mut_ptr().add(1)) };
            assert_eq!(&output[1..length + 1], expected.as_bytes());
            assert_eq!(output[length + 1], 0);
            assert_eq!((output[0], output[13]), (255, 255));
            let mut data = [255; 16];
            data[..3].copy_from_slice(b"abc");
            let mut used = 3;
            assert_eq!(
                unsafe { swr_v1_string_append_i32(data.as_mut_ptr(), &mut used, 15, value) },
                OK
            );
            assert_eq!(&data[..3], b"abc");
            assert_eq!(&data[3..used], expected.as_bytes());
            assert_eq!(data[15], 255);
            used = 0;
            assert_eq!(
                unsafe { swr_v1_string_append_i32(ptr::null_mut(), &mut used, 0, value) },
                1
            );
            assert_eq!(used, 0);
        }
        let mut bytes = [255; 12];
        let mut used = 1;
        for (data, length, capacity) in [
            (bytes.as_mut_ptr(), ptr::null_mut(), 12),
            (ptr::null_mut(), &mut used, 12),
            (bytes.as_mut_ptr(), &mut used, 0),
            (bytes.as_mut_ptr(), &mut used, usize::MAX),
        ] {
            assert_eq!(
                unsafe { swr_v1_string_append_i32(data, length, capacity, 0) },
                INVALID
            );
            assert_eq!(used, 1);
            assert_eq!(bytes, [255; 12]);
        }
        assert_eq!(
            unsafe { swr_v1_string_append_i32(bytes.as_mut_ptr(), &mut used, 1, 0) },
            1
        );
        assert_eq!((used, bytes), (1, [255; 12]));
        assert_eq!(unsafe { swr_v1_string_format_i32(0, ptr::null_mut()) }, 0);
    }
}

#[cfg(test)]
mod terminator_tests {
    use super::*;
    #[test]
    fn terminator_preserves_length_offset_and_allocation_prefix() {
        let mut bytes = [91u8; 16];
        let mut state = StringState {
            data: bytes.as_mut_ptr(),
            length: 3,
            capacity: 8,
            offset: 2,
        };
        let edit = StringEdit {
            operation: TERMINATE,
            data: ptr::null(),
            length: 0,
            count: 0,
            offset: 0,
            alignment: 8,
            page: 4096,
        };
        let mut plan = MaybeUninit::uninit();
        let mut detached = ptr::null_mut();
        assert_eq!(
            unsafe {
                swr_v1_string_edit_in_place(&mut state, &edit, plan.as_mut_ptr(), &mut detached)
            },
            OK
        );
        assert_eq!((state.length, state.capacity, state.offset), (3, 8, 2));
        assert_eq!(bytes[3], 0);
        assert_eq!(&bytes[..3], &[91; 3]);
        assert_eq!(&bytes[4..], &[91; 12]);
        state.length = 8;
        let before = bytes;
        assert_eq!(
            unsafe {
                swr_v1_string_edit_in_place(&mut state, &edit, plan.as_mut_ptr(), &mut detached)
            },
            1
        );
        let plan = unsafe { plan.assume_init() };
        assert_eq!(
            (plan.capacity, plan.length, plan.offset, plan.allocation),
            (16, 8, 2, 2)
        );
        assert_eq!(bytes, before);
        let mut replacement = [92u8; 16];
        replacement[..8].copy_from_slice(&bytes[..8]); // Native realloc retains initialized bytes.
        assert_eq!(
            unsafe {
                swr_v1_string_apply(
                    &mut state,
                    &edit,
                    &plan,
                    replacement.as_mut_ptr(),
                    &mut detached,
                )
            },
            OK
        );
        assert_eq!((state.length, state.capacity, state.offset), (8, 16, 2));
        assert_eq!(&replacement[..8], &bytes[..8]);
        assert_eq!(replacement[8], 0);
        assert_eq!(&replacement[9..], &[92; 7]);
        assert!(detached.is_null());
        let mut borrowed = StringState {
            data: bytes.as_mut_ptr(),
            length: 8,
            capacity: 8,
            offset: 1,
        };
        let borrowed_edit = StringEdit { count: 1, ..edit };
        let mut rejected = MaybeUninit::uninit();
        let before = bytes;
        assert_eq!(
            unsafe {
                swr_v1_string_edit_in_place(
                    &mut borrowed,
                    &borrowed_edit,
                    rejected.as_mut_ptr(),
                    &mut detached,
                )
            },
            INVALID
        );
        assert_eq!(bytes, before);
        assert_eq!(
            (borrowed.length, borrowed.capacity, borrowed.offset),
            (8, 8, 1)
        );
        borrowed.length = 2;
        assert_eq!(
            unsafe {
                swr_v1_string_edit_in_place(
                    &mut borrowed,
                    &borrowed_edit,
                    rejected.as_mut_ptr(),
                    &mut detached,
                )
            },
            OK
        );
        assert_eq!(bytes[2], 0);
    }
}

#[cfg(test)]
mod copy_tests {
    use super::*;
    #[test]
    fn copy_edit_plans_capacity_and_metadata_before_exact_byte_publication() {
        let source = *b"a\0bxxxx";
        let edit = StringEdit {
            operation: COPY,
            data: source.as_ptr(),
            length: 3,
            count: 7,
            offset: 2,
            alignment: 8,
            page: 0,
        };
        let mut target = StringState {
            data: ptr::null_mut(),
            length: 0,
            capacity: 0,
            offset: 0,
        };
        let mut plan = StringPlan::ZERO;
        let mut detached = ptr::null_mut();
        let mut allocation = [0xcd; 9];
        unsafe {
            assert_eq!(swr_v1_string_prepare(&target, &edit, &mut plan), OK);
            assert_eq!(
                (plan.capacity, plan.length, plan.offset, plan.allocation),
                (8, 3, 2, 1)
            );
            assert_eq!(
                swr_v1_string_apply(
                    &mut target,
                    &edit,
                    &plan,
                    allocation.as_mut_ptr(),
                    &mut detached
                ),
                OK
            );
        }
        assert_eq!(&allocation[..3], b"a\0b");
        assert_eq!(&allocation[3..], &[0xcd; 6]);
        assert_eq!((target.length, target.capacity, target.offset), (3, 8, 2));
        assert!(detached.is_null());
        // Private direct same-object copy resets before its allocation, as native.
        let same = StringEdit { page: 1, ..edit };
        target = StringState {
            data: ptr::null_mut(),
            length: 0,
            capacity: 0,
            offset: 0,
        };
        unsafe { assert_eq!(swr_v1_string_prepare(&target, &same, &mut plan), OK) };
        assert_eq!((plan.capacity, plan.length, plan.offset), (8, 0, 0));
        let invalid = StringEdit { count: 2, ..edit };
        unsafe { assert_eq!(swr_v1_string_prepare(&target, &invalid, &mut plan), INVALID) };
        assert!(plan == StringPlan::ZERO);
    }
}
