//! Complete line-result policy; read, NUL publication and seek remain native.
#[repr(C)]
#[derive(Debug, Copy, Clone, PartialEq, Eq)]
pub struct FileLineResult {
    pub length: i64,
    pub action: u32,
    pub extra: u32,
}
/// Nonpositive results return unchanged without inspecting data. Positive results
/// select native NUL publication followed by seek; extra preserves the original
/// skipped byte when no terminator occurs. Offset addition stays native so the
/// original left-associated signed arithmetic is preserved.
/// # Safety
/// For positive read_result, data points to that many initialized readable bytes,
/// with read_result <= isize::MAX. The borrow ends before any native effect.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_os_file_line_result(
    data: *const u8,
    read_result: i64,
) -> FileLineResult {
    if read_result <= 0 {
        return FileLineResult {
            length: read_result,
            action: 0,
            extra: 0,
        };
    }
    // SAFETY: a positive read result is the length of the initialized prefix at `data`.
    let end = unsafe { crate::swr_v1_os_line_end(data, crate::size_t(read_result)) };
    FileLineResult {
        length: if end == 0 {
            read_result
        } else {
            crate::ssize_t(end)
        },
        action: 1,
        extra: u32::from(end == 0),
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn nonpositive_never_borrows_or_finalizes() {
        for n in [i64::MIN, -1, 0] {
            assert_eq!(
                unsafe { swr_v1_os_file_line_result(std::ptr::null(), n) },
                FileLineResult {
                    length: n,
                    action: 0,
                    extra: 0
                }
            );
        }
    }
    #[test]
    fn first_terminator_includes_it_and_preserves_seek_distinction() {
        for (bytes, length, extra) in [
            (b"abc".as_slice(), 3, 1),
            (b"a\nb\0".as_slice(), 2, 0),
            (b"\0\n".as_slice(), 1, 0),
            (b"\xff\xfe".as_slice(), 2, 1),
            (b"abc\n".as_slice(), 4, 0),
        ] {
            assert_eq!(
                unsafe {
                    swr_v1_os_file_line_result(bytes.as_ptr(), i64::try_from(bytes.len()).unwrap())
                },
                FileLineResult {
                    length,
                    action: 1,
                    extra
                }
            );
        }
        assert_eq!(std::mem::size_of::<FileLineResult>(), 16);
    }
}
