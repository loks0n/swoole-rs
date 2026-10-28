//! `swoole::MsgQueue` (upstream `src/os/msg_queue.cc`): open, blocking flag,
//! push and pop over a `SysV` message queue. Native keeps the queue id and logs;
//! each call returns right after a failing syscall with its errno intact.
use libc::{c_int, c_long, c_void};

// The XSI message queue calls, declared here because libc omits them on Darwin.
unsafe extern "C" {
    fn msgget(key: libc::key_t, flags: c_int) -> c_int;
    fn msgsnd(id: c_int, msg: *const c_void, size: usize, flags: c_int) -> c_int;
    fn msgrcv(id: c_int, msg: *mut c_void, size: usize, kind: c_long, flags: c_int) -> isize;
    #[cfg(test)]
    fn msgctl(id: c_int, cmd: c_int, buf: *mut c_void) -> c_int;
}

use libc::{IPC_CREAT, IPC_NOWAIT};

fn errno() -> c_int {
    std::io::Error::last_os_error().raw_os_error().unwrap_or(0)
}

/// Permissions outside (0, 01000) default to 0666.
const fn permissions(perms: c_int) -> c_int {
    if perms <= 0 || perms >= 0o1000 {
        0o666
    } else {
        perms
    }
}

#[repr(C)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct MsgOpen {
    pub id: c_int,
    pub perms: c_int,
}

/// `msgget(key, IPC_CREAT | perms)` with the defaulted permissions.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_os_msg_open(key: libc::key_t, perms: c_int) -> MsgOpen {
    let perms = permissions(perms);
    // SAFETY: msgget has no memory preconditions.
    let id = unsafe { msgget(key, IPC_CREAT | perms) };
    MsgOpen { id, perms }
}

/// `MsgQueue::set_blocking`: only `IPC_NOWAIT` changes.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_os_msg_flags(flags: c_int, blocking: bool) -> c_int {
    if blocking {
        flags & !IPC_NOWAIT
    } else {
        flags | IPC_NOWAIT
    }
}

/// `MsgQueue::push`: retries `EINTR`. 0 sent, 1 failed with `EAGAIN` (quiet),
/// 2 failed (native warns).
/// # Safety
/// `msg` points to a message of `length` payload bytes after its `long` type.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_os_msg_push(
    id: c_int,
    msg: *const c_void,
    length: usize,
    flags: c_int,
) -> c_int {
    loop {
        // SAFETY: `msg` is a valid message per the contract.
        if unsafe { msgsnd(id, msg, length, flags) } == 0 {
            return 0;
        }
        match errno() {
            libc::EINTR => {}
            libc::EAGAIN => return 1,
            _ => return 2,
        }
    }
}

#[repr(C)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct MsgPop {
    pub result: isize,
    pub warn: bool,
}

/// `MsgQueue::pop`: one `msgrcv`; failures other than `ENOMSG`/`EINTR` warn.
/// # Safety
/// `msg` points to writable room for a `long` type and `size` payload bytes.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_os_msg_pop(
    id: c_int,
    msg: *mut c_void,
    size: usize,
    kind: c_long,
    flags: c_int,
) -> MsgPop {
    // SAFETY: `msg` is writable per the contract.
    let result = unsafe { msgrcv(id, msg, size, kind, flags) };
    MsgPop {
        result,
        warn: result < 0 && !matches!(errno(), libc::ENOMSG | libc::EINTR),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn permissions_and_flags_match_the_native_expressions() {
        for perms in -1024..2048 {
            let expected = if perms <= 0 || perms >= 0o1000 {
                0o666
            } else {
                perms
            };
            assert_eq!(permissions(perms), expected, "perms {perms}");
        }
        for flags in -128..128 {
            assert_eq!(
                swr_v1_os_msg_flags(flags, true),
                flags & !IPC_NOWAIT,
                "blocking"
            );
            assert_eq!(
                swr_v1_os_msg_flags(flags, false),
                flags | IPC_NOWAIT,
                "nonblocking"
            );
        }
    }

    #[repr(C)]
    struct Message {
        kind: c_long,
        data: [u8; 8],
    }

    #[test]
    fn a_private_queue_round_trips_and_reports_empty_quietly() {
        let queue = swr_v1_os_msg_open(libc::IPC_PRIVATE, 0);
        assert_eq!(queue.perms, 0o666, "default permissions");
        if queue.id < 0 {
            return; // SysV IPC unavailable in this sandbox.
        }
        let sent = Message {
            kind: 3,
            data: *b"payload\0",
        };
        let flags = swr_v1_os_msg_flags(0, false);
        assert_eq!(
            unsafe { swr_v1_os_msg_push(queue.id, (&raw const sent).cast(), 8, flags) },
            0,
            "sent"
        );
        let mut got = Message {
            kind: 3,
            data: [0; 8],
        };
        let pop = unsafe { swr_v1_os_msg_pop(queue.id, (&raw mut got).cast(), 8, 3, flags) };
        assert_eq!(
            (pop, got.data),
            (
                MsgPop {
                    result: 8,
                    warn: false
                },
                *b"payload\0"
            ),
            "received"
        );
        let pop = unsafe { swr_v1_os_msg_pop(queue.id, (&raw mut got).cast(), 8, 3, flags) };
        assert_eq!(
            pop,
            MsgPop {
                result: -1,
                warn: false
            },
            "ENOMSG is quiet"
        );
        // SAFETY: removes the private queue created above.
        unsafe { msgctl(queue.id, libc::IPC_RMID, std::ptr::null_mut()) };
        let pop = unsafe { swr_v1_os_msg_pop(queue.id, (&raw mut got).cast(), 8, 3, flags) };
        assert_eq!(
            pop,
            MsgPop {
                result: -1,
                warn: true
            },
            "a removed queue warns"
        );
    }
}
