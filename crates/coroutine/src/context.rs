//! Complete stack/completion bookkeeping; Native owns every resource effect.
use std::ffi::c_void;
use std::ptr;

#[repr(C)]
pub struct ContextStackCell {
    pub pointer: *mut c_void,
}
#[repr(C)]
pub struct ContextExtent {
    pub size: u32,
}
#[repr(C)]
pub struct ContextCompletion {
    pub value: u8,
}
#[repr(C)]
pub struct ContextStackView {
    pub pointer: *mut c_void,
    pub top: *mut c_void,
    pub size: usize,
    pub present: u8,
}
impl ContextStackView {
    fn empty() -> Self {
        Self {
            pointer: ptr::null_mut(),
            top: ptr::null_mut(),
            size: 0,
            present: 0,
        }
    }
}

unsafe fn stack_view(
    stack: *const ContextStackCell,
    extent: *const ContextExtent,
) -> ContextStackView {
    let pointer = unsafe { (*stack).pointer };
    ContextStackView {
        pointer,
        top: ptr::null_mut(),
        size: unsafe { (*extent).size } as usize,
        present: u8::from(!pointer.is_null()),
    }
}

/// # Safety
/// Both cells are initialized readable storage with serialized access. This
/// copies metadata only, never bytes from the pointed-to allocation.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_context_stack_read(
    stack: *const ContextStackCell,
    extent: *const ContextExtent,
) -> ContextStackView {
    unsafe { stack_view(stack, extent) }
}

/// Original unsigned field conversion, not stack-size normalization/admission.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_context_extent_new(requested: usize) -> ContextExtent {
    ContextExtent {
        size: requested as u32,
    }
}

/// First constructor-body publication; fn/extent/private-data initialization
/// already finished. Thread backend supplies null extent and allocates no stack.
/// # Safety
/// Completion is writable cell storage, possibly uninitialized. Extent is null
/// or initialized readable storage. Neither aliases the other.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_context_prepare(
    completion: *mut ContextCompletion,
    extent: *const ContextExtent,
) -> usize {
    unsafe { completion.write(ContextCompletion { value: 0 }) };
    unsafe { extent.as_ref() }.map_or(0, |extent| extent.size as usize)
}

/// Native function invocation has returned; publish before swap/unlock.
/// # Safety
/// Completion is writable cell storage. No reference to its prior value is made.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_context_finish(completion: *mut ContextCompletion) {
    unsafe { completion.write(ContextCompletion { value: 1 }) };
}

/// # Safety
/// Completion is initialized readable storage without racing mutation.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_context_completed(completion: *const ContextCompletion) -> u8 {
    u8::from(unsafe { (*completion).value } != 0)
}

/// Whole stack admission/query/top/clear/marker operation. ADMIT initializes the
/// cell only after Native allocation. CLEAR publishes null only after Native free
/// and reads nothing afterward. READ/TOP refresh both fields after Native effects.
/// # Safety
/// Stack cell is writable storage; ADMIT may initialize it, all other operations
/// require it initialized. Extent is live readable initialized storage except
/// CLEAR does not access it. No cells alias and access is serialized. MARK/USAGE
/// additionally require live bounded allocated bytes, and USAGE's marker spans
/// initialized. Original requested-vs-truncated size rules and defined domains
/// remain the caller's contract. No Rust frame crosses a Native effect.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_context_stack_step(
    stack: *mut ContextStackCell,
    extent: *const ContextExtent,
    operation: u32,
    allocation: *mut c_void,
    requested: usize,
) -> ContextStackView {
    if operation == 3 {
        unsafe {
            stack.write(ContextStackCell {
                pointer: ptr::null_mut(),
            })
        };
        return ContextStackView::empty();
    }
    if operation > 5 {
        return ContextStackView::empty();
    }
    if operation == 0 {
        unsafe {
            stack.write(ContextStackCell {
                pointer: allocation,
            })
        };
    }
    let mut view = unsafe { stack_view(stack, extent) };
    match operation {
        2 => view.top = view.pointer.cast::<u8>().wrapping_add(view.size).cast(),
        4 => unsafe { crate::stack::mark(view.pointer.cast(), requested) },
        5 => view.size = unsafe { crate::stack::usage(view.pointer.cast(), view.size) },
        _ => {}
    }
    view
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::mem::MaybeUninit;

    #[test]
    fn raw_cell_initialization_fresh_views_and_completion_keep_native_barriers() {
        let mut bytes = vec![0xa5_u8; 128 * 1024];
        let extent = swr_v1_context_extent_new(bytes.len());
        let mut stack = MaybeUninit::<ContextStackCell>::uninit();
        let mut completion = MaybeUninit::<ContextCompletion>::uninit();
        unsafe {
            assert_eq!(
                swr_v1_context_prepare(completion.as_mut_ptr(), &extent),
                bytes.len()
            );
            assert_eq!(swr_v1_context_completed(completion.as_ptr()), 0);
            // Native allocation returns before the previously uninitialized
            // pointer cell is admitted. No actual Context/allocator is invoked.
            let pointer = bytes.as_mut_ptr().cast();
            let view = swr_v1_context_stack_step(stack.as_mut_ptr(), &extent, 0, pointer, 0);
            assert_eq!(
                (view.pointer, view.size, view.present),
                (pointer, bytes.len(), 1)
            );
            let top = swr_v1_context_stack_step(stack.as_mut_ptr(), &extent, 2, ptr::null_mut(), 0);
            assert_eq!(top.top, bytes.as_mut_ptr().add(bytes.len()).cast());
            swr_v1_context_stack_step(stack.as_mut_ptr(), &extent, 4, ptr::null_mut(), bytes.len());
            let usage =
                swr_v1_context_stack_step(stack.as_mut_ptr(), &extent, 5, ptr::null_mut(), 0);
            assert_eq!(usage.size, 64 * 1024);
            swr_v1_context_finish(completion.as_mut_ptr());
            assert_eq!(swr_v1_context_completed(completion.as_ptr()), 1);
            // Clear follows the external free barrier and never destroys bytes.
            let cleared =
                swr_v1_context_stack_step(stack.as_mut_ptr(), &extent, 3, ptr::null_mut(), 0);
            assert_eq!(
                (cleared.pointer, cleared.size, cleared.present),
                (ptr::null_mut(), 0, 0)
            );
            let read =
                swr_v1_context_stack_step(stack.as_mut_ptr(), &extent, 1, ptr::null_mut(), 0);
            assert_eq!(
                (read.pointer, read.size, read.present),
                (ptr::null_mut(), bytes.len(), 0)
            );
            let mut thread_completion = MaybeUninit::<ContextCompletion>::uninit();
            assert_eq!(
                swr_v1_context_prepare(thread_completion.as_mut_ptr(), ptr::null()),
                0
            );
            assert_eq!(swr_v1_context_completed(thread_completion.as_ptr()), 0);
        }
    }
}
