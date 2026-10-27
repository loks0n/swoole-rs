//! Whole public String operations in one call. Native passes the `swoole::String`
//! itself; Rust calls its allocator directly and edits its fields in the original
//! order. Fields are re-read after every allocator call, because the allocator may
//! change either String, and no reference to a String outlives an allocator call.
use super::*;
use std::ffi::c_void;

/// Layout of `swoole::Allocator`.
#[repr(C)]
pub struct StringAllocator {
    pub malloc: Option<unsafe extern "C" fn(usize) -> *mut c_void>,
    pub calloc: Option<unsafe extern "C" fn(usize, usize) -> *mut c_void>,
    pub realloc: Option<unsafe extern "C" fn(*mut c_void, usize) -> *mut c_void>,
    pub free: Option<unsafe extern "C" fn(*mut c_void)>,
}

/// Layout of `swoole::String`.
#[repr(C)]
#[derive(Clone, Copy)]
pub struct StringObject {
    pub length: usize,
    pub capacity: usize,
    pub offset: i64,
    pub data: *mut u8,
    pub allocator: *const StringAllocator,
}

impl StringObject {
    fn state(&self) -> StringState {
        StringState {
            data: self.data,
            length: self.length,
            capacity: self.capacity,
            offset: self.offset,
        }
    }
}

/// The String's fields now.
unsafe fn read(object: *const StringObject) -> StringObject {
    // SAFETY: the caller passes a live String.
    unsafe { object.read() }
}

/// Edit the String's fields through a reference that ends before any allocator call.
unsafe fn update(object: *mut StringObject, edit: impl FnOnce(&mut StringObject)) {
    // SAFETY: the caller passes a live String that nothing else touches meanwhile.
    edit(unsafe { &mut *object });
}

unsafe fn malloc(allocator: *const StringAllocator, size: usize) -> Result<*mut u8, i32> {
    // SAFETY: the caller passes a live allocator.
    let function = unsafe { allocator.as_ref() }
        .and_then(|a| a.malloc)
        .ok_or(INVALID)?;
    // SAFETY: calling the String's own allocator.
    Ok(unsafe { function(size) }.cast())
}

/// `allocate_string(INITIAL)`: publishes empty fields, then the pointer and
/// allocator, then reports a null pointer.
unsafe fn allocate(
    object: *mut StringObject,
    capacity: usize,
    allocator: *const StringAllocator,
) -> Result<(), i32> {
    // SAFETY: live String.
    unsafe {
        update(object, |o| {
            o.length = 0;
            o.capacity = capacity;
            o.offset = 0;
        });
    };
    // SAFETY: `allocator` is live.
    let data = unsafe { malloc(allocator, capacity) }?;
    // SAFETY: live String.
    unsafe {
        update(object, |o| {
            o.data = data;
            o.allocator = allocator;
        });
    };
    if data.is_null() { Err(NOMEM) } else { Ok(()) }
}

/// `String::reserve`: initial allocation from `initial` for empty storage,
/// otherwise realloc, publishing pointer and capacity only on success.
unsafe fn reserve(
    object: *mut StringObject,
    requested: usize,
    alignment: usize,
    initial: *const StringAllocator,
) -> Result<(), i32> {
    let capacity = aligned(requested, alignment)?;
    // SAFETY: live String.
    let s = unsafe { read(object) };
    s.state().validate()?;
    if capacity < s.length {
        return Err(INVALID);
    }
    if s.capacity == 0 {
        // SAFETY: `initial` is a live allocator.
        return unsafe { allocate(object, capacity, initial) };
    }
    // SAFETY: the String's allocator is live and owns `data`.
    let realloc = unsafe { s.allocator.as_ref() }
        .and_then(|a| a.realloc)
        .ok_or(INVALID)?;
    // SAFETY: as above.
    let replacement: *mut u8 = unsafe { realloc(s.data.cast(), capacity) }.cast();
    if replacement.is_null() {
        return Err(NOMEM);
    }
    // SAFETY: live String.
    unsafe {
        update(object, |o| {
            o.data = replacement;
            o.capacity = capacity;
        });
    };
    Ok(())
}

/// The copy constructor: allocate from `initial`, then copy the source as it is
/// after the allocation.
unsafe fn copy(
    object: *mut StringObject,
    source: *const StringObject,
    alignment: usize,
    initial: *const StringAllocator,
) -> Result<*mut u8, i32> {
    // SAFETY: live source String.
    let capacity = aligned(unsafe { read(source) }.capacity, alignment)?;
    // SAFETY: `initial` is the source's allocator or the standard one.
    unsafe { allocate(object, capacity, initial) }?;
    // SAFETY: live source String.
    let from = unsafe { read(source) };
    from.state().validate()?;
    // SAFETY: live String.
    let to = unsafe { read(object) };
    if from.length > to.capacity {
        return Err(INVALID);
    }
    if from.length != 0 {
        // SAFETY: the source span is readable, the new storage holds `capacity >= length` bytes.
        unsafe { ptr::copy(from.data, to.data, from.length) };
    }
    // SAFETY: live String.
    unsafe {
        update(object, |o| {
            o.length = from.length;
            o.offset = from.offset;
        });
    };
    Ok(ptr::null_mut())
}

/// Detach the unread bytes into new storage and return the old storage, or null
/// without changes when the allocator fails.
unsafe fn pop(object: *mut StringObject, edit: &StringEdit) -> Result<*mut u8, i32> {
    // SAFETY: live String.
    let s = unsafe { read(object) };
    s.state().validate()?;
    let offset = usize::try_from(s.offset).map_err(|_| INVALID)?;
    let captured = s.length.checked_sub(offset).ok_or(INVALID)?;
    let requested = aligned(edit.length.max(captured), edit.alignment)?;
    // SAFETY: the String's allocator is live.
    let replacement = unsafe { malloc(s.allocator, requested) }?;
    if replacement.is_null() {
        return Ok(ptr::null_mut());
    }
    // SAFETY: live String.
    unsafe {
        update(object, |o| {
            o.data = replacement;
            o.capacity = requested;
            o.length = captured;
        });
    };
    // The original copies from the offset as it is after malloc.
    // SAFETY: live String.
    let offset = usize::try_from(unsafe { read(object) }.offset).map_err(|_| INVALID)?;
    if offset
        .checked_add(captured)
        .is_none_or(|end| end > s.capacity)
    {
        return Err(INVALID);
    }
    if captured != 0 {
        // SAFETY: `offset + captured <= old capacity`, and `captured <= requested`.
        unsafe { ptr::copy(s.data.wrapping_add(offset), replacement, captured) };
    }
    // SAFETY: live String.
    unsafe { update(object, |o| o.offset = 0) };
    Ok(s.data)
}

/// APPEND, WRITE, APPEND_I32, REPEAT and TERMINATE: reserve if needed, then write
/// at the String's fields as they are after the reserve.
unsafe fn write(
    object: *mut StringObject,
    source: *const StringObject,
    edit: &StringEdit,
    initial: *const StringAllocator,
) -> Result<(), i32> {
    // SAFETY: live String.
    let start = unsafe { read(object) };
    start.state().validate()?;
    let mut digits = itoa::Buffer::new();
    // Byte input, unless it comes from a source String (read fresh each time).
    // Input inside the String's own storage is kept as an offset, because a
    // reserve may move the storage.
    let (bytes, internal) = match edit.operation {
        TERMINATE => ((ptr::null(), 0), None),
        _ if !source.is_null() => ((ptr::null(), 0), None),
        APPEND_I32 => {
            let text = digits
                .format(i32::try_from(edit.offset).map_err(|_| INVALID)?)
                .as_bytes();
            ((text.as_ptr(), text.len()), None)
        }
        _ => {
            let offset = start.state().input_offset(edit.data, edit.length)?;
            let count = if edit.operation == REPEAT && edit.length == 1 {
                edit.count
            } else {
                edit.length
            };
            ((edit.data, count), (offset != NO_SOURCE).then_some(offset))
        }
    };
    let input = || -> Result<(*const u8, usize), i32> {
        if source.is_null() || edit.operation == TERMINATE {
            return Ok(bytes);
        }
        // SAFETY: live source String.
        let from = unsafe { read(source) };
        from.state().validate()?;
        Ok((from.data.cast_const(), from.length))
    };
    let at = |s: &StringObject| {
        if edit.operation == WRITE {
            usize::try_from(edit.offset).map_err(|_| INVALID)
        } else {
            Ok(s.length)
        }
    };
    let repeats = if edit.operation == REPEAT && edit.length != 1 {
        edit.count
    } else {
        1
    };
    for _ in 0..repeats {
        // SAFETY: live String.
        let s = unsafe { read(object) };
        s.state().validate()?;
        let end = at(&s)?
            .checked_add(input()?.1)
            .filter(|&end| isize::try_from(end).is_ok())
            .ok_or(OVERFLOW)?;
        let requested = if edit.operation == TERMINATE {
            if s.length != s.capacity {
                None
            } else if edit.count == 1 {
                return Err(INVALID); // A borrowed span cannot grow.
            } else {
                Some(s.length.checked_add(1).ok_or(OVERFLOW)?)
            }
        } else if end > s.capacity {
            Some(if edit.operation == WRITE {
                aligned(end.checked_mul(2).ok_or(OVERFLOW)?, edit.page)?
            } else {
                end
            })
        } else {
            None
        };
        if let Some(requested) = requested {
            // SAFETY: the String's storage and the allocators are live.
            unsafe { reserve(object, requested, edit.alignment, initial) }?;
        }
        // SAFETY: live String.
        let s = unsafe { read(object) };
        s.state().validate()?;
        if edit.operation == TERMINATE {
            if s.length >= s.capacity || s.data.is_null() {
                return Err(INVALID);
            }
            // SAFETY: `length < capacity` inside writable storage.
            unsafe { s.data.wrapping_add(s.length).write(0) };
            return Ok(());
        }
        let (data, count) = input()?;
        let at = at(&s)?;
        let end = at.checked_add(count).ok_or(OVERFLOW)?;
        if end > s.capacity {
            return Err(INVALID);
        }
        if count != 0 {
            let data = match internal {
                Some(offset) if offset > s.capacity || edit.length > s.capacity - offset => {
                    return Err(INVALID);
                }
                Some(offset) => s.data.wrapping_add(offset).cast_const(),
                None => data,
            };
            if data.is_null() || s.data.is_null() {
                return Err(INVALID);
            }
            if edit.operation == REPEAT && edit.length == 1 {
                // SAFETY: one readable input byte.
                let byte = unsafe { *data };
                // SAFETY: `at + count <= capacity` is writable.
                unsafe { ptr::write_bytes(s.data.wrapping_add(at), byte, count) };
            } else {
                // SAFETY: `count` readable input bytes; `at + count <= capacity` is writable;
                // `ptr::copy` allows the input to alias the String's storage.
                unsafe { ptr::copy(data, s.data.wrapping_add(at), count) };
            }
        }
        // WRITE only ever extends the length.
        if edit.operation != WRITE || end > s.length {
            // SAFETY: live String.
            unsafe { update(object, |o| o.length = end) };
        }
    }
    Ok(())
}

/// One public String operation on `object`, a live `swoole::String` (only written
/// for COPY). `source` is null or a String (required for COPY, else appended).
/// First allocations use `initial`: the source's allocator for COPY, else the
/// standard one. Returns POP's old storage through `result`, else null.
/// # Safety
/// The Strings and allocators are live, `edit` follows the public operation's
/// contract and `result` is writable.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_string_edit_object(
    object: *mut StringObject,
    source: *const StringObject,
    edit: *const StringEdit,
    initial: *const StringAllocator,
    result: *mut *mut u8,
) -> i32 {
    if object.is_null() || edit.is_null() || initial.is_null() || result.is_null() {
        return INVALID;
    }
    // SAFETY: non-null (checked above) and valid per the contract.
    let edit = unsafe { &*edit };
    let outcome = match edit.operation {
        COPY if source.is_null() => Err(INVALID),
        // SAFETY: the contract makes every pointer live.
        COPY => unsafe { copy(object, source, edit.alignment, initial) },
        // SAFETY: as above.
        POP => unsafe { pop(object, edit) },
        APPEND | WRITE | APPEND_I32 | REPEAT | TERMINATE => {
            // SAFETY: as above.
            unsafe { write(object, source, edit, initial) }.map(|()| ptr::null_mut())
        }
        _ => Err(INVALID),
    };
    let (status, old) = match outcome {
        Ok(old) => (OK, old),
        Err(status) => (status, ptr::null_mut()),
    };
    // SAFETY: writable per the contract.
    unsafe { result.write(old) };
    status
}

#[cfg(all(test, unix))]
mod tests {
    use super::*;
    use std::cell::RefCell;

    thread_local!(static SIZES: RefCell<Vec<usize>> = const { RefCell::new(Vec::new()) });
    unsafe extern "C" fn record_malloc(size: usize) -> *mut c_void {
        SIZES.with(|s| s.borrow_mut().push(size));
        // SAFETY: plain libc allocation.
        unsafe { libc::malloc(size) }
    }
    unsafe extern "C" fn record_realloc(data: *mut c_void, size: usize) -> *mut c_void {
        SIZES.with(|s| s.borrow_mut().push(size));
        // SAFETY: `data` came from this allocator.
        unsafe { libc::realloc(data, size) }
    }
    unsafe extern "C" fn fail_malloc(_: usize) -> *mut c_void {
        ptr::null_mut()
    }
    unsafe extern "C" fn fail_realloc(_: *mut c_void, _: usize) -> *mut c_void {
        ptr::null_mut()
    }
    static SYSTEM: StringAllocator = StringAllocator {
        malloc: Some(record_malloc),
        calloc: None,
        realloc: Some(record_realloc),
        free: None,
    };
    static FAILING: StringAllocator = StringAllocator {
        malloc: Some(fail_malloc),
        calloc: None,
        realloc: Some(fail_realloc),
        free: None,
    };

    fn string(bytes: &[u8], capacity: usize) -> StringObject {
        // SAFETY: test allocation, freed by `bytes_of`.
        let data: *mut u8 = unsafe { libc::malloc(capacity) }.cast();
        // SAFETY: `capacity >= bytes.len()`.
        unsafe { ptr::copy(bytes.as_ptr(), data, bytes.len()) };
        StringObject {
            data,
            length: bytes.len(),
            capacity,
            offset: 0,
            allocator: &raw const SYSTEM,
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
    fn run(
        object: &mut StringObject,
        source: Option<&StringObject>,
        edit: &StringEdit,
    ) -> (i32, *mut u8) {
        SIZES.with(|s| s.borrow_mut().clear());
        let mut result = ptr::null_mut();
        let source = source.map_or(ptr::null(), std::ptr::from_ref);
        // SAFETY: live test objects.
        (
            unsafe {
                swr_v1_string_edit_object(object, source, edit, &raw const SYSTEM, &raw mut result)
            },
            result,
        )
    }
    fn sizes() -> Vec<usize> {
        SIZES.with(|s| s.borrow().clone())
    }
    fn bytes(object: &StringObject) -> Vec<u8> {
        // SAFETY: `length` initialized bytes.
        unsafe { std::slice::from_raw_parts(object.data, object.length) }.to_vec()
    }

    #[test]
    fn append_reallocates_and_keeps_offset() {
        let mut s = string(b"ab", 4);
        s.offset = 1;
        assert_eq!(run(&mut s, None, &edit(APPEND, b"XYZ", 0, 0)).0, OK);
        assert_eq!(
            (bytes(&s), s.capacity, s.offset, sizes()),
            (b"abXYZ".to_vec(), 8, 1, vec![8])
        );
    }
    #[test]
    fn append_from_own_storage_survives_realloc() {
        let mut s = string(b"abcd", 4);
        let e = StringEdit {
            data: s.data,
            length: 4,
            ..edit(APPEND, b"", 0, 0)
        };
        assert_eq!(run(&mut s, None, &e).0, OK);
        assert_eq!(bytes(&s), b"abcdabcd");
    }
    #[test]
    fn write_doubles_to_page_and_only_extends_length() {
        let mut s = string(b"ab", 4);
        assert_eq!(run(&mut s, None, &edit(WRITE, b"XYZ", 0, 3)).0, OK);
        assert_eq!((s.length, s.capacity), (6, 16));
        // SAFETY: inside capacity.
        assert_eq!(
            unsafe { std::slice::from_raw_parts(s.data.add(3), 3) },
            b"XYZ"
        );
        assert_eq!(run(&mut s, None, &edit(WRITE, b"Q", 0, 0)).0, OK);
        assert_eq!(bytes(&s)[..2], *b"Qb");
        assert_eq!(s.length, 6);
    }
    #[test]
    fn repeat_keeps_each_original_growth_request() {
        let mut s = string(b"", 8);
        assert_eq!(
            run(&mut s, None, &edit(REPEAT, b"abcdefghijklmnopq", 3, 0)).0,
            OK
        );
        assert_eq!((s.length, sizes()), (51, vec![24, 40, 56]));
        assert_eq!(bytes(&s), b"abcdefghijklmnopq".repeat(3));
        let mut s = string(b"", 8);
        assert_eq!(run(&mut s, None, &edit(REPEAT, b"Z", 17, 0)).0, OK);
        assert_eq!((bytes(&s), s.capacity), (vec![b'Z'; 17], 24));
    }
    #[test]
    fn copy_allocates_from_initial_and_takes_source_fields() {
        let mut source = string(b"abc", 8);
        source.offset = 1;
        let mut s = StringObject {
            data: ptr::null_mut(),
            length: 0,
            capacity: 0,
            offset: 0,
            allocator: ptr::null(),
        };
        assert_eq!(run(&mut s, Some(&source), &edit(COPY, b"", 0, 0)).0, OK);
        assert_eq!(
            (bytes(&s), s.offset, s.capacity, sizes()),
            (b"abc".to_vec(), 1, 8, vec![8])
        );
        assert!(ptr::eq(s.allocator, &raw const SYSTEM));
    }
    #[test]
    fn integer_and_terminator() {
        let mut s = string(b"ab", 4);
        assert_eq!(run(&mut s, None, &edit(APPEND_I32, b"", 0, -12345)).0, OK);
        assert_eq!((bytes(&s), s.capacity), (b"ab-12345".to_vec(), 8));
        assert_eq!(run(&mut s, None, &edit(TERMINATE, b"", 0, 0)).0, OK);
        // SAFETY: the terminator sits inside capacity.
        assert_eq!((s.capacity, unsafe { *s.data.add(8) }), (16, 0));
        s.capacity = s.length;
        assert_eq!(run(&mut s, None, &edit(TERMINATE, b"", 1, 0)).0, INVALID);
    }
    #[test]
    fn empty_storage_takes_the_initial_allocator() {
        let mut s = StringObject {
            data: ptr::null_mut(),
            length: 0,
            capacity: 0,
            offset: 0,
            allocator: &raw const FAILING,
        };
        assert_eq!(run(&mut s, None, &edit(APPEND, b"abc", 0, 0)).0, OK);
        assert!(ptr::eq(s.allocator, &raw const SYSTEM));
        assert_eq!(bytes(&s), b"abc");
    }
    #[test]
    fn pop_detaches_unread_bytes() {
        let mut s = string(b"abcdefg", 16);
        s.offset = 2;
        let old = s.data;
        let (status, result) = run(
            &mut s,
            None,
            &StringEdit {
                length: 8,
                ..edit(POP, b"", 0, 0)
            },
        );
        assert_eq!(
            (status, result, bytes(&s), s.capacity, s.offset),
            (OK, old, b"cdefg".to_vec(), 8, 0)
        );
        s.allocator = &raw const FAILING;
        let before = s.data;
        assert_eq!(
            run(&mut s, None, &edit(POP, b"", 0, 0)),
            (OK, ptr::null_mut())
        );
        assert_eq!(s.data, before);
    }
    #[test]
    fn failed_realloc_changes_nothing() {
        let mut s = string(b"abcd", 4);
        s.allocator = &raw const FAILING;
        assert_eq!(run(&mut s, None, &edit(APPEND, b"e", 0, 0)).0, NOMEM);
        assert_eq!((bytes(&s), s.capacity), (b"abcd".to_vec(), 4));
    }
}
