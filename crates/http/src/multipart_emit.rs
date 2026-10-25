//! Immutable multipart operation plans; all allocation and IO executes natively.
#[repr(C)]
pub struct HttpMultipartAction {
    pub action: u32,
    pub effects: u32,
    pub data: *const u8,
    pub length: usize,
}
#[repr(u32)]
#[derive(Clone, Copy)]
enum Operation {
    Done,
    Marker,
    Filename,
    Boundary,
    Flush,
    Close,
    HeaderName,
    HeaderValue,
}
const SET_HEADER: u32 = 1;
const CLEAR_HEADER: u32 = 2;
const COMMIT_BODY: u32 = 4;
const fn operation(action: Operation, effects: u32) -> HttpMultipartAction {
    HttpMultipartAction {
        action: action as u32,
        effects,
        data: std::ptr::null(),
        length: 0,
    }
}
const fn marker(data: &'static [u8], effects: u32) -> HttpMultipartAction {
    HttpMultipartAction {
        action: Operation::Marker as u32,
        effects,
        data: data.as_ptr(),
        length: data.len(),
    }
}
const HEADER_FILE: &[HttpMultipartAction] = &[
    marker(b"Swoole-Upload-File: ", 0),
    operation(Operation::Filename, 0),
    marker(b"\r\n", SET_HEADER),
];
const HEADER: &[HttpMultipartAction] = &[marker(b"\r\n", SET_HEADER)];
const DATA_FILE: &[HttpMultipartAction] = &[
    marker(b"\r\nSwoole-Upload-File", CLEAR_HEADER),
    operation(Operation::Flush, 0),
    operation(Operation::Close, 0),
    marker(b"\r\n", 0),
];
const DATA: &[HttpMultipartAction] = &[marker(b"\r\n", CLEAR_HEADER)];
const PART: &[HttpMultipartAction] = &[operation(Operation::Boundary, 0), marker(b"\r\n", 0)];
const BODY: &[HttpMultipartAction] = &[
    operation(Operation::Boundary, 0),
    marker(b"--", 0),
    operation(Operation::Done, COMMIT_BODY),
];
const VALUE: &[HttpMultipartAction] = &[
    operation(Operation::HeaderName, 0),
    marker(b": ", 0),
    operation(Operation::HeaderValue, 0),
    marker(b"\r\n", 0),
];
/// Kinds0=header complete,1=data end,2=part begin,3=body end,4=header value.
/// Actions0=done,1=append static marker,2=append current native filename,
/// 3=append current boundary,4=fflush current FILE,5=fclose then clear FILE,
/// 6=append current header name,7=append caller's header-value bytes.
/// Effects1=set header-parsed,2=clear it,4=commit content length+dispatch flag.
/// # Safety
/// Count is aligned/writable and disjoint from module-owned read-only storage.
/// Returned plan/markers are immutable and valid for the module lifetime. Native
/// applies each effect before its action, reading native operands at that point.
/// No Rust frame/owner/borrow survives any native allocation, callback or IO.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_http_multipart_emit(
    kind: u32,
    has_file: u32,
    count: *mut usize,
) -> *const HttpMultipartAction {
    if count.is_null() {
        return std::ptr::null();
    }
    let plan = match (kind, has_file != 0) {
        (0, true) => HEADER_FILE,
        (0, false) => HEADER,
        (1, true) => DATA_FILE,
        (1, false) => DATA,
        (2, _) => PART,
        (3, _) => BODY,
        (4, _) => VALUE,
        _ => return std::ptr::null(),
    };
    unsafe { count.write(plan.len()) };
    plan.as_ptr()
}
/// Native body-end publication reads lengths only after both appends returned.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_http_multipart_body_length(
    buffer_length: usize,
    header_length: usize,
) -> usize {
    buffer_length.wrapping_sub(header_length)
}
