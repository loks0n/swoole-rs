//! Public String continuation. Only transient copied facts cross Native effects;
//! the Native object's fields remain authoritative, and publication is masked.
use super::*;
const LENGTH: u32 = 1;
const OFFSET: u32 = 2;
const DATA: u32 = 4;
const CAPACITY: u32 = 8;
const CONTINUE: u32 = 4;
#[repr(C)]
#[derive(Clone, Copy, Default)]
pub struct StringCompatCursor {
    pub old: *mut u8,
    pub old_capacity: usize,
    pub captured_length: usize,
    pub requested: usize,
    pub end: usize,
    pub iteration: usize,
    pub source_offset: usize,
    pub input_internal: u32,
    pub phase: u32,
    pub digits_length: u32,
    pub digits: [u8; 12],
}
#[repr(C)]
#[derive(Clone, Copy)]
pub struct StringCompatStep {
    pub state: StringState,
    pub result: *mut u8,
    pub requested: usize,
    /// 0 done, 1 Native reserve, 2 Native initial alloc, 3 Native malloc, 4 resume.
    pub action: u32,
    /// length=1, offset=2, data=4, capacity=8; all other live fields are untouched.
    pub mask: u32,
}
fn output(state: StringState) -> StringCompatStep {
    StringCompatStep {
        state,
        result: ptr::null_mut(),
        requested: 0,
        action: 0,
        mask: 0,
    }
}
fn amount(
    edit: &StringEdit,
    cursor: &StringCompatCursor,
    source: &StringState,
    source_object: bool,
) -> usize {
    if source_object {
        source.length
    } else if edit.operation == APPEND_I32 {
        cursor.digits_length as usize
    } else if edit.operation == REPEAT && edit.length == 1 {
        edit.count
    } else {
        edit.length
    }
}
pub(super) unsafe fn step(
    cursor: &mut StringCompatCursor,
    state: StringState,
    source: StringState,
    edit: &StringEdit,
    source_object: bool,
    replacement: *mut u8,
) -> Result<StringCompatStep, i32> {
    let mut out = output(state);
    if edit.operation == COPY {
        if cursor.phase == 0 {
            // Destination construction storage must never be observed here.
            cursor.phase = 1;
            out.requested = source.capacity;
            out.action = 2;
            return Ok(out);
        }
        if cursor.phase != 1 {
            return Err(INVALID);
        }
        state.validate()?;
        source.validate()?;
        if source.length > state.capacity {
            return Err(INVALID);
        }
        if source.length != 0 {
            // SAFETY: both states validated and `source.length <= state.capacity`; the
            // caller supplies live spans (readable source, writable destination).
            unsafe { ptr::copy(source.data, state.data, source.length) };
        }
        out.state.length = source.length;
        out.state.offset = source.offset;
        out.mask = LENGTH | OFFSET;
        cursor.phase = 3;
        return Ok(out);
    }
    if edit.operation == POP {
        match cursor.phase {
            0 => {
                state.validate()?;
                let offset = usize::try_from(state.offset).map_err(|_| INVALID)?;
                cursor.captured_length = state.length.checked_sub(offset).ok_or(INVALID)?;
                cursor.old = state.data;
                cursor.old_capacity = state.capacity;
                cursor.requested =
                    aligned(edit.length.max(cursor.captured_length), edit.alignment)?;
                cursor.phase = 1;
                out.requested = cursor.requested;
                out.action = 3;
            }
            1 => {
                if replacement.is_null() {
                    cursor.phase = 3;
                    return Ok(out);
                }
                // Preserve the original publication prefix before byte copy.
                out.state.data = replacement;
                out.state.capacity = cursor.requested;
                out.state.length = cursor.captured_length;
                out.mask = DATA | CAPACITY | LENGTH;
                out.action = CONTINUE;
                cursor.phase = 2;
            }
            2 => {
                let offset = usize::try_from(state.offset).map_err(|_| INVALID)?;
                if offset > cursor.old_capacity
                    || cursor.captured_length > cursor.old_capacity - offset
                    || cursor.captured_length > state.capacity
                {
                    return Err(INVALID);
                }
                if cursor.captured_length != 0 {
                    if cursor.old.is_null() || state.data.is_null() {
                        return Err(INVALID);
                    }
                    // SAFETY: both non-null (checked above); `offset + captured_length` lies in
                    // the captured old span, which the caller keeps live, and `captured_length`
                    // fits the new capacity.
                    unsafe {
                        ptr::copy(
                            cursor.old.wrapping_add(offset),
                            state.data,
                            cursor.captured_length,
                        )
                    };
                }
                out.state.offset = 0;
                out.mask = OFFSET;
                out.result = cursor.old;
                cursor.phase = 3;
            }
            _ => return Err(INVALID),
        }
        return Ok(out);
    }
    state.validate()?;
    if source_object {
        source.validate()?;
    }
    if !matches!(
        edit.operation,
        APPEND | WRITE | APPEND_I32 | REPEAT | TERMINATE
    ) {
        return Err(INVALID);
    }
    if cursor.phase == 0 {
        if cursor.iteration == 0
            && matches!(edit.operation, APPEND | WRITE | REPEAT)
            && !source_object
        {
            let offset = state.input_offset(edit.data, edit.length)?;
            cursor.input_internal = u32::from(offset != NO_SOURCE);
            cursor.source_offset = offset;
        }
        if edit.operation == REPEAT && cursor.iteration >= edit.count {
            return Ok(out);
        }
        if edit.operation == APPEND_I32 {
            let value = i32::try_from(edit.offset).map_err(|_| INVALID)?;
            let mut text = itoa::Buffer::new();
            let text = text.format(value).as_bytes();
            cursor.digits[..text.len()].copy_from_slice(text);
            cursor.digits_length = text.len() as u32;
        }
        let count = amount(edit, cursor, &source, source_object);
        let at = if edit.operation == WRITE {
            usize::try_from(edit.offset).map_err(|_| INVALID)?
        } else {
            state.length
        };
        cursor.end = at.checked_add(count).ok_or(OVERFLOW)?;
        if cursor.end > isize::MAX as usize {
            return Err(OVERFLOW);
        }
        let requested = if edit.operation == TERMINATE {
            if state.length == state.capacity {
                if edit.count == 1 {
                    return Err(INVALID);
                } // Existing borrowed-span admission.
                Some(state.length.checked_add(1).ok_or(OVERFLOW)?)
            } else {
                None
            }
        } else if cursor.end > state.capacity {
            Some(if edit.operation == WRITE {
                aligned(cursor.end.checked_mul(2).ok_or(OVERFLOW)?, edit.page)?
            } else {
                cursor.end
            })
        } else {
            None
        };
        cursor.phase = 1;
        out.action = CONTINUE;
        if let Some(requested) = requested {
            out.requested = aligned(requested, edit.alignment)?;
            out.action = 1;
            return Ok(out);
        }
        // No Native effect: finish the existing operation locally, without
        // re-entering our exported raw ABI or adding a roundtrip for fit edits.
        // SAFETY: forwards this step's own byte-span contract unchanged.
        return unsafe { step(cursor, state, source, edit, source_object, replacement) };
    }
    if cursor.phase != 1 {
        return Err(INVALID);
    }
    if edit.operation == TERMINATE {
        if state.length >= state.capacity || state.data.is_null() {
            return Err(INVALID);
        }
        // SAFETY: non-null and `length < capacity` (checked above), inside writable storage.
        unsafe { state.data.wrapping_add(state.length).write(0) };
        cursor.phase = 3;
        return Ok(out);
    }
    let count = amount(edit, cursor, &source, source_object);
    let at = if edit.operation == WRITE {
        usize::try_from(edit.offset).map_err(|_| INVALID)?
    } else {
        state.length
    };
    let end = at.checked_add(count).ok_or(OVERFLOW)?;
    if end > state.capacity {
        return Err(INVALID);
    }
    if count != 0 {
        let data = if source_object {
            source.data.cast_const()
        } else if edit.operation == APPEND_I32 {
            cursor.digits.as_ptr()
        } else if cursor.input_internal != 0 {
            if cursor.source_offset > state.capacity
                || edit.length > state.capacity - cursor.source_offset
            {
                return Err(INVALID);
            }
            // In range: `source_offset + edit.length <= capacity` (checked above).
            state.data.wrapping_add(cursor.source_offset).cast_const()
        } else {
            edit.data
        };
        if data.is_null() || state.data.is_null() {
            return Err(INVALID);
        }
        // Both non-null (checked above); `at + count <= capacity` inside writable storage,
        // and the input span is live and readable for `count` bytes.
        if edit.operation == REPEAT && edit.length == 1 {
            // SAFETY: as above.
            let byte = unsafe { *data };
            // SAFETY: as above.
            unsafe { ptr::write_bytes(state.data.wrapping_add(at), byte, count) };
        } else {
            // SAFETY: as above; `ptr::copy` allows the internal alias.
            unsafe { ptr::copy(data, state.data.wrapping_add(at), count) };
        }
    }
    // Original WRITE publishes length only when its captured end extends the
    // freshly observed length; an unchanged value is not a publication phase.
    if edit.operation == WRITE {
        if cursor.end > state.length {
            out.state.length = cursor.end;
            out.mask = LENGTH;
        }
    } else {
        out.state.length = end;
        out.mask = LENGTH;
    }
    if edit.operation == REPEAT && edit.length != 1 {
        cursor.iteration += 1;
        cursor.phase = 0;
        out.action = CONTINUE;
    } else {
        cursor.phase = 3;
    }
    Ok(out)
}
/// One copied phase. No allocator/callback, Rust borrow across return, persistent
/// owner or object-layout access. Native executes actions and publishes mask.
/// # Safety
/// All PODs are initialized, aligned and disjoint; outputs writable. For byte
/// phases the freshly supplied storage/input spans are live, initialized for
/// reads, writable for writes and satisfy the original public operation domain.
/// COPY phase0 uses synthetic initialized destination facts. POP copy additionally
/// requires the captured old span still live. It is not runtime-qualified here.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_string_compat_step(
    cursor: *mut StringCompatCursor,
    state: *const StringState,
    source: *const StringState,
    edit: *const StringEdit,
    source_object: u32,
    replacement: *mut u8,
    result: *mut StringCompatStep,
) -> i32 {
    if cursor.is_null()
        || state.is_null()
        || source.is_null()
        || edit.is_null()
        || result.is_null()
        || source_object > 1
    {
        return INVALID;
    }
    // All five are non-null (checked above), initialized, aligned and disjoint PODs.
    // SAFETY: as above.
    let cursor = unsafe { &mut *cursor };
    // SAFETY: as above.
    let state = unsafe { *state };
    // SAFETY: as above.
    let source = unsafe { *source };
    // SAFETY: as above.
    let edit = unsafe { &*edit };
    // SAFETY: the caller supplies live byte spans per this export's contract.
    let value = unsafe { step(cursor, state, source, edit, source_object == 1, replacement) };
    match value {
        Ok(value) => {
            // SAFETY: as above.
            unsafe { result.write(value) };
            OK
        }
        Err(status) => status,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn state(bytes: &mut [u8; 64], length: usize, capacity: usize) -> StringState {
        StringState {
            data: bytes.as_mut_ptr(),
            length,
            capacity,
            offset: 0,
        }
    }
    fn edit(operation: u32, bytes: &[u8], count: usize, offset: i64) -> StringEdit {
        StringEdit {
            operation,
            data: bytes.as_ptr(),
            length: bytes.len(),
            count,
            offset,
            alignment: 8,
            page: 8,
        }
    }
    fn empty() -> StringState {
        StringState {
            data: ptr::null_mut(),
            length: 0,
            capacity: 0,
            offset: 0,
        }
    }
    fn phase(
        c: &mut StringCompatCursor,
        s: StringState,
        source: StringState,
        e: &StringEdit,
        from: bool,
    ) -> StringCompatStep {
        unsafe { step(c, s, source, e, from, ptr::null_mut()).unwrap() }
    }
    #[test]
    fn c_layout_on_supported_lp64_host() {
        assert_eq!(
            (
                std::mem::size_of::<StringCompatCursor>(),
                std::mem::align_of::<StringCompatCursor>()
            ),
            (80, 8)
        );
        assert_eq!(std::mem::offset_of!(StringCompatCursor, digits), 68);
        assert_eq!(std::mem::size_of::<StringCompatStep>(), 56);
        assert_eq!(std::mem::offset_of!(StringCompatStep, mask), 52);
    }
    #[test]
    fn append_resumes_with_fresh_initialized_metadata() {
        let mut bytes = [0u8; 64];
        bytes[..4].copy_from_slice(b"abcd");
        let mut s = state(&mut bytes, 2, 4);
        let e = edit(APPEND, b"XYZ", 0, 0);
        let mut c = StringCompatCursor::default();
        let first = phase(&mut c, s, empty(), &e, false);
        assert_eq!((first.action, first.requested, first.mask), (1, 8, 0));
        // Scripted scalar stores only: no actual allocation or callback.
        s.capacity = 8;
        s.length = 1;
        s.offset = 1;
        let done = phase(&mut c, s, empty(), &e, false);
        assert_eq!(
            (done.state.length, done.state.offset, done.mask, done.action),
            (4, 1, LENGTH, 0)
        );
        assert_eq!(&bytes[..4], b"aXYZ");
    }
    #[test]
    fn write_preserves_fresh_length_beyond_captured_end() {
        let mut bytes = [0u8; 64];
        let mut s = state(&mut bytes, 2, 4);
        let e = edit(WRITE, b"XYZ", 0, 3);
        let mut c = StringCompatCursor::default();
        let first = phase(&mut c, s, empty(), &e, false);
        assert_eq!(first.requested, 16);
        s.capacity = 16;
        s.length = 10;
        s.offset = 2;
        let done = phase(&mut c, s, empty(), &e, false);
        assert_eq!(
            (done.state.length, done.state.offset, done.mask),
            (10, 2, 0)
        );
        assert_eq!(&bytes[3..6], b"XYZ");
    }
    #[test]
    fn repeat_retains_each_original_growth_request() {
        let mut bytes = [0u8; 64];
        let mut s = state(&mut bytes, 0, 8);
        let e = edit(REPEAT, b"abcdefghijklmnopq", 3, 0);
        let mut c = StringCompatCursor::default();
        let mut requests = [0usize; 3];
        let mut used = 0;
        loop {
            let next = phase(&mut c, s, empty(), &e, false);
            if next.mask & LENGTH != 0 {
                s.length = next.state.length;
            }
            if next.action == 1 {
                requests[used] = next.requested;
                used += 1;
                s.capacity = next.requested;
            }
            if next.action == 0 {
                break;
            }
        }
        assert_eq!(requests, [24, 40, 56]);
        assert_eq!(used, 3);
        assert_eq!(s.length, 51);
        for part in bytes[..51].as_chunks::<17>().0 {
            assert_eq!(part, b"abcdefghijklmnopq");
        }
    }
    #[test]
    fn copy_initial_phase_uses_only_source_then_fresh_source() {
        let mut source = [0u8; 64];
        source[..3].copy_from_slice(b"abc");
        let mut from = state(&mut source, 2, 8);
        let mut target = [0u8; 64];
        let e = edit(COPY, b"", 0, 0);
        let mut c = StringCompatCursor::default();
        let first = phase(&mut c, empty(), from, &e, false);
        assert_eq!((first.action, first.requested, first.mask), (2, 8, 0));
        from.length = 3;
        from.offset = 1;
        let done = phase(&mut c, state(&mut target, 0, 8), from, &e, false);
        assert_eq!(
            (done.state.length, done.state.offset, done.mask),
            (3, 1, LENGTH | OFFSET)
        );
        assert_eq!(&target[..3], b"abc");
    }
    #[test]
    fn integer_and_terminator_sample_live_fields_after_reserve() {
        let mut bytes = [0u8; 64];
        let mut s = state(&mut bytes, 2, 4);
        let e = edit(APPEND_I32, b"", 0, 12345);
        let mut c = StringCompatCursor::default();
        assert_eq!(phase(&mut c, s, empty(), &e, false).requested, 8);
        s.length = 1;
        s.capacity = 8;
        s.offset = 1;
        let done = phase(&mut c, s, empty(), &e, false);
        assert_eq!(done.state.length, 6);
        assert_eq!(&bytes[1..6], b"12345");
        let e = edit(TERMINATE, b"", 0, 0);
        let mut c = StringCompatCursor::default();
        s.length = 2;
        s.capacity = 2;
        assert_eq!(phase(&mut c, s, empty(), &e, false).requested, 8);
        s.length = 3;
        s.capacity = 8;
        bytes[3] = 99;
        let done = phase(&mut c, s, empty(), &e, false);
        assert_eq!(done.mask, 0);
        assert_eq!(done.state.offset, 1);
        assert_eq!(bytes[3], 0);
    }
    #[test]
    fn pop_scalar_capture_and_early_publication_only() {
        // Symbolic tokens: phases0/1 never dereference these. Copy phase is NOT run.
        let s = StringState {
            data: ptr::without_provenance_mut(4096),
            length: 7,
            capacity: 16,
            offset: 2,
        };
        let e = edit(POP, b"", 0, 0);
        let mut e = e;
        e.length = 8;
        let mut c = StringCompatCursor::default();
        let first = phase(&mut c, s, empty(), &e, false);
        assert_eq!((first.action, first.requested), (3, 8));
        assert_eq!((c.old, c.captured_length), (s.data, 5));
        let mut live = s;
        live.offset = 3;
        let early = unsafe {
            step(
                &mut c,
                live,
                empty(),
                &e,
                false,
                ptr::without_provenance_mut(8192),
            )
            .unwrap()
        };
        assert_eq!(
            (
                early.state.data as usize,
                early.state.length,
                early.state.capacity,
                early.state.offset
            ),
            (8192, 5, 8, 3)
        );
        assert_eq!(
            (early.mask, early.action),
            (DATA | CAPACITY | LENGTH, CONTINUE)
        );
    }
    #[test]
    fn append_object_source_is_reobserved_after_reserve() {
        let mut bytes = [0u8; 64];
        let mut source = [0u8; 64];
        source[..3].copy_from_slice(b"XYZ");
        let mut s = state(&mut bytes, 3, 4);
        let mut from = state(&mut source, 2, 8);
        let e = edit(APPEND, b"", 0, 0);
        let mut c = StringCompatCursor::default();
        assert_eq!(phase(&mut c, s, from, &e, true).requested, 8);
        s.capacity = 8;
        s.length = 1;
        from.length = 3;
        let done = phase(&mut c, s, from, &e, true);
        assert_eq!(done.state.length, 4);
        assert_eq!(&bytes[1..4], b"XYZ");
    }
}
