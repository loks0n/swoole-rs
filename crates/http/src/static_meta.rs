//! Inline static handler policy; native owns strings, RNG and MIME references.
use crate::proxy::HttpProxyText;
use crate::{INVALID, OVERFLOW, bytes};
use std::{mem::MaybeUninit, slice};
pub(crate) const BOUNDARY: &[u8] = b"SwooleBoundary\0";
const CONTENT_TYPE: &[u8] = b"multipart/byteranges; boundary=\0";

/// Return the lazy boundary initializer, or NULL for an existing boundary.
/// # Safety
/// random_length is aligned/writable; the returned string has static lifetime.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_http_static_boundary(
    length: usize,
    random_length: *mut usize,
) -> *const u8 {
    if length != 0 || random_length.is_null() {
        return std::ptr::null();
    }
    unsafe { random_length.write(39 - BOUNDARY.len()) };
    BOUNDARY.as_ptr()
}
/// Multipart prefix for multiple tasks, otherwise NULL (native MIME reference).
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_http_static_content_prefix(tasks: usize) -> *const u8 {
    if tasks > 1 {
        CONTENT_TYPE.as_ptr()
    } else {
        std::ptr::null()
    }
}
/// Query/write the binary-safe multipart content type, excluding any NUL.
/// # Safety
/// Input spans are initialized. Output and written are writable and disjoint
/// from inputs. Native string allocation completes before this call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_http_static_content_type(
    boundary: *const HttpProxyText,
    output: *mut u8,
    capacity: usize,
    written: *mut usize,
) -> i32 {
    if boundary.is_null() || written.is_null() || (capacity != 0 && output.is_null()) {
        return INVALID;
    }
    let boundary = unsafe { &*boundary };
    let boundary = match unsafe { bytes(boundary.data, boundary.length) } {
        Ok(v) => v,
        Err(e) => return e,
    };
    let prefix = &CONTENT_TYPE[..CONTENT_TYPE.len() - 1];
    let Some(length) = prefix
        .len()
        .checked_add(boundary.len())
        .filter(|&n| n <= isize::MAX as usize)
    else {
        return OVERFLOW;
    };
    if capacity != 0 {
        if capacity < length || capacity > isize::MAX as usize {
            return OVERFLOW;
        }
        let output = unsafe { slice::from_raw_parts_mut(output.cast::<MaybeUninit<u8>>(), length) };
        for (slot, &byte) in output.iter_mut().zip(prefix.iter().chain(boundary)) {
            slot.write(byte);
        }
    }
    unsafe { written.write(length) };
    0
}
/// Check0=no parent token,1=inside root using pinned C-string prefix semantics.
/// # Safety
/// Filename/root are readable for their declared initialized spans.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_http_static_path_check(
    filename: *const u8,
    length: usize,
    root: *const u8,
    root_length: usize,
    kind: u32,
) -> i32 {
    if kind > 1 {
        return INVALID;
    }
    let filename = match unsafe {
        bytes(
            filename,
            if kind == 0 {
                #[expect(
                    clippy::cast_possible_truncation,
                    reason = "the native uint32_t filename length"
                )]
                let native = length as u32 as usize;
                native
            } else {
                length
            },
        )
    } {
        Ok(v) => v,
        Err(e) => return e,
    };
    if kind == 0 {
        return i32::from(!filename.windows(2).any(|s| s == b".."));
    }
    if filename.len() <= root_length || filename[root_length] != b'/' {
        return 0;
    }
    let root = match unsafe { bytes(root, root_length) } {
        Ok(v) => v,
        Err(e) => return e,
    };
    for (&a, &b) in filename.iter().zip(root) {
        if a != b {
            return 0;
        }
        if a == 0 {
            break;
        }
    }
    1
}
/// Publish404 only for the terminal location match; no native callback occurs.
/// # Safety
/// status is aligned, initialized and exclusively writable.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_http_static_catch(last: u32, status: *mut i32) -> i32 {
    if status.is_null() {
        return INVALID;
    }
    if last == 0 {
        return 0;
    }
    unsafe { status.write(404) };
    1
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn binary_content_and_rejected_small_buffer_do_not_publish_partial_results() {
        let boundary = HttpProxyText {
            data: b"a\0b".as_ptr(),
            length: 3,
        };
        let mut output = [0xa5; 64];
        let mut written = 99;
        assert_eq!(
            unsafe {
                swr_v1_http_static_content_type(&boundary, output.as_mut_ptr(), 1, &mut written)
            },
            OVERFLOW
        );
        assert_eq!(output, [0xa5; 64]);
        assert_eq!(written, 99);
        assert_eq!(
            unsafe {
                swr_v1_http_static_content_type(
                    &boundary,
                    output.as_mut_ptr(),
                    output.len(),
                    &mut written,
                )
            },
            0
        );
        assert_eq!(&output[..written], b"multipart/byteranges; boundary=a\0b");
        assert_eq!(output[written], 0xa5);
    }
    #[test]
    fn c_prefix_containment_and_bytewise_parent_check_remain_distinct() {
        let filename = b"/r\0other/child";
        let root = b"/r\0oot";
        assert_eq!(
            unsafe {
                swr_v1_http_static_path_check(
                    filename.as_ptr(),
                    filename.len(),
                    root.as_ptr(),
                    root.len(),
                    1,
                )
            },
            0
        );
        let filename = b"/r\0abc/child";
        assert_eq!(
            unsafe {
                swr_v1_http_static_path_check(
                    filename.as_ptr(),
                    filename.len(),
                    root.as_ptr(),
                    root.len(),
                    1,
                )
            },
            1
        );
        let filename = b"a\0..b";
        assert_eq!(
            unsafe {
                swr_v1_http_static_path_check(
                    filename.as_ptr(),
                    filename.len(),
                    std::ptr::null(),
                    0,
                    0,
                )
            },
            0
        );
    }
}
