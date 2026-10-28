//! OS support: the async thread pool, file IO loops, sendfile, entropy and the
//! `SysV` message queue policies.
#![cfg_attr(
    not(test),
    deny(
        clippy::undocumented_unsafe_blocks,
        clippy::multiple_unsafe_ops_per_block
    )
)]
mod file;
#[cfg(any(target_vendor = "apple", target_os = "freebsd"))]
pub use file::swr_v1_os_sendfile;
pub use file::{
    FileIo, FileSize, Sendfile, swr_v1_os_file_read_all, swr_v1_os_file_read_line,
    swr_v1_os_file_size, swr_v1_os_file_write_all, swr_v1_os_random_bytes, swr_v1_os_sendfile_copy,
};
mod pool;
pub use pool::{
    Pool, PoolHooks, swr_v1_os_pool_acquire, swr_v1_os_pool_dispatch, swr_v1_os_pool_join,
    swr_v1_os_pool_notify_one, swr_v1_os_pool_queue_size, swr_v1_os_pool_release,
    swr_v1_os_pool_task_id, swr_v1_os_pool_worker_num,
};

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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn message_queue_policies_match_the_native_expressions() {
        for perms in -1024..2048 {
            assert_eq!(
                swr_v1_os_permissions(perms),
                if perms <= 0 || perms >= 0o1000 {
                    0o666
                } else {
                    perms
                },
                "perms {perms}"
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
                    assert_eq!(
                        swr_v1_os_queue_flags(flags, block, nowait),
                        expected,
                        "flags {flags}"
                    );
                }
            }
        }
        for interrupted in [false, true] {
            for again in [false, true] {
                let expected = if interrupted {
                    1
                } else if again {
                    2
                } else {
                    3
                };
                assert_eq!(
                    swr_v1_os_queue_error(interrupted, again),
                    expected,
                    "msgsnd error"
                );
            }
        }
    }
}
