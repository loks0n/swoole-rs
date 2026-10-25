//! Blocking Socket orchestration. Only POD facts enter; Native owns callbacks,
//! File/Socket/array storage, clocks, errno, SSL, syscalls and all effects.
use crate::ReactorOutputAction;
#[repr(C)]
pub struct ReactorBlockingWait {
    pub phase: u32,
    pub timeout_msec: i32,
    pub began_at: f64,
}
#[repr(C)]
pub struct ReactorBlockingIo {
    pub phase: u32,
    pub action: i32,
    pub length: usize,
    pub offset: usize,
    pub value: isize,
}
#[repr(C)]
pub struct ReactorBlockingFile {
    pub phase: u32,
    pub flags: u32,
}
fn output(phase: u32, action: i32, value: i64) -> ReactorOutputAction {
    ReactorOutputAction {
        phase,
        action,
        value,
    }
}
fn next_wait(state: &mut ReactorBlockingWait, phase: u32, action: i32) -> i32 {
    state.phase = phase;
    action
}
fn after_wait(state: &mut ReactorBlockingWait) -> i32 {
    if state.timeout_msec > 0 {
        next_wait(state, 12, 13)
    } else {
        next_wait(state, 6, 6)
    }
}
/// Wait effects:0 false,1 initial clock,2 nonblock fact,3 set nonblock,4 SSL
///fact,5 clear SSL error,6 callback,7 take kernel-nobufs flag,8 usleep,9 wait,
///10 errno fact,11 dont-restart fact,12 true,13 elapsed clock,14 trace,
///15 publish timeout error/false. Only requested facts are observed by Native.
/// # Safety
/// `state` is a unique live POD for this synchronous call. No reference survives
/// return or spans a Native callback, clock, syscall, logger or exception.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_blocking_wait(
    state: *mut ReactorBlockingWait,
    observed: i32,
    now: f64,
) -> i32 {
    let state = unsafe { &mut *state };
    match state.phase {
        0 if state.timeout_msec > 0 => next_wait(state, 1, 1),
        0 => next_wait(state, 2, 2),
        1 => {
            state.began_at = now;
            next_wait(state, 2, 2)
        }
        2 if observed == 0 => next_wait(state, 3, 3),
        2 | 3 => next_wait(state, 4, 4),
        4 if observed != 0 => next_wait(state, 5, 5),
        4 | 5 => next_wait(state, 6, 6),
        6 if observed == 4 => next_wait(state, 100, 0),
        6 if observed == 5 => next_wait(state, 100, 12),
        6 if observed == 1 => next_wait(state, 7, 7),
        6 => next_wait(state, 9, 9),
        7 if observed != 0 => next_wait(state, 8, 8),
        7 => next_wait(state, 9, 9),
        8 => next_wait(state, 6, 6),
        9 if observed == -1 => next_wait(state, 10, 10),
        9 => after_wait(state),
        10 if observed == libc::EINTR => next_wait(state, 11, 11),
        10 => next_wait(state, 100, 0),
        11 if observed != 0 => next_wait(state, 100, 0),
        11 => after_wait(state),
        12 => {
            // Pinned sec2msec(double) converts to C long before subtracting
            // from int. Preserve that order and its defined finite domain.
            let elapsed = ((now - state.began_at) * 1000.0) as libc::c_long;
            state.timeout_msec = (state.timeout_msec as libc::c_long).wrapping_sub(elapsed) as i32;
            next_wait(state, 13, 14)
        }
        13 if state.timeout_msec <= 0 => next_wait(state, 100, 15),
        13 => next_wait(state, 6, 6),
        _ => -1,
    }
}
/// SSL is observed before requesting its want flags. Event constants are
/// statically asserted by the real Native caller. No SSL effect happens here.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_reactor_blocking_event(
    phase: u32,
    flags: u32,
    event: i32,
) -> ReactorOutputAction {
    match phase {
        0 if flags != 0 => output(1, 1, 0),
        0 => output(1, 0, event.into()),
        1 if flags != 0 => output(3, 0, 1024),
        1 => output(2, 2, 0),
        2 => output(3, 0, if flags != 0 { 512 } else { event.into() }),
        _ => output(phase, -1, 0),
    }
}
fn io(phase: u32, action: i32, length: usize, offset: usize, value: isize) -> ReactorBlockingIo {
    ReactorBlockingIo {
        phase,
        action,
        length,
        offset,
        value,
    }
}
/// Kinds:0 contiguous send,1 writev,2 sendfile,3 final bool/byte conversion,
///4 one-shot read/write;5 receive (flags in begin, WAITALL controls repeat);
///6 one-shot datagram (a short positive datagram completes, never streams).
/// Actions:0 return Native enum/value,1 actual send,2 errno fact,3 classify,
///4 publish last error,5 publish byte counter,6 observe File offset/end.
/// Positive overflow outside the pinned defined ssize_t domain is not parity.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_reactor_blocking_io(
    kind: u32,
    phase: u32,
    length: usize,
    bytes: isize,
    result: isize,
    observed: i32,
    begin: i64,
    end: i64,
) -> ReactorBlockingIo {
    if kind == 3 {
        return io(0, 0, 0, 0, if observed != 0 { bytes } else { -1 });
    }
    if kind > 6 {
        return io(phase, -1, 0, 0, 0);
    }
    match phase {
        0 => io(
            1,
            1,
            if kind == 0 || kind == 4 || kind == 5 {
                length.wrapping_sub(bytes as usize)
            } else {
                0
            },
            bytes as usize,
            if kind == 5 {
                (begin as i32 & !libc::MSG_WAITALL) as isize
            } else {
                0
            },
        ),
        1 if result < 0 => io(2, 2, 0, 0, 0),
        1 if result == 0 => io(6, 0, 0, 0, if kind == 2 { 4 } else { 5 }),
        1 if kind == 2 => io(4, 6, 0, 0, 0),
        1 => io(
            4,
            5,
            0,
            0,
            if kind == 0 || kind == 4 || kind == 5 {
                bytes.wrapping_add(result)
            } else {
                result
            },
        ),
        2 if observed == libc::EINTR => io(6, 0, 0, 0, 1),
        2 => io(3, 3, 0, 0, 0),
        3 if observed == 2 => io(6, 0, 0, 0, 1),
        3 => io(5, 4, 0, 0, 0),
        5 => io(6, 0, 0, 0, 4),
        4 => io(
            6,
            0,
            0,
            0,
            if (kind == 0 && bytes as usize != length)
                || (kind == 5 && begin as i32 & libc::MSG_WAITALL != 0 && bytes != length as isize)
                || (kind == 2 && begin < end)
            {
                1
            } else {
                5
            },
        ),
        _ => io(phase, -1, 0, 0, 0),
    }
}
/// Whole synchronous sendfile order. Effects:0 return,1 parameter validation,
///2 cork,3 wait/callback,4 uncork,5 observe validated range. Flags retain only
///transient cork/wait booleans; actual File and offset stay Native-owned.
/// # Safety
/// `state` uniquely names a live Native POD; no reference survives return.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_blocking_file(
    state: *mut ReactorBlockingFile,
    observed: i32,
    begin: i64,
    end: i64,
    cork_min: i64,
) -> ReactorOutputAction {
    let state = unsafe { &mut *state };
    let finish = |flags| output(6, 0, if flags & 2 != 0 { 0 } else { -1 });
    let reply = match state.phase {
        0 => output(1, 1, 0),
        1 if observed == 0 => output(6, 0, -1),
        1 => output(5, 5, 0),
        5 if end.wrapping_sub(begin) > cork_min => output(2, 2, 0),
        5 => output(3, 3, 0),
        2 => {
            state.flags = u32::from(observed != 0);
            output(3, 3, 0)
        }
        3 => {
            state.flags |= u32::from(observed != 0) << 1;
            if state.flags & 1 != 0 {
                output(4, 4, 0)
            } else {
                finish(state.flags)
            }
        }
        4 => finish(state.flags),
        _ => output(state.phase, -1, 0),
    };
    state.phase = reply.phase;
    reply
}
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_reactor_blocking_layout(kind: u32, field: u32) -> usize {
    match (kind, field) {
        (0, 0) => std::mem::size_of::<ReactorBlockingWait>(),
        (0, 1) => std::mem::align_of::<ReactorBlockingWait>(),
        (0, 2) => std::mem::offset_of!(ReactorBlockingWait, timeout_msec),
        (0, 3) => std::mem::offset_of!(ReactorBlockingWait, began_at),
        (1, 0) => std::mem::size_of::<ReactorBlockingIo>(),
        (1, 1) => std::mem::align_of::<ReactorBlockingIo>(),
        (1, 2) => std::mem::offset_of!(ReactorBlockingIo, length),
        (1, 3) => std::mem::offset_of!(ReactorBlockingIo, offset),
        (1, 4) => std::mem::offset_of!(ReactorBlockingIo, value),
        (2, 0) => std::mem::size_of::<ReactorBlockingFile>(),
        (2, 1) => std::mem::align_of::<ReactorBlockingFile>(),
        (2, 2) => std::mem::offset_of!(ReactorBlockingFile, flags),
        _ => usize::MAX,
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn datagram_positive_short_result_is_single_message() {
        for result in [1, 3, 17] {
            let call = swr_v1_reactor_blocking_io(6, 0, 0, 0, 0, 0, 0, 0);
            assert_eq!(call.action, 1);
            let publication = swr_v1_reactor_blocking_io(6, 1, 0, 0, result, 0, 0, 0);
            assert_eq!((publication.action, publication.value), (5, result));
            assert_eq!(
                swr_v1_reactor_blocking_io(6, 4, 0, result, result, 0, 0, 0).value,
                5
            );
        }
    }
    #[test]
    fn blocking_positive_wait_io_and_file_order() {
        let mut state = ReactorBlockingWait {
            phase: 0,
            timeout_msec: 100,
            began_at: 0.0,
        };
        let mut actions = Vec::new();
        for (observed, now) in [
            (0, 0.0),
            (0, 1.0),
            (0, 0.0),
            (0, 0.0),
            (0, 0.0),
            (1, 0.0),
            (0, 0.0),
            (0, 0.0),
            (0, 1.005),
            (0, 0.0),
            (5, 0.0),
        ] {
            actions.push(unsafe { swr_v1_reactor_blocking_wait(&mut state, observed, now) });
        }
        assert_eq!(actions, vec![1, 2, 3, 4, 6, 7, 9, 13, 14, 6, 12]);
        assert_eq!(state.timeout_msec, 96); // C-long truncation of represented double.
        assert_eq!(swr_v1_reactor_blocking_event(0, 0, 77).value, 77);
        assert_eq!(swr_v1_reactor_blocking_event(0, 1, 77).action, 1);
        assert_eq!(swr_v1_reactor_blocking_event(1, 3, 77).value, 1024);
        for sent in 1..=7 {
            let send = swr_v1_reactor_blocking_io(0, 0, 7, 0, 0, 0, 0, 0);
            assert_eq!((send.action, send.length, send.offset), (1, 7, 0));
            let publish = swr_v1_reactor_blocking_io(0, 1, 7, 0, sent, 0, 0, 0);
            assert_eq!((publish.action, publish.value), (5, sent));
            assert_eq!(
                swr_v1_reactor_blocking_io(0, 4, 7, sent, sent, 0, 0, 0).value,
                if sent == 7 { 5 } else { 1 }
            );
        }
        let mut file = ReactorBlockingFile { phase: 0, flags: 0 };
        let mut actions = Vec::new();
        for (observed, begin, end) in [
            (0, 0, 0),
            (1, 0, 0),
            (0, 2, 31),
            (1, 0, 0),
            (1, 0, 0),
            (0, 0, 0),
        ] {
            actions.push(
                unsafe { swr_v1_reactor_blocking_file(&mut file, observed, begin, end, 8) }.action,
            );
        }
        assert_eq!(actions, vec![1, 5, 2, 3, 4, 0]);
    }
    #[test]
    fn blocking_positive_receive_waitall_and_one_shot() {
        for flags in [0, libc::MSG_WAITALL] {
            let first = swr_v1_reactor_blocking_io(5, 0, 7, 0, 0, 0, flags as i64, 0);
            assert_eq!(first.action, 1);
            assert_eq!(first.length, 7);
            assert_eq!(first.offset, 0);
            assert_eq!(first.value, 0); // MSG_WAITALL is cleared before Native recv.
            let append = swr_v1_reactor_blocking_io(5, 1, 7, 0, 3, 0, flags as i64, 0);
            assert_eq!(append.action, 5);
            assert_eq!(append.value, 3);
            let next = swr_v1_reactor_blocking_io(5, 4, 7, 3, 3, 0, flags as i64, 0);
            assert_eq!(next.value, if flags == 0 { 5 } else { 1 });
        }
        let complete = swr_v1_reactor_blocking_io(5, 4, 7, 7, 4, 0, libc::MSG_WAITALL as i64, 0);
        assert_eq!(complete.value, 5);
    }
}
