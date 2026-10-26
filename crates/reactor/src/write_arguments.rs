//! Real POSIX-vector length and post-send Buffer append preparation. Native owns
//! Socket/Buffer effects; no vector borrow survives this completed call.
#[repr(C)]
pub struct ReactorWriteArguments {
    pub length: usize,
    pub offset: usize,
    pub status: i32,
}
/// # Safety
/// When TLS is false, `vectors` names `count` live genuine target C iovec
/// objects. Only their lengths are read. No data pointer is dereferenced or
/// retained. The caller preserves the original Native input domain.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_write_prepare(
    tls: u32,
    vectors: *const libc::iovec,
    count: usize,
) -> ReactorWriteArguments {
    if tls != 0 {
        return ReactorWriteArguments {
            length: 0,
            offset: 0,
            status: 1,
        };
    }
    let mut length = 0usize;
    for index in 0..count {
        // The target libc binding is the actual POSIX C ABI, not a copied POD.
        // SAFETY: `index < count`, and `vectors` names `count` initialized iovecs.
        length = length.wrapping_add(unsafe { (*vectors.wrapping_add(index)).iov_len });
    }
    ReactorWriteArguments {
        length,
        offset: 0,
        status: 0,
    }
}
/// Kind zero is contiguous bytes; kind one is a vector's offset-only append.
/// Native retains the original size_t-to-uint32_t/off_t conversions at Buffer.
#[unsafe(no_mangle)]
#[expect(clippy::cast_sign_loss, reason = "native ssize_t sent offsets")]
pub extern "C" fn swr_v1_reactor_write_append(
    kind: u32,
    length: usize,
    sent: isize,
) -> ReactorWriteArguments {
    let offset = if sent > 0 { sent as usize } else { 0 };
    ReactorWriteArguments {
        length: if kind == 0 {
            length.wrapping_sub(offset)
        } else {
            0
        },
        offset,
        status: if kind < 2 { 0 } else { -1 },
    }
}
/// Target layout witness for the genuine POSIX seam and its Native compiler.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_reactor_iovec_layout(field: u32) -> usize {
    match field {
        0 => std::mem::size_of::<libc::iovec>(),
        1 => std::mem::align_of::<libc::iovec>(),
        2 => std::mem::offset_of!(libc::iovec, iov_base),
        3 => std::mem::offset_of!(libc::iovec, iov_len),
        _ => usize::MAX,
    }
}
#[cfg(test)]
#[expect(
    clippy::cast_sign_loss,
    reason = "tests drive the native integer interfaces with literal and loop values"
)]
mod tests {
    use super::*;
    #[test]
    fn write_arguments_positive_vectors_and_append_ranges() {
        assert_eq!(
            std::mem::size_of::<ReactorWriteArguments>(),
            3 * std::mem::size_of::<usize>()
        );
        assert_eq!(
            std::mem::offset_of!(ReactorWriteArguments, offset),
            std::mem::size_of::<usize>()
        );
        assert_eq!(
            std::mem::offset_of!(ReactorWriteArguments, status),
            2 * std::mem::size_of::<usize>()
        );
        let vectors = [1, 3, 7].map(|iov_len| libc::iovec {
            iov_base: std::ptr::null_mut(),
            iov_len,
        });
        let prepared = unsafe { swr_v1_reactor_write_prepare(0, vectors.as_ptr(), vectors.len()) };
        assert_eq!(
            (prepared.length, prepared.offset, prepared.status),
            (11, 0, 0)
        );
        // TLS rejects before any vector observation; no Native error is executed.
        assert_eq!(
            unsafe { swr_v1_reactor_write_prepare(1, std::ptr::null(), 9) }.status,
            1
        );
        for sent in [1, 3, 11] {
            let scalar = swr_v1_reactor_write_append(0, 11, sent);
            let vector = swr_v1_reactor_write_append(1, 0, sent);
            assert_eq!(
                (scalar.length, scalar.offset, scalar.status),
                (11 - sent as usize, sent as usize, 0)
            );
            assert_eq!(
                (vector.length, vector.offset, vector.status),
                (0, sent as usize, 0)
            );
        }
        // Pure arithmetic preserves the C size_t fold; no oversized Native I/O.
        let vectors = [usize::MAX, 3].map(|iov_len| libc::iovec {
            iov_base: std::ptr::null_mut(),
            iov_len,
        });
        assert_eq!(
            unsafe { swr_v1_reactor_write_prepare(0, vectors.as_ptr(), 2) }.length,
            2
        );
    }
}
