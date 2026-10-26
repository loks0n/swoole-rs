use super::bytes;
use std::ffi::{CStr, c_char};
pub(super) static METHODS: [&CStr; 27] = [
    c"DELETE",
    c"GET",
    c"HEAD",
    c"POST",
    c"PUT",
    c"PATCH",
    c"CONNECT",
    c"OPTIONS",
    c"TRACE",
    c"COPY",
    c"LOCK",
    c"MKCOL",
    c"MOVE",
    c"PROPFIND",
    c"PROPPATCH",
    c"UNLOCK",
    c"REPORT",
    c"MKACTIVITY",
    c"CHECKOUT",
    c"MERGE",
    c"M-SEARCH",
    c"NOTIFY",
    c"SUBSCRIBE",
    c"UNSUBSCRIBE",
    c"PURGE",
    c"QUERY",
    c"PRI",
];
/// Return the immutable NUL-terminated legacy status, or null for native fallback.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_http_status(code: i32) -> *const c_char {
    match code {
        100 => c"100 Continue".as_ptr(),
        101 => c"101 Switching Protocols".as_ptr(),
        102 => c"102 Processing".as_ptr(),
        103 => c"103 Early Hints".as_ptr(),
        201 => c"201 Created".as_ptr(),
        202 => c"202 Accepted".as_ptr(),
        203 => c"203 Non-Authoritative Information".as_ptr(),
        204 => c"204 No Content".as_ptr(),
        205 => c"205 Reset Content".as_ptr(),
        206 => c"206 Partial Content".as_ptr(),
        207 => c"207 Multi-Status".as_ptr(),
        208 => c"208 Already Reported".as_ptr(),
        226 => c"226 IM Used".as_ptr(),
        300 => c"300 Multiple Choices".as_ptr(),
        301 => c"301 Moved Permanently".as_ptr(),
        302 => c"302 Found".as_ptr(),
        303 => c"303 See Other".as_ptr(),
        304 => c"304 Not Modified".as_ptr(),
        305 => c"305 Use Proxy".as_ptr(),
        306 => c"306 (Unused)".as_ptr(),
        307 => c"307 Temporary Redirect".as_ptr(),
        308 => c"308 Permanent Redirect".as_ptr(),
        400 => c"400 Bad Request".as_ptr(),
        401 => c"401 Unauthorized".as_ptr(),
        402 => c"402 Payment Required".as_ptr(),
        403 => c"403 Forbidden".as_ptr(),
        404 => c"404 Not Found".as_ptr(),
        405 => c"405 Method Not Allowed".as_ptr(),
        406 => c"406 Not Acceptable".as_ptr(),
        407 => c"407 Proxy Authentication Required".as_ptr(),
        408 => c"408 Request Timeout".as_ptr(),
        409 => c"409 Conflict".as_ptr(),
        410 => c"410 Gone".as_ptr(),
        411 => c"411 Length Required".as_ptr(),
        412 => c"412 Precondition Failed".as_ptr(),
        413 => c"413 Payload Too Large".as_ptr(),
        414 => c"414 URI Too Long".as_ptr(),
        415 => c"415 Unsupported Media Type".as_ptr(),
        416 => c"416 Range Not Satisfiable".as_ptr(),
        417 => c"417 Expectation Failed".as_ptr(),
        418 => c"418 I'm a teapot".as_ptr(),
        421 => c"421 Misdirected Request".as_ptr(),
        422 => c"422 Unprocessable Entity".as_ptr(),
        423 => c"423 Locked".as_ptr(),
        424 => c"424 Failed Dependency".as_ptr(),
        425 => c"425 Too Early".as_ptr(),
        426 => c"426 Upgrade Required".as_ptr(),
        428 => c"428 Precondition Required".as_ptr(),
        429 => c"429 Too Many Requests".as_ptr(),
        431 => c"431 Request Header Fields Too Large".as_ptr(),
        451 => c"451 Unavailable For Legal Reasons".as_ptr(),
        500 => c"500 Internal Server Error".as_ptr(),
        501 => c"501 Not Implemented".as_ptr(),
        502 => c"502 Bad Gateway".as_ptr(),
        503 => c"503 Service Unavailable".as_ptr(),
        504 => c"504 Gateway Timeout".as_ptr(),
        505 => c"505 HTTP Version Not Supported".as_ptr(),
        506 => c"506 Variant Also Negotiates".as_ptr(),
        507 => c"507 Insufficient Storage".as_ptr(),
        508 => c"508 Loop Detected".as_ptr(),
        510 => c"510 Not Extended".as_ptr(),
        511 => c"511 Network Authentication Required".as_ptr(),
        0 => c"200 OK".as_ptr(),
        200 => c"200 OK".as_ptr(),
        _ => std::ptr::null(),
    }
}
/// # Safety
/// Nonempty input is readable for length bytes. No borrow/allocator escapes.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_http_method(data: *const u8, length: usize) -> i32 {
    // SAFETY: the caller lends `length` initialized bytes at `data` (null only when empty).
    let input = match unsafe { bytes(data, length) } {
        Ok(v) => v,
        Err(e) => return e,
    };
    METHODS
        .iter()
        .position(|name| super::case_equal(name.to_bytes(), input))
        .map_or(-1, |index| i32::try_from(index + 1).unwrap_or(-1))
}
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_http_method_string(method: i32) -> *const c_char {
    usize::try_from(method)
        .ok()
        .and_then(|id| id.checked_sub(1))
        .and_then(|index| METHODS.get(index))
        .map_or(std::ptr::null(), |name| name.as_ptr())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn method_ids_roundtrip_and_reject_unknowns() {
        for (index, name) in METHODS.iter().enumerate() {
            let lower = name.to_bytes().to_ascii_lowercase();
            assert_eq!(
                unsafe { swr_v1_http_method(lower.as_ptr(), lower.len()) },
                i32::try_from(index + 1).unwrap()
            );
            assert_eq!(
                swr_v1_http_method_string(i32::try_from(index + 1).unwrap()),
                name.as_ptr()
            );
        }
        assert!(swr_v1_http_method_string(0).is_null());
        assert!(swr_v1_http_method_string(28).is_null());
    }
}
