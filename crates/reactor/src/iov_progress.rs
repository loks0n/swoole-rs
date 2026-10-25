//! Genuine POSIX iovec progress policy. Native retains both existing arrays,
//! public counters and all payload-pointer writes; Rust reads only live lengths.
#[repr(C)]
pub struct ReactorIovProgress {
    pub offset_bytes: usize,
    pub advance: usize,
    pub consumed: usize,
    pub remain_count: i32,
    pub index: i32,
    pub action: i32,
}
pub(crate) fn progress(
    lengths: impl IntoIterator<Item = usize>,
    n: isize,
    remaining: i32,
    index: i32,
    offset: usize,
) -> ReactorIovProgress {
    if n <= 0 || remaining == 0 {
        return ReactorIovProgress {
            offset_bytes: offset,
            advance: 0,
            consumed: 0,
            remain_count: remaining,
            index,
            action: 0,
        };
    }
    let mut total = 0usize;
    for (i, length) in lengths.into_iter().enumerate() {
        total = total.wrapping_add(length);
        if (total as isize) >= n {
            let mut consumed = length.wrapping_sub(total.wrapping_sub(n as usize));
            let mut advance = i;
            if consumed == length {
                advance += 1;
                consumed = 0;
            }
            let remain_count = remaining.wrapping_sub(advance as i32);
            return ReactorIovProgress {
                offset_bytes: (if i > 0 { 0 } else { offset }).wrapping_add(consumed),
                advance,
                consumed,
                remain_count,
                index: index.wrapping_add(advance as i32),
                action: if remain_count == 0 { 2 } else { 1 },
            };
        }
    }
    ReactorIovProgress {
        offset_bytes: offset,
        advance: 0,
        consumed: 0,
        remain_count: remaining,
        index,
        action: -1,
    }
}
/// Actions:0 unchanged,1 publish counters then advance/update iterator,
///2 publish counters and return BEFORE touching the iterator, -1 Native abort.
/// The existing offset_bytes behavior at exact segment boundaries is preserved;
/// it is not normalized into a different absolute/segment offset policy.
/// # Safety
/// For positive n/remaining, vectors names remaining live target C iovec objects.
/// Their payloads are neither observed nor borrowed. Valid Native signed-sum/
/// integer domains are preserved; oversized conversions/overflow are not parity.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_iov_progress(
    vectors: *const libc::iovec,
    n: isize,
    remaining: i32,
    index: i32,
    offset: usize,
) -> ReactorIovProgress {
    progress(
        (0..remaining).map(|i| unsafe { (*vectors.add(i as usize)).iov_len }),
        n,
        remaining,
        index,
        offset,
    )
}
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_reactor_iov_progress_layout(field: u32) -> usize {
    match field {
        0 => std::mem::size_of::<ReactorIovProgress>(),
        1 => std::mem::align_of::<ReactorIovProgress>(),
        2 => std::mem::offset_of!(ReactorIovProgress, offset_bytes),
        3 => std::mem::offset_of!(ReactorIovProgress, advance),
        4 => std::mem::offset_of!(ReactorIovProgress, consumed),
        5 => std::mem::offset_of!(ReactorIovProgress, remain_count),
        6 => std::mem::offset_of!(ReactorIovProgress, index),
        7 => std::mem::offset_of!(ReactorIovProgress, action),
        _ => usize::MAX,
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn iov_progress_positive_segments_and_native_boundary_metadata() {
        let first = progress([3, 5], 2, 2, 0, 0);
        assert_eq!(
            (
                first.action,
                first.remain_count,
                first.index,
                first.offset_bytes,
                first.advance,
                first.consumed
            ),
            (1, 2, 0, 2, 0, 2)
        );
        let boundary = progress([1, 5], 1, 2, 0, 2);
        assert_eq!(
            (
                boundary.action,
                boundary.remain_count,
                boundary.index,
                boundary.offset_bytes,
                boundary.advance,
                boundary.consumed
            ),
            (1, 1, 1, 2, 1, 0)
        );
        let final_piece = progress([5], 5, 1, 1, 2);
        assert_eq!(
            (
                final_piece.action,
                final_piece.remain_count,
                final_piece.index,
                final_piece.offset_bytes
            ),
            (2, 0, 2, 2)
        );
        // Pure guard proof only; no Native zero-count/negative-I/O probe.
        let unchanged = unsafe { swr_v1_reactor_iov_progress(std::ptr::null(), 1, 0, 2, 2) };
        assert_eq!((unchanged.action, unchanged.index), (0, 2));
        let vectors = [1, 3, 7].map(|iov_len| libc::iovec {
            iov_base: std::ptr::null_mut(),
            iov_len,
        });
        let result = unsafe { swr_v1_reactor_iov_progress(vectors.as_ptr(), 4, 3, 0, 0) };
        assert_eq!(
            (
                result.action,
                result.remain_count,
                result.index,
                result.advance,
                result.consumed
            ),
            (1, 1, 2, 2, 0)
        );
    }
}
