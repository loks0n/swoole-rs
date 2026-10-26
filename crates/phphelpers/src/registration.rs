//! Ordered stdext registration policy; Zend handler/function storage stays native.
use std::ffi::c_char;

#[repr(C)]
pub struct SwrPhpInitStep {
    index: u32,
    name: *const c_char,
    length: usize,
}

const FUNCTIONS: [&[u8]; 6] = [
    b"swoole_call_array_method\0",
    b"swoole_call_string_method\0",
    b"swoole_call_stream_method\0",
    b"array_push\0",
    b"array_unshift\0",
    b"array_splice\0",
];

/// # Safety
/// Cursor is aligned initialized native storage, disjoint from writable step.
/// Returned names are immutable static bytes. Native registration, lookups and
/// handler capture/replacement execute after Rust returns, in this exact order.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phphelpers_init_next(
    cursor: *mut usize,
    step: *mut SwrPhpInitStep,
) -> u32 {
    let (Some(cursor), false) = (unsafe { cursor.as_mut() }, step.is_null()) else {
        return 0;
    };
    let (action, index) = match *cursor {
        0..=4 => (1, *cursor),
        5..=10 => (2, *cursor - 5),
        11..=13 => (3, *cursor - 11),
        _ => return 0,
    };
    let name = if action == 2 { FUNCTIONS[index] } else { &[] };
    let Ok(index) = u32::try_from(index) else {
        return 0;
    };
    unsafe {
        step.write(SwrPhpInitStep {
            index,
            name: if name.is_empty() {
                std::ptr::null()
            } else {
                name.as_ptr().cast()
            },
            length: name.len().saturating_sub(1),
        });
    }
    *cursor += 1;
    action
}

#[repr(C)]
pub struct SwrPhpWrapper {
    name: *const c_char,
    length: usize,
    position: i32,
}

/// # Safety
/// Output is aligned writable native storage. Name is immutable static bytes;
/// native function-table caching and invocation execute after this returns.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phphelpers_wrapper(index: u32, output: *mut SwrPhpWrapper) -> u8 {
    if output.is_null() {
        return 0;
    }
    let (name, position): (&[u8], i32) = match index {
        0 => (b"array_search\0", 1),
        1 => (b"in_array\0", 1),
        2 => (b"implode\0", 1),
        3 => (b"array_key_exists\0", 1),
        4 => (b"array_map\0", 1),
        5 => (b"str_replace\0", 2),
        6 => (b"str_ireplace\0", 2),
        7 => (b"explode\0", 1),
        8 => (b"hash\0", 1),
        9 => (b"str_replace\0", 2),
        10 => (b"str_ireplace\0", 2),
        _ => return 0,
    };
    unsafe {
        output.write(SwrPhpWrapper {
            name: name.as_ptr().cast(),
            length: name.len() - 1,
            position,
        });
    }
    1
}
