//! Multipart upload accounting and result policy; native retains parser/stdio.
use crate::INVALID;
#[repr(C)]
#[derive(Default)]
pub struct HttpMultipartData {
    pub phase: u32,
    pub has_file: u32,
    pub flags: u32,
    pub buffer_length: usize,
    pub maximum: usize,
    pub upload_size: usize,
    pub upload_maximum: usize,
    pub length: usize,
    pub written: i64,
}
impl HttpMultipartData {
    pub(crate) fn step(&mut self) -> i32 {
        if self.phase > 2 {
            return INVALID;
        }
        self.flags = 0;
        match self.phase {
            0 => {
                if self.has_file == 0 {
                    // Native unsigned size_t addition is defined to wrap. Preserve
                    // its existing limit behavior rather than silently tightening it.
                    if self.buffer_length.wrapping_add(self.length) > self.maximum {
                        self.flags = 3;
                        5
                    } else {
                        1
                    }
                } else {
                    self.upload_size = self.upload_size.wrapping_add(self.length);
                    if self.upload_size > self.upload_maximum {
                        self.flags = 5;
                        5
                    } else {
                        self.phase = 1;
                        2
                    }
                }
            }
            1 => {
                if i64::try_from(self.length).is_ok_and(|length| self.written == length) {
                    0
                } else {
                    self.phase = 2;
                    3
                }
            }
            2 => {
                self.flags = 3;
                4
            }
            _ => INVALID,
        }
    }
}
/// Native action:0=success,1=append,2=fwrite,3=fclose+clear FILE,4=warn/reject,
/// 5=reject. Flags:1=excepted,2=unavailable,4=too_large. Upload_size publication
/// follows the first call when has_file; flags apply before the requested action.
/// # Safety
/// State is aligned/readable/writable and valid for each call. No native object,
/// allocation, callback or borrow is retained between resumptions.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_http_multipart_data(state: *mut HttpMultipartData) -> i32 {
    if state.is_null() {
        return INVALID;
    }
    let state = unsafe { &mut *state };
    state.step()
}
/// Classify the mature parser's return after its native execution has ended.
/// -1=log parser error,0=log short result/reject,1=log short result/excepted,
/// 2=clear input/success. Unsigned cast matches the pinned ssize_t/size_t check.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_http_multipart_result(
    processed: i64,
    length: usize,
    excepted: u32,
) -> i32 {
    if processed < 0 {
        -1
    } else if usize::try_from(processed) != Ok(length) {
        i32::from(excepted != 0)
    } else {
        2
    }
}
/// Classify the complete native header name before scratch allocation can move it.
/// # Safety
/// The input span is readable for this call. No reference survives the return.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_http_multipart_disposition(data: *const u8, length: usize) -> i32 {
    match unsafe { crate::bytes(data, length) } {
        Ok(name) => i32::from(crate::case_equal(name, b"content-disposition")),
        Err(status) => status,
    }
}
/// Consume the existing destructive cookie iterator through the first filename.
/// The legacy callback stops even for a filename with no '=' or an empty value.
/// Native file creation runs only after this function returns.
/// # Safety
/// Scratch is writable through capacity<=isize::MAX and initialized through a
/// reachable NUL terminator. No reference or owner is retained across native work.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_http_multipart_filename(data: *mut u8, capacity: usize) -> i32 {
    let mut cursor = 0;
    let mut cookie = crate::headers::HttpCookie::default();
    loop {
        let status = unsafe {
            crate::headers::swr_v1_http_cookie_next(data, capacity, &mut cursor, &mut cookie)
        };
        if status != 1 {
            return status;
        }
        let key =
            unsafe { core::slice::from_raw_parts(data.add(cookie.key_offset), cookie.key_length) };
        if crate::case_equal(key, b"filename") {
            return 1;
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn filename_stops_with_identical_destructive_cookie_state() {
        for input in [
            &b"form-data; name=x; filename=one; filename=two\0"[..],
            b"FiLeNaMe;next=x\0",
            b"filename =x;other=y\0",
            b"=bad; filename=\0",
            b"filename\0;ignored=value",
            b"name=x\0",
            b"\0",
        ] {
            let mut expected = input.to_vec();
            let mut actual = input.to_vec();
            let mut cursor = 0;
            let mut out = crate::headers::HttpCookie::default();
            let result = loop {
                let status = unsafe {
                    crate::headers::swr_v1_http_cookie_next(
                        expected.as_mut_ptr(),
                        expected.len(),
                        &mut cursor,
                        &mut out,
                    )
                };
                if status != 1 {
                    break status;
                }
                if expected[out.key_offset..out.key_offset + out.key_length]
                    .eq_ignore_ascii_case(b"filename")
                {
                    break 1;
                }
            };
            assert_eq!(
                unsafe { swr_v1_http_multipart_filename(actual.as_mut_ptr(), actual.len()) },
                result
            );
            assert_eq!(actual, expected);
        }
        assert_eq!(
            unsafe { swr_v1_http_multipart_disposition(b"Content-Disposition".as_ptr(), 19) },
            1
        );
        assert_eq!(
            unsafe { swr_v1_http_multipart_disposition(b"content-disposition ".as_ptr(), 20) },
            0
        );
        assert_eq!(
            unsafe { swr_v1_http_multipart_filename(core::ptr::null_mut(), 0) },
            INVALID
        );
        assert_eq!(
            unsafe { swr_v1_http_multipart_disposition(core::ptr::null(), 1) },
            INVALID
        );
        let mut missing_nul = *b"filename";
        assert_eq!(
            unsafe { swr_v1_http_multipart_filename(missing_nul.as_mut_ptr(), missing_nul.len()) },
            INVALID
        );
    }
    #[test]
    fn unsigned_accounting_and_write_failure_publication_order() {
        let mut data = HttpMultipartData {
            buffer_length: usize::MAX,
            length: 1,
            ..Default::default()
        };
        assert_eq!(unsafe { swr_v1_http_multipart_data(&mut data) }, 1);
        data.has_file = 1;
        data.upload_size = usize::MAX;
        assert_eq!(unsafe { swr_v1_http_multipart_data(&mut data) }, 2);
        assert_eq!(data.upload_size, 0);
        data.written = 0;
        assert_eq!(unsafe { swr_v1_http_multipart_data(&mut data) }, 3);
        assert_eq!(data.flags, 0);
        assert_eq!(unsafe { swr_v1_http_multipart_data(&mut data) }, 4);
        assert_eq!(data.flags, 3);
        assert_eq!(swr_v1_http_multipart_result(-1, usize::MAX, 1), -1);
        assert_eq!(swr_v1_http_multipart_result(1, 2, 0), 0);
        assert_eq!(swr_v1_http_multipart_result(1, 2, 1), 1);
        assert_eq!(swr_v1_http_multipart_result(2, 2, 0), 2);
    }
}
