//! Immutable known-string bytes in frozen native enum order. Zend's mutable
//! persistent/interned pointer table remains singular and native-owned.
use std::ffi::c_char;

const STRINGS: [&[u8]; 64] = [
    b"type\0",
    b"host\0",
    b"user-agent\0",
    b"accept\0",
    b"content-type\0",
    b"content-length\0",
    b"authorization\0",
    b"connection\0",
    b"accept-encoding\0",
    b"port\0",
    b"setting\0",
    b"id\0",
    b"fd\0",
    b"sock\0",
    b"pipe\0",
    b"headers\0",
    b"requestMethod\0",
    b"requestHeaders\0",
    b"requestBody\0",
    b"uploadFiles\0",
    b"cookies\0",
    b"downloadFile\0",
    b"downloadOffset\0",
    b"server\0",
    b"header\0",
    b"get\0",
    b"post\0",
    b"files\0",
    b"tmpfiles\0",
    b"cookie\0",
    b"method\0",
    b"path\0",
    b"data\0",
    b"pipeline\0",
    b"usePipelineRead\0",
    b"trailer\0",
    b"master_pid\0",
    b"callback\0",
    b"opcode\0",
    b"code\0",
    b"reason\0",
    b"flags\0",
    b"finish\0",
    b"in_coroutine\0",
    b"private_data\0",
    b"Swoole\\NameResolver\0",
    b"socket\0",
    b"127.0.0.1\0",
    b"::1\0",
    b"request_method\0",
    b"request_uri\0",
    b"path_info\0",
    b"request_time\0",
    b"request_time_float\0",
    b"server_protocol\0",
    b"server_port\0",
    b"server_addr\0",
    b"remote_port\0",
    b"remote_addr\0",
    b"master_time\0",
    b"query_string\0",
    b"HTTP/1.0\0",
    b"HTTP/1.1\0",
    b"HTTP/2\0",
];

#[unsafe(no_mangle)]
pub(crate) extern "C" fn swr_v1_phphelpers_known_count() -> usize {
    STRINGS.len()
}

/// # Safety
/// Cursor and length are independent aligned native-owned writable storage.
/// Cursor is initialized; returned bytes are immutable static NUL-terminated data.
/// Zend allocation/interning and publication happen after Rust returns.
#[unsafe(no_mangle)]
pub(crate) unsafe extern "C" fn swr_v1_phphelpers_known_next(
    cursor: *mut usize,
    length: *mut usize,
) -> *const c_char {
    if cursor.is_null() || length.is_null() {
        return std::ptr::null();
    }
    // SAFETY: non-null (checked above), aligned, initialized cursor storage.
    let index = unsafe { cursor.read() };
    let Some(bytes) = STRINGS.get(index) else {
        return std::ptr::null();
    };
    // The cursor is initialized input; length is write-only output and may be
    // uninitialized. Never form a typed reference to that output storage.
    // SAFETY: non-null (checked above), aligned, writable output.
    unsafe { length.write(bytes.len() - 1) };
    // SAFETY: as for the read above.
    unsafe { cursor.write(index + 1) };
    bytes.as_ptr().cast()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::mem::MaybeUninit;
    #[test]
    fn known_output_initializes_once_and_end_preserves_output() {
        let mut cursor = 0;
        for expected in STRINGS {
            let mut length = MaybeUninit::<usize>::uninit();
            let name =
                unsafe { swr_v1_phphelpers_known_next(&raw mut cursor, length.as_mut_ptr()) };
            assert_eq!(name, expected.as_ptr().cast());
            assert_eq!(unsafe { length.assume_init() }, expected.len() - 1);
        }
        let mut length = 37;
        assert!(
            unsafe { swr_v1_phphelpers_known_next(&raw mut cursor, &raw mut length) }.is_null()
        );
        assert_eq!(length, 37);
        assert_eq!(cursor, STRINGS.len());
        cursor = 0;
        assert!(
            unsafe { swr_v1_phphelpers_known_next(&raw mut cursor, std::ptr::null_mut()) }
                .is_null()
        );
        assert_eq!(cursor, 0);
    }
}
