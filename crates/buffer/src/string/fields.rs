//! Designated cells of an actual, independently layout-qualified Native String.
//! This schema is never a Rust-owned value or a reference to a foreign object.
//! Cursors are operation-local; Native primitive effects run only after return.
use super::*;
use std::ffi::{c_char, c_void};

#[repr(C)]
pub struct NativeAllocator {
    _opaque: [u8; 0],
}
#[repr(C)]
struct Cells {
    length: usize,
    size: usize,
    offset: libc::off_t,
    data: *mut c_char,
    allocator: *const NativeAllocator,
}
const INIT: u32 = 0;
const ALLOC: u32 = 1;
const RESERVE_FIELDS: u32 = 2;
const EDIT: u32 = 3;
const MOVE: u32 = 4;
const OWNERSHIP: u32 = 5;
const CLEAR: u32 = 6;
const RELEASE: u32 = 7;
const GROW: u32 = 8;
const REDUCE_FIELDS: u32 = 9;
const BYTES: u32 = 10;
const DEFAULT: u32 = 1;
const MALLOC: u32 = 2;
const REALLOC: u32 = 3;
const FREE: u32 = 4;

#[repr(C)]
#[derive(Default)]
pub struct StringFieldsCursor {
    pub edit: StringCompatCursor,
    pub allocator: *const NativeAllocator,
    pub owner: *mut u8,
    pub requested: usize,
    pub allocation: u32,
    pub phase: u32,
    pub after: u32,
}
#[repr(C)]
#[derive(Default)]
pub struct StringFieldsEffect {
    pub allocator: *const NativeAllocator,
    pub pointer: *mut u8,
    pub requested: usize,
    pub action: u32,
}

// Only these raw projections touch foreign member storage. No whole-record
// load/store/reference, copy, Drop, allocator dereference or integer provenance.
unsafe fn state(p: *const Cells) -> StringState {
    unsafe {
        StringState {
            data: (&raw const (*p).data).read().cast(),
            length: (&raw const (*p).length).read(),
            capacity: (&raw const (*p).size).read(),
            offset: (&raw const (*p).offset).read(),
        }
    }
}
unsafe fn publish(p: *mut Cells, s: StringState, mask: u32) {
    unsafe {
        if mask & 4 != 0 {
            (&raw mut (*p).data).write(s.data.cast());
        }
        if mask & 8 != 0 {
            (&raw mut (*p).size).write(s.capacity);
        }
        if mask & 1 != 0 {
            (&raw mut (*p).length).write(s.length);
        }
        if mask & 2 != 0 {
            (&raw mut (*p).offset).write(s.offset);
        }
    }
}
unsafe fn clear(p: *mut Cells, take: bool) {
    unsafe {
        if take {
            (&raw mut (*p).data).write(ptr::null_mut());
        }
        (&raw mut (*p).length).write(0);
        if take {
            (&raw mut (*p).size).write(0);
        }
        (&raw mut (*p).offset).write(0);
    }
}
unsafe fn move_fields(p: *mut Cells, source: *mut Cells) {
    // Preserve original ordered individual reads/stores; allocator remains on
    // the moved-from object. No whole-record transfer or constructor ownership.
    unsafe {
        (&raw mut (*p).data).write((&raw const (*source).data).read());
        (&raw mut (*p).length).write((&raw const (*source).length).read());
        (&raw mut (*p).offset).write((&raw const (*source).offset).read());
        (&raw mut (*p).size).write((&raw const (*source).size).read());
        (&raw mut (*p).allocator).write((&raw const (*source).allocator).read());
        clear(source, true);
    }
}
fn effect(c: &StringFieldsCursor, action: u32) -> StringFieldsEffect {
    StringFieldsEffect {
        allocator: c.allocator,
        pointer: c.owner,
        requested: c.requested,
        action,
    }
}
unsafe fn initial(
    c: &mut StringFieldsCursor,
    p: *mut Cells,
    alignment: usize,
) -> Result<Option<StringFieldsEffect>, i32> {
    if c.allocator.is_null() {
        c.allocation = 1;
        return Ok(Some(effect(c, DEFAULT)));
    }
    c.requested = aligned(c.requested, alignment)?;
    // Constructor write-only prefix. In particular, no destination pointer or
    // allocator read occurs before malloc and their own initialization.
    unsafe {
        (&raw mut (*p).length).write(0);
        (&raw mut (*p).size).write(c.requested);
        (&raw mut (*p).offset).write(0);
    }
    c.allocation = 2;
    Ok(Some(effect(c, MALLOC)))
}
unsafe fn allocate(
    c: &mut StringFieldsCursor,
    p: *mut Cells,
    requested: usize,
    allocator: *const NativeAllocator,
    initial_alloc: bool,
    alignment: usize,
) -> Result<Option<StringFieldsEffect>, i32> {
    c.requested = requested;
    if initial_alloc || unsafe { (&raw const (*p).size).read() } == 0 {
        c.allocator = allocator;
        unsafe { initial(c, p, alignment) }
    } else {
        c.requested = aligned(requested, alignment)?;
        unsafe {
            c.allocator = (&raw const (*p).allocator).read();
            c.owner = (&raw const (*p).data).read().cast();
        }
        c.allocation = 3;
        Ok(Some(effect(c, REALLOC)))
    }
}
unsafe fn resume_allocation(
    c: &mut StringFieldsCursor,
    p: *mut Cells,
    token: *const NativeAllocator,
    replacement: *mut u8,
    alignment: usize,
) -> Result<Option<StringFieldsEffect>, i32> {
    match c.allocation {
        1 => {
            if token.is_null() {
                return Err(INVALID);
            }
            c.allocator = token;
            unsafe {
                return initial(c, p, alignment);
            }
        }
        2 => unsafe {
            (&raw mut (*p).data).write(replacement.cast());
            (&raw mut (*p).allocator).write(c.allocator);
            if replacement.is_null() {
                return Err(NOMEM);
            }
        },
        3 => {
            if replacement.is_null() {
                return Err(NOMEM);
            }
            unsafe {
                (&raw mut (*p).data).write(replacement.cast());
                (&raw mut (*p).size).write(c.requested);
            }
        }
        _ => return Err(INVALID),
    }
    c.allocation = 0;
    Ok(None)
}

struct Operation<'a> {
    p: *mut Cells,
    source: *const Cells,
    moving: *mut Cells,
    operation: u32,
    argument: usize,
    allocator: *const NativeAllocator,
    edit: &'a StringEdit,
    token: *const NativeAllocator,
    replacement: *mut u8,
}
unsafe fn operation(
    c: &mut StringFieldsCursor,
    input: Operation<'_>,
) -> Result<StringFieldsEffect, i32> {
    let Operation {
        p,
        source,
        moving,
        operation,
        argument,
        allocator,
        edit,
        token,
        replacement,
    } = input;
    let done = StringFieldsEffect::default();
    if c.allocation != 0 {
        if let Some(fx) = unsafe { resume_allocation(c, p, token, replacement, edit.alignment)? } {
            return Ok(fx);
        }
        if c.after == 0 {
            return Ok(done);
        }
    }
    match operation {
        INIT => unsafe {
            (&raw mut (*p).length).write(0);
            (&raw mut (*p).size).write(0);
            (&raw mut (*p).offset).write(0);
            (&raw mut (*p).data).write(ptr::null_mut());
            (&raw mut (*p).allocator).write(ptr::null());
            return Ok(done);
        },
        ALLOC | RESERVE_FIELDS => {
            return unsafe {
                allocate(
                    c,
                    p,
                    argument,
                    allocator,
                    operation == ALLOC,
                    edit.alignment,
                )
            }
            .map(|v| v.unwrap_or(done));
        }
        BYTES => {
            if c.phase == 0 {
                c.phase = 1;
                c.after = 2;
                let requested = edit.length.checked_add(1).ok_or(OVERFLOW)?;
                return unsafe { allocate(c, p, requested, ptr::null(), true, edit.alignment) }
                    .map(|v| v.unwrap_or(done));
            }
            unsafe {
                let data = (&raw const (*p).data).read().cast::<u8>();
                if edit.length != 0 {
                    ptr::copy(edit.data, data, edit.length);
                }
                data.add(edit.length).write(0);
                (&raw mut (*p).length).write(edit.length);
            }
            return Ok(done);
        }
        CLEAR => {
            unsafe {
                clear(p, false);
            }
            return Ok(done);
        }
        RELEASE => unsafe {
            let pointer = (&raw const (*p).data).read().cast();
            clear(p, true);
            return Ok(StringFieldsEffect { pointer, ..done });
        },
        MOVE => {
            if moving.is_null() {
                return Err(INVALID);
            }
            unsafe {
                move_fields(p, moving);
            }
            return Ok(done);
        }
        OWNERSHIP => {
            if argument > 2 {
                return Err(INVALID);
            }
            if c.phase == 0 {
                if argument != 0 && (p.cast_const() == source || p == moving) {
                    return Ok(done);
                }
                c.phase = 1;
                c.allocator = unsafe { (&raw const (*p).allocator).read() };
                // Original short circuit: pointer not read with null allocator.
                if !c.allocator.is_null() {
                    c.owner = unsafe { (&raw const (*p).data).read().cast() };
                    if !c.owner.is_null() {
                        return Ok(effect(c, FREE));
                    }
                }
            }
            if argument == 0 {
                return Ok(done);
            }
            if argument == 2 {
                if moving.is_null() {
                    return Err(INVALID);
                }
                unsafe {
                    move_fields(p, moving);
                }
                return Ok(done);
            }
            // Copy source is freshly read after Native free. The independent
            // const role is preserved, even if other permitted fields changed.
        }
        GROW => {
            if c.phase == 0 {
                let length = unsafe { (&raw const (*p).length).read() }
                    .checked_add(argument)
                    .filter(|&n| n <= isize::MAX as usize)
                    .ok_or(OVERFLOW)?;
                unsafe {
                    (&raw mut (*p).length).write(length);
                }
                let size = unsafe { (&raw const (*p).size).read() };
                if length != size {
                    return Ok(done);
                }
                let requested = size.checked_mul(2).ok_or(OVERFLOW)?;
                c.phase = 1;
                return unsafe { allocate(c, p, requested, ptr::null(), false, edit.alignment) }
                    .map(|v| v.unwrap_or(done));
            }
            return Ok(done);
        }
        REDUCE_FIELDS => unsafe {
            if edit.offset == 0 {
                return Ok(done);
            }
            let count = usize::try_from(edit.offset).map_err(|_| INVALID)?;
            let length = (&raw const (*p).length)
                .read()
                .checked_sub(count)
                .ok_or(INVALID)?;
            (&raw mut (*p).length).write(length);
            (&raw mut (*p).offset).write(0);
            if length != 0 {
                let data = (&raw const (*p).data).read();
                if data.is_null() {
                    return Err(INVALID);
                }
                ptr::copy(data.add(count), data, length);
            }
            return Ok(done);
        },
        EDIT => {}
        _ => return Err(INVALID),
    }
    let copying = edit.operation == COPY || operation == OWNERSHIP;
    if copying && source.is_null() {
        return Err(INVALID);
    }
    let mut copy_edit;
    let edit = if operation == OWNERSHIP {
        copy_edit = StringEdit {
            operation: COPY,
            data: ptr::null(),
            length: 0,
            count: 0,
            offset: 0,
            alignment: edit.alignment,
            page: edit.page,
        };
        &mut copy_edit
    } else {
        edit
    };
    loop {
        let live = if copying && c.edit.phase == 0 {
            StringState {
                data: ptr::null_mut(),
                length: 0,
                capacity: 0,
                offset: 0,
            }
        } else {
            unsafe { state(p) }
        };
        let from = if source.is_null() {
            StringState {
                data: ptr::null_mut(),
                length: 0,
                capacity: 0,
                offset: 0,
            }
        } else {
            unsafe { state(source) }
        };
        let mut local_edit;
        let edit = if edit.operation == TERMINATE {
            local_edit = StringEdit {
                count: u64::from(
                    !live.data.is_null() && unsafe { (&raw const (*p).allocator).read().is_null() },
                ) as usize,
                ..*edit
            };
            &mut local_edit
        } else {
            edit
        };
        let plan = unsafe {
            compatibility::step(
                &mut c.edit,
                live,
                from,
                edit,
                !source.is_null() && !copying,
                replacement,
            )?
        };
        unsafe {
            publish(p, plan.state, plan.mask);
        }
        match plan.action {
            0 => {
                return Ok(StringFieldsEffect {
                    pointer: plan.result,
                    ..done
                });
            }
            1 | 2 => {
                let allocator = if plan.action == 2 {
                    unsafe { (&raw const (*source).allocator).read() }
                } else {
                    ptr::null()
                };
                c.after = 1;
                return unsafe {
                    allocate(
                        c,
                        p,
                        plan.requested,
                        allocator,
                        plan.action == 2,
                        edit.alignment,
                    )
                }
                .map(|v| v.unwrap_or(done));
            }
            3 => {
                c.allocator = unsafe { (&raw const (*p).allocator).read() };
                c.requested = plan.requested;
                return Ok(effect(c, MALLOC));
            }
            4 => {}
            _ => return Err(INVALID),
        }
    }
}

/// # Safety
/// The feature's exact target/schema checks and foreign-member lifetime contract
/// must already hold. `object` is its actual aligned mutable String subobject;
/// source is a const live String, moving is mutable. Only authorized constructor
/// branches accept uninitialized destination cells. Cursor/edit/output are valid
/// independent PODs. Byte storage satisfies the selected operation's contract.
/// No input borrow may survive a returned Native effect; no callback runs here.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_string_fields_step(
    cursor: *mut StringFieldsCursor,
    object: *mut c_void,
    source: *const c_void,
    moving: *mut c_void,
    operation_code: u32,
    argument: usize,
    allocator: *const NativeAllocator,
    edit: *const StringEdit,
    token: *const NativeAllocator,
    replacement: *mut u8,
    output: *mut StringFieldsEffect,
) -> i32 {
    if cursor.is_null() || object.is_null() || edit.is_null() || output.is_null() {
        return INVALID;
    }
    match unsafe {
        operation(
            &mut *cursor,
            Operation {
                p: object.cast(),
                source: source.cast(),
                moving: moving.cast(),
                operation: operation_code,
                argument,
                allocator,
                edit: &*edit,
                token,
                replacement,
            },
        )
    } {
        Ok(result) => {
            unsafe {
                output.write(result);
            }
            OK
        }
        Err(status) => {
            unsafe {
                output.write(StringFieldsEffect::default());
            }
            status
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::mem::{MaybeUninit, align_of, offset_of, size_of};
    fn edit(operation: u32) -> StringEdit {
        StringEdit {
            operation,
            data: ptr::null(),
            length: 0,
            count: 0,
            offset: 0,
            alignment: 8,
            page: 4096,
        }
    }
    // These are initialized Rust scalar/fixed-storage models, never constructed
    // Native objects or actual allocator/callback/free/POP/lifetime effects.
    unsafe fn run(c: &mut StringFieldsCursor, input: Operation<'_>) -> StringFieldsEffect {
        unsafe { operation(c, input).unwrap() }
    }
    fn request<'a>(p: *mut Cells, op: u32, e: &'a StringEdit) -> Operation<'a> {
        Operation {
            p,
            source: ptr::null(),
            moving: ptr::null_mut(),
            operation: op,
            argument: 0,
            allocator: ptr::null(),
            edit: e,
            token: ptr::null(),
            replacement: ptr::null_mut(),
        }
    }
    unsafe fn initialized(
        p: *mut Cells,
        bytes: &mut [u8],
        length: usize,
        token: *const NativeAllocator,
    ) {
        unsafe {
            (&raw mut (*p).data).write(bytes.as_mut_ptr().cast());
            (&raw mut (*p).length).write(length);
            (&raw mut (*p).size).write(bytes.len());
            (&raw mut (*p).offset).write(0);
            (&raw mut (*p).allocator).write(token);
        }
    }
    #[test]
    fn exact_target_schema_and_cursor_are_scalar_layouts() {
        assert_eq!((size_of::<Cells>(), align_of::<Cells>()), (40, 8));
        assert_eq!(
            [
                offset_of!(Cells, length),
                offset_of!(Cells, size),
                offset_of!(Cells, offset),
                offset_of!(Cells, data),
                offset_of!(Cells, allocator)
            ],
            [0, 8, 16, 24, 32]
        );
        assert_eq!(
            (size_of::<libc::off_t>(), align_of::<libc::off_t>()),
            (8, 8)
        );
        const { assert!(libc::off_t::MIN < 0) };
        assert_eq!(
            (
                size_of::<StringFieldsCursor>(),
                size_of::<StringFieldsEffect>()
            ),
            (120, 32)
        );
    }
    #[test]
    fn write_only_constructor_default_then_prefix_then_pointer_token() {
        let mut cells = MaybeUninit::<Cells>::uninit();
        let p = cells.as_mut_ptr();
        let mut cursor = StringFieldsCursor::default();
        let e = edit(0);
        let token_byte = 7u8;
        let token = (&raw const token_byte).cast::<NativeAllocator>();
        let mut bytes = [0u8; 16];
        let mut input = request(p, ALLOC, &e);
        input.argument = 9;
        assert_eq!(unsafe { run(&mut cursor, input) }.action, DEFAULT);
        let mut input = request(p, ALLOC, &e);
        input.token = token;
        let fx = unsafe { run(&mut cursor, input) };
        assert_eq!((fx.action, fx.requested), (MALLOC, 16));
        unsafe {
            assert_eq!((&raw const (*p).length).read(), 0);
            assert_eq!((&raw const (*p).size).read(), 16);
            assert_eq!((&raw const (*p).offset).read(), 0);
        }
        let mut input = request(p, ALLOC, &e);
        input.replacement = bytes.as_mut_ptr();
        assert_eq!(unsafe { run(&mut cursor, input) }.action, 0);
        unsafe {
            assert_eq!(state(p).data, bytes.as_mut_ptr());
            assert_eq!((&raw const (*p).allocator).read(), token);
        }
    }
    #[test]
    fn realloc_publishes_only_pointer_and_capacity_after_external_scalar_changes() {
        let mut cells = MaybeUninit::<Cells>::uninit();
        let p = cells.as_mut_ptr();
        let token_byte = 0u8;
        let token = (&raw const token_byte).cast();
        let mut before = [1u8; 8];
        let mut after = [2u8; 32];
        unsafe {
            initialized(p, &mut before, 3, token);
        }
        let mut c = StringFieldsCursor::default();
        let e = edit(0);
        let mut input = request(p, RESERVE_FIELDS, &e);
        input.argument = 24;
        let fx = unsafe { run(&mut c, input) };
        assert_eq!(
            (fx.action, fx.pointer, fx.requested),
            (REALLOC, before.as_mut_ptr(), 24)
        );
        unsafe {
            (&raw mut (*p).length).write(2);
            (&raw mut (*p).offset).write(1);
        }
        let mut input = request(p, RESERVE_FIELDS, &e);
        input.replacement = after.as_mut_ptr();
        assert_eq!(unsafe { run(&mut c, input) }.action, 0);
        unsafe {
            let s = state(p);
            assert_eq!(
                (s.length, s.offset, s.capacity, s.data),
                (2, 1, 24, after.as_mut_ptr())
            );
        }
    }
    #[test]
    fn append_reobserves_live_fields_after_symbolic_resize() {
        let mut cells = MaybeUninit::<Cells>::uninit();
        let p = cells.as_mut_ptr();
        let token_byte = 0u8;
        let token = (&raw const token_byte).cast();
        let mut before = *b"abcd";
        let mut after = [0u8; 8];
        after[..4].copy_from_slice(&before);
        unsafe {
            initialized(p, &mut before, 2, token);
        }
        let mut c = StringFieldsCursor::default();
        let mut e = edit(APPEND);
        e.data = b"XYZ".as_ptr();
        e.length = 3;
        let fx = unsafe { run(&mut c, request(p, EDIT, &e)) };
        assert_eq!((fx.action, fx.requested), (REALLOC, 8));
        unsafe {
            (&raw mut (*p).length).write(1);
            (&raw mut (*p).offset).write(1);
        }
        let mut input = request(p, EDIT, &e);
        input.replacement = after.as_mut_ptr();
        assert_eq!(unsafe { run(&mut c, input) }.action, 0);
        unsafe {
            assert_eq!((state(p).length, state(p).offset), (4, 1));
        }
        assert_eq!(&after[..4], b"aXYZ");
    }
    #[test]
    fn copy_uses_const_source_with_fresh_post_effect_length_and_offset() {
        let mut dst = MaybeUninit::<Cells>::uninit();
        let p = dst.as_mut_ptr();
        let mut source = MaybeUninit::<Cells>::uninit();
        let from = source.as_mut_ptr();
        let mut bytes = *b"source!!";
        let mut output = [0u8; 8];
        let token_byte = 0u8;
        let token = (&raw const token_byte).cast();
        unsafe {
            initialized(from, &mut bytes, 6, token);
        }
        let mut c = StringFieldsCursor::default();
        let e = edit(COPY);
        let mut input = request(p, EDIT, &e);
        input.source = from;
        assert_eq!(unsafe { run(&mut c, input) }.action, MALLOC);
        unsafe {
            (&raw mut (*from).length).write(3);
            (&raw mut (*from).offset).write(1);
        }
        let mut input = request(p, EDIT, &e);
        input.source = from;
        input.replacement = output.as_mut_ptr();
        assert_eq!(unsafe { run(&mut c, input) }.action, 0);
        assert_eq!(&output[..3], b"sou");
        unsafe {
            assert_eq!((state(p).length, state(p).offset), (3, 1));
        }
    }
    #[test]
    fn byte_constructor_is_one_write_only_operation() {
        let mut dst = MaybeUninit::<Cells>::uninit();
        let p = dst.as_mut_ptr();
        let mut output = [0u8; 8];
        let token_byte = 0u8;
        let token = (&raw const token_byte).cast();
        let mut c = StringFieldsCursor::default();
        let mut e = edit(0);
        e.data = b"hi".as_ptr();
        e.length = 2;
        assert_eq!(
            unsafe { run(&mut c, request(p, BYTES, &e)) }.action,
            DEFAULT
        );
        let mut input = request(p, BYTES, &e);
        input.token = token;
        assert_eq!(unsafe { run(&mut c, input) }.action, MALLOC);
        let mut input = request(p, BYTES, &e);
        input.replacement = output.as_mut_ptr();
        assert_eq!(unsafe { run(&mut c, input) }.action, 0);
        assert_eq!(&output[..3], b"hi\0");
        unsafe {
            assert_eq!(state(p).length, 2);
        }
    }
    #[test]
    fn move_release_clear_and_self_assignment_only_touch_designated_cells() {
        let mut a = MaybeUninit::<Cells>::uninit();
        let p = a.as_mut_ptr();
        let mut b = MaybeUninit::<Cells>::uninit();
        let from = b.as_mut_ptr();
        let mut bytes = [1u8; 16];
        let token_byte = 0u8;
        let token = (&raw const token_byte).cast();
        unsafe {
            initialized(from, &mut bytes, 5, token);
        }
        let e = edit(0);
        let mut input = request(p, MOVE, &e);
        input.moving = from;
        unsafe {
            run(&mut StringFieldsCursor::default(), input);
        }
        unsafe {
            assert_eq!(state(p).length, 5);
            assert_eq!((&raw const (*from).allocator).read(), token);
            assert!(state(from).data.is_null());
        }
        let mut input = request(p, OWNERSHIP, &e);
        input.argument = 1;
        input.source = p;
        assert_eq!(
            unsafe { run(&mut StringFieldsCursor::default(), input) }.action,
            0
        );
        unsafe {
            run(&mut StringFieldsCursor::default(), request(p, CLEAR, &e));
            assert_eq!(state(p).length, 0);
            assert_eq!(state(p).capacity, 16);
        }
        assert_eq!(
            unsafe { run(&mut StringFieldsCursor::default(), request(p, RELEASE, &e)) }.pointer,
            bytes.as_mut_ptr()
        );
        unsafe {
            assert_eq!(state(p).capacity, 0);
            assert_eq!((&raw const (*p).allocator).read(), token);
        }
    }
    #[test]
    fn free_selection_returns_before_any_effect_and_does_not_publish() {
        let mut cells = MaybeUninit::<Cells>::uninit();
        let p = cells.as_mut_ptr();
        let mut bytes = [0u8; 8];
        let token_byte = 0u8;
        let token = (&raw const token_byte).cast();
        unsafe {
            initialized(p, &mut bytes, 3, token);
        }
        let e = edit(0);
        let fx = unsafe {
            run(
                &mut StringFieldsCursor::default(),
                request(p, OWNERSHIP, &e),
            )
        };
        assert_eq!(
            (fx.action, fx.allocator, fx.pointer),
            (FREE, token, bytes.as_mut_ptr())
        );
        unsafe {
            assert_eq!(state(p).length, 3);
        } // No actual free/destructor/callback.
    }
    #[test]
    fn repeat_keeps_original_reserve_cadence_in_fixed_storage_model() {
        let mut cells = MaybeUninit::<Cells>::uninit();
        let p = cells.as_mut_ptr();
        let mut bytes = [0u8; 64];
        let token_byte = 0u8;
        let token = (&raw const token_byte).cast();
        unsafe {
            initialized(p, &mut bytes, 0, token);
            (&raw mut (*p).size).write(8);
        }
        let mut e = edit(REPEAT);
        e.data = b"abcdefghijklmnopq".as_ptr();
        e.length = 17;
        e.count = 3;
        let mut c = StringFieldsCursor::default();
        let mut requests = Vec::new();
        loop {
            let mut input = request(p, EDIT, &e);
            input.replacement = bytes.as_mut_ptr();
            let fx = unsafe { run(&mut c, input) };
            if fx.action == 0 {
                break;
            }
            assert_eq!(fx.action, REALLOC);
            requests.push(fx.requested);
        }
        assert_eq!(requests, [24, 40, 56]);
        unsafe {
            assert_eq!(state(p).length, 51);
        }
        assert_eq!(&bytes[..17], &bytes[34..51]);
    }
    #[test]
    fn grow_and_reduce_commit_original_metadata_prefixes() {
        let mut cells = MaybeUninit::<Cells>::uninit();
        let p = cells.as_mut_ptr();
        let mut bytes = *b"abcdefgh";
        let token_byte = 0u8;
        let token = (&raw const token_byte).cast();
        unsafe {
            initialized(p, &mut bytes, 6, token);
        }
        let e = edit(0);
        let mut input = request(p, GROW, &e);
        input.argument = 2;
        let fx = unsafe { run(&mut StringFieldsCursor::default(), input) };
        assert_eq!((fx.action, fx.requested), (REALLOC, 16));
        unsafe {
            assert_eq!(state(p).length, 8);
        }
        let mut e = edit(0);
        e.offset = 3;
        unsafe {
            run(
                &mut StringFieldsCursor::default(),
                request(p, REDUCE_FIELDS, &e),
            );
            assert_eq!(state(p).length, 5);
        }
        assert_eq!(&bytes[..5], b"defgh");
    }
}
