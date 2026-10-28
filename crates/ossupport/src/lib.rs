//! OS support policy. All storage, syscalls, threads and callbacks remain native.
#![cfg_attr(
    not(test),
    deny(
        clippy::undocumented_unsafe_blocks,
        clippy::multiple_unsafe_ops_per_block
    )
)]
mod read_content;
pub use read_content::{ReadContentState, swr_v1_os_read_content_next};
mod file_content;
pub use file_content::{FileContentState, swr_v1_os_file_content_next};
mod sendfile_fallback;
pub use sendfile_fallback::{SendfileFallbackState, swr_v1_os_sendfile_fallback_next};
mod random_bytes;
pub use random_bytes::{RandomBytesState, swr_v1_os_random_bytes_next};
mod file_line;
pub use file_line::{FileLineResult, swr_v1_os_file_line_result};
mod file_io;
pub use file_io::{FileIoState, swr_v1_os_file_io_next};
mod pool;
pub use pool::{
    Pool, PoolHooks, swr_v1_os_pool_acquire, swr_v1_os_pool_dispatch, swr_v1_os_pool_join,
    swr_v1_os_pool_notify_one, swr_v1_os_pool_queue_size, swr_v1_os_pool_release,
    swr_v1_os_pool_task_id, swr_v1_os_pool_worker_num,
};

/// C's `(size_t)` of an `ssize_t`, as the native policy computes it.
#[expect(
    clippy::cast_possible_truncation,
    clippy::cast_sign_loss,
    reason = "size_t and ssize_t are both 64-bit on the LP64 targets Swoole supports"
)]
const fn size_t(value: i64) -> usize {
    value as usize
}

/// C's `(ssize_t)` of a `size_t`, as the native policy computes it.
#[expect(
    clippy::cast_possible_wrap,
    reason = "size_t and ssize_t are both 64-bit on the LP64 targets Swoole supports"
)]
const fn ssize_t(value: usize) -> i64 {
    value as i64
}

/// Native errno values are reduced to flags before calling; 0 stop, 1 retry, 2 warn.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_os_fs_error(result: i64, retry: bool) -> i32 {
    if result == 0 {
        0
    } else if retry {
        1
    } else {
        2
    }
}
/// Empty takes priority over too large. 0 permitted, 1 empty, 2 too large.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_os_content(length: u64, maximum: u64) -> i32 {
    if length == 0 {
        1
    } else if length > maximum {
        2
    } else {
        0
    }
}
/// Return 0 for a regular file, 1 for failed fstat, or 2 for a non-regular file.
/// Syscall execution, errno publication and returned size remain native.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_os_file_size_action(
    fstat_succeeded: bool,
    mode: u64,
    type_mask: u64,
    regular_type: u64,
) -> i32 {
    if !fstat_succeeded {
        1
    } else if mode & type_mask != regular_type {
        2
    } else {
        0
    }
}
/// Returns terminator-inclusive length, or zero when there is no terminator.
/// # Safety
/// data points to exactly length initialized readable bytes, or length is zero.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_os_line_end(data: *const u8, length: usize) -> usize {
    if length == 0 {
        return 0;
    }
    // SAFETY: the native read already established `length` initialized bytes at `data`.
    let bytes = unsafe { std::slice::from_raw_parts(data, length) };
    bytes
        .iter()
        .position(|&b| b == 0 || b == b'\n')
        .map_or(0, |n| n + 1)
}
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_os_permissions(perms: i32) -> i32 {
    if perms <= 0 || perms >= 0o1000 {
        0o666
    } else {
        perms
    }
}
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_os_queue_flags(flags: i32, blocking: bool, nowait: i32) -> i32 {
    if blocking {
        flags & !nowait
    } else {
        flags | nowait
    }
}
/// Msgsnd failed: 1 retry, 2 quiet final failure, 3 warned final failure.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_os_queue_error(interrupted: bool, again: bool) -> i32 {
    if interrupted {
        1
    } else if again {
        2
    } else {
        3
    }
}
/// The entropy loop retries only EINTR/EAGAIN on result -1, otherwise stops.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_os_random_error(result: i64, interrupted: bool, again: bool) -> bool {
    result == -1 && (interrupted || again)
}
/// Darwin/BSD sendfile after native offset update: retry, error, success, warn.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_os_sendfile_action(result: i64, interrupted: bool) -> i32 {
    if result == -1 {
        if interrupted { 1 } else { 2 }
    } else if result == 0 {
        0
    } else {
        3
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn file_size_action_preserves_native_stat_and_mode_outcomes() {
        for (succeeded, mode, mask, regular, expected) in [
            (false, 0, 0o170_000, 0o100_000, 1),
            (false, 0o040_755, 0o170_000, 0o100_000, 1),
            (true, 0o100_644, 0o170_000, 0o100_000, 0),
            (true, 0o040_755, 0o170_000, 0o100_000, 2),
            (true, 0o020_600, 0o170_000, 0o100_000, 2),
        ] {
            assert_eq!(
                swr_v1_os_file_size_action(succeeded, mode, mask, regular),
                expected
            );
        }
    }

    #[test]
    fn file_and_ipc_priorities() {
        assert_eq!(swr_v1_os_fs_error(0, true), 0);
        assert_eq!(swr_v1_os_fs_error(-1, true), 1);
        assert_eq!(swr_v1_os_content(0, 0), 1);
        assert_eq!(swr_v1_os_content(1, 0), 2);
        assert_eq!(unsafe { swr_v1_os_line_end(b"ab\0cd\n".as_ptr(), 6) }, 3);
        assert_eq!(unsafe { swr_v1_os_line_end(b"abc".as_ptr(), 3) }, 0);
        assert_eq!(swr_v1_os_permissions(0o1000), 0o666);
        assert_eq!(swr_v1_os_queue_error(true, true), 1);
        assert_eq!(swr_v1_os_sendfile_action(-1, true), 1);
    }
    // Each policy against the native expression it replaces (upstream v6.2.4),
    // over every combination of boundary values.
    const SIZES: [usize; 8] = [0, 1, 2, 8, 64, 128, 1024, usize::MAX];
    #[test]
    fn small_policies_match_the_native_expressions() {
        for perms in -1024..2048 {
            assert_eq!(
                swr_v1_os_permissions(perms),
                if perms <= 0 || perms >= 0o1000 {
                    0o666
                } else {
                    perms
                }
            );
        }
        for flags in -128..128 {
            for nowait in [1, 8, 2048] {
                for block in [false, true] {
                    let expected = if block {
                        flags & !nowait
                    } else {
                        flags | nowait
                    };
                    assert_eq!(swr_v1_os_queue_flags(flags, block, nowait), expected);
                }
            }
        }
        for result in -2..3 {
            for a in [false, true] {
                for b in [false, true] {
                    assert_eq!(
                        swr_v1_os_fs_error(result, a),
                        if result == 0 {
                            0
                        } else if a {
                            1
                        } else {
                            2
                        }
                    );
                    assert_eq!(
                        swr_v1_os_random_error(result, a, b),
                        result == -1 && (a || b)
                    );
                    let sendfile = match result {
                        -1 => {
                            if a {
                                1
                            } else {
                                2
                            }
                        }
                        0 => 0,
                        _ => 3,
                    };
                    assert_eq!(swr_v1_os_sendfile_action(result, a), sendfile);
                }
            }
        }
    }
    #[test]
    fn content_event_queue_and_worker_policies_match_the_native_expressions() {
        for length in SIZES {
            for maximum in SIZES {
                let (length, maximum) = (length as u64, maximum as u64);
                assert_eq!(
                    swr_v1_os_content(length, maximum),
                    if length == 0 {
                        1
                    } else if length > maximum {
                        2
                    } else {
                        0
                    }
                );
            }
        }
        for handler in [false, true] {
            for canceled in [false, true] {
                assert_eq!(
                    swr_v1_os_queue_error(handler, canceled),
                    if handler {
                        1
                    } else if canceled {
                        2
                    } else {
                        3
                    }
                );
            }
        }
    }
    #[test]
    fn line_end_is_the_first_nul_or_newline() {
        for length in 0..256 {
            let mut data = vec![b'x'; length];
            for at in 0..=length {
                if at < length {
                    data[at] = if at % 2 == 0 { 0 } else { b'\n' };
                }
                let expected = data
                    .iter()
                    .position(|&b| b == 0 || b == b'\n')
                    .map_or(0, |i| i + 1);
                assert_eq!(
                    unsafe { swr_v1_os_line_end(data.as_ptr(), data.len()) },
                    expected
                );
                if at < length {
                    data[at] = b'x';
                }
            }
        }
    }
}
