//! Readiness/interest and opt-in metadata ownership; Native retains effects and default registries.
#[cfg(unix)]
mod batch;
#[cfg(unix)]
pub use batch::*;
#[cfg(unix)]
mod backend;
#[cfg(unix)]
pub use backend::*;
#[cfg(unix)]
mod poll;
#[cfg(unix)]
pub use poll::*;

#[cfg(unix)]
mod registration;
#[cfg(unix)]
pub use registration::*;

#[cfg(unix)]
mod write_arguments;
#[cfg(unix)]
pub use write_arguments::*;

mod output;
pub use output::*;

mod output_workflow;
pub use output_workflow::*;

mod builtins;
pub use builtins::*;

mod handlers;
pub use handlers::*;

mod initialize;
pub use initialize::*;

mod deferred;
pub use deferred::*;

mod callbacks;
pub use callbacks::*;

mod owner;

mod write_workflow;
pub use write_workflow::*;

mod wait;
pub use wait::*;

mod ready_workflow;
pub use ready_workflow::*;

mod flush;
pub use flush::*;

const INVALID: i32 = -1;
const READ: u32 = 1;
const WRITE: u32 = 2;
const ERROR: u32 = 4;
#[repr(C)]
#[derive(Default)]
pub struct ReadyState {
    pub phase: u32,
}
/// Return0=done,1=read,2=write,3=error,4=once removal. Backend0=poll/epoll;
/// backend1=kqueue's one-filter record. Mask bits read1/write2/error4 are native
/// readiness, not current interest. Supply fresh removal/once facts after each
/// action, and a fresh mask too: recursive native waits may rewrite the batch.
/// # Safety
/// State is aligned/writable and not accessed concurrently. No native object,
/// callback, allocation or reference is retained across calls.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_ready(
    state: *mut ReadyState,
    backend: u32,
    mask: u32,
    removed: u32,
    once: u32,
) -> i32 {
    if state.is_null() || backend > 1 || mask & !7 != 0 {
        return INVALID;
    }
    let state = unsafe { &mut *state };
    if state.phase > 4 {
        return INVALID;
    }
    if backend == 1 && state.phase == 0 {
        state.phase = 3;
        return if removed != 0 {
            0
        } else if mask & READ != 0 {
            1
        } else if mask & WRITE != 0 {
            2
        } else {
            0
        };
    }
    while state.phase < 4 {
        let phase = state.phase;
        state.phase += 1;
        if removed != 0 {
            continue;
        }
        match phase {
            0 if mask & READ != 0 => return 1,
            1 if mask & WRITE != 0 => return 2,
            2 if mask & ERROR != 0 => {
                // The original error-with-R/W continue skips ONCE bookkeeping.
                if mask & (READ | WRITE) != 0 {
                    state.phase = 4;
                    return 0;
                }
                return 3;
            }
            3 if once != 0 => return 4,
            _ => {}
        }
    }
    0
}
#[repr(C)]
#[derive(Default, Debug, PartialEq, Copy, Clone)]
pub struct Interest {
    pub events: i32,
    ///0=no operation,1=set,2=add,3=delete.
    pub action: u32,
    /// Publish native socket.events before the native operation, even if it fails.
    pub publish: u32,
}
const SW_READ: i32 = 1 << 9;
const SW_WRITE: i32 = 1 << 10;
/// Operations0=add bits,1=remove bits,2=remove read,3=remove write,
///4=add read,5=add write. Dedicated interest helpers intentionally discard old
/// flags on their add-only branch, matching the public inline native methods.
/// # Safety
/// Output is aligned/writable. No allocation, owner, callback or borrow escapes.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_interest(
    operation: u32,
    events: i32,
    bits: i32,
    output: *mut Interest,
) -> i32 {
    if output.is_null() || operation > 5 {
        return INVALID;
    }
    let result = match operation {
        0 if events & bits == 0 => Interest {
            events: events | bits,
            action: 1,
            publish: 0,
        },
        1 if events & bits != 0 => Interest {
            events: events & !bits,
            action: 1,
            publish: 0,
        },
        0 | 1 => Interest {
            events,
            ..Interest::default()
        },
        2 | 3 => {
            let (remove, keep) = if operation == 2 {
                (SW_READ, SW_WRITE)
            } else {
                (SW_WRITE, SW_READ)
            };
            if events & keep != 0 {
                Interest {
                    events: events & !remove,
                    action: 1,
                    publish: 1,
                }
            } else {
                Interest {
                    events,
                    action: 3,
                    publish: 0,
                }
            }
        }
        4 | 5 => {
            let (add, other) = if operation == 4 {
                (SW_READ, SW_WRITE)
            } else {
                (SW_WRITE, SW_READ)
            };
            if events & other != 0 {
                Interest {
                    events: events | add,
                    action: 1,
                    publish: 1,
                }
            } else {
                Interest {
                    events: add,
                    action: 2,
                    publish: 0,
                }
            }
        }
        _ => unreachable!(),
    };
    unsafe { output.write(result) };
    0
}
/// Select the next kqueue filter operation without running a native syscall.
/// Operation 0 adds requested filters, 1 sets both filters (including deletes),
/// 2 deletes currently requested filters. Return 0=done, 1=read/add, 2=write/add,
/// 3=read/delete, 4=write/delete, -1=invalid. Supply current native events on
/// every step. Stop on native failure before asking for another action.
/// # Safety
/// State is aligned/writable, initialized to zero, and exclusively accessed.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_filter(
    state: *mut ReadyState,
    operation: u32,
    events: i32,
) -> i32 {
    if state.is_null() || operation > 2 {
        return INVALID;
    }
    let state = unsafe { &mut *state };
    if state.phase > 2 {
        return INVALID;
    }
    next_filter(&mut state.phase, operation, events)
}

pub(crate) fn next_filter(phase: &mut u32, operation: u32, events: i32) -> i32 {
    while *phase < 2 {
        let index = *phase;
        *phase += 1;
        let requested = if index == 0 {
            events & SW_READ != 0 || (operation != 2 && events < 256)
        } else {
            events & SW_WRITE != 0
        };
        if operation != 1 && !requested {
            continue;
        }
        return (index + 1 + if operation == 2 || !requested { 2 } else { 0 }) as i32;
    }
    0
}

/// Queue admission/retry policy. Native owns send/catch/allocation/append and
/// invokes each action after this function returns. Flags: empty1, TLS-send2,
/// output-buffer-present4, writable-interest8. Actions: done0, send1, catch2,
/// allocate3, add-write4, append-and-return-length5, return-send-result6,
/// package-too-large7, overflow8, publish-native-errno-and-fail9.
/// # Safety
/// State is aligned/writable, starts at zero and is exclusively accessed.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_write(
    state: *mut ReadyState,
    length: usize,
    buffered: usize,
    capacity: u32,
    flags: u32,
    sent: isize,
    wait: u32,
    interrupted: u32,
) -> i32 {
    if state.is_null() || flags & !15 != 0 {
        return INVALID;
    }
    let state = unsafe { &mut *state };
    if state.phase > 7 {
        return INVALID;
    }
    loop {
        match state.phase {
            0 => {
                // Preserve native uint32_t admission truncation, not usize.
                if length as u32 > capacity {
                    state.phase = 7;
                    return 7;
                }
                if flags & 1 == 0 {
                    state.phase = 7;
                    return if buffered.wrapping_add(length) > capacity as usize {
                        8
                    } else {
                        5
                    };
                }
                if flags & 2 != 0 {
                    state.phase = 4;
                } else {
                    state.phase = 2;
                    return 1;
                }
            }
            2 => {
                if sent > 0 {
                    if sent == length as isize {
                        state.phase = 7;
                        return 6;
                    }
                    state.phase = 4;
                } else {
                    state.phase = 3;
                    return 2;
                }
            }
            3 => {
                if wait != 0 {
                    state.phase = 4;
                } else if interrupted != 0 {
                    state.phase = 2;
                    return 1;
                } else {
                    state.phase = 7;
                    return 9;
                }
            }
            4 => {
                state.phase = 5;
                if flags & 4 == 0 {
                    return 3;
                }
            }
            5 => {
                state.phase = 6;
                if flags & 8 == 0 {
                    return 4;
                }
            }
            6 => {
                state.phase = 7;
                return 5;
            }
            7 => return 0,
            _ => return INVALID,
        }
    }
}

/// Encode the stream's four-byte network-order body length. The supplied total
/// length follows native size_t subtraction and uint32 truncation semantics.
/// # Safety
/// Destination points to four writable bytes. No pointer is retained.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_stream_prepare(destination: *mut u8, total_length: usize) -> i32 {
    if destination.is_null() {
        return INVALID;
    }
    let bytes = (total_length.wrapping_sub(4) as u32).to_be_bytes();
    unsafe { destination.cast::<[u8; 4]>().write(bytes) };
    0
}
/// Decode sync framing, including the native signed int length/capacity casts.
/// # Safety
/// Header points to four readable bytes, including any native zero-filled tail
/// after a short prefix read. No pointer is retained.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_stream_length(header: *const u8, capacity: usize) -> i32 {
    if header.is_null() {
        return INVALID;
    }
    let length = u32::from_be_bytes(unsafe { header.cast::<[u8; 4]>().read() }) as i32;
    if length <= 0 || length > capacity as i32 {
        INVALID
    } else {
        length
    }
}
#[repr(C)]
pub struct StreamView {
    pub offset: u32,
    pub length: u32,
    pub close_wait: u32,
}
/// Native dispatch retains the span/callback. A four-byte record terminates;
/// other lengths preserve native uint32 subtraction, including small inputs.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_stream_view(length: u32) -> StreamView {
    StreamView {
        offset: 4,
        length: length.wrapping_sub(4),
        close_wait: u32::from(length == 4),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn stream_lengths_preserve_network_bytes_and_native_signed_capacity() {
        let mut bytes = [0xa5; 6];
        assert_eq!(
            unsafe { swr_v1_stream_prepare(bytes.as_mut_ptr().add(1), 12) },
            0
        );
        assert_eq!(bytes, [0xa5, 0, 0, 0, 8, 0xa5]);
        assert_eq!(unsafe { swr_v1_stream_length(bytes.as_ptr().add(1), 8) }, 8);
        assert_eq!(
            unsafe { swr_v1_stream_length(bytes.as_ptr().add(1), i32::MAX as usize + 1) },
            INVALID
        );
        assert_eq!(
            unsafe { swr_v1_stream_prepare(core::ptr::null_mut(), 4) },
            INVALID
        );
        assert_eq!(
            unsafe { swr_v1_stream_length(core::ptr::null(), 8) },
            INVALID
        );
        assert_eq!(swr_v1_stream_view(3).length, u32::MAX);
        assert_eq!(swr_v1_stream_view(4).close_wait, 1);
    }
    #[test]
    fn error_with_read_write_skips_once_and_callback_facts_are_fresh() {
        let mut state = ReadyState::default();
        assert_eq!(
            unsafe { swr_v1_reactor_ready(&mut state, 0, READ | WRITE | ERROR, 0, 1) },
            1
        );
        assert_eq!(
            unsafe { swr_v1_reactor_ready(&mut state, 0, READ | WRITE | ERROR, 1, 1) },
            0
        );
        let mut state = ReadyState::default();
        for expected in [1, 2, 0] {
            assert_eq!(
                unsafe { swr_v1_reactor_ready(&mut state, 0, 7, 0, 1) },
                expected
            );
        }
        let mut state = ReadyState::default();
        assert_eq!(
            unsafe { swr_v1_reactor_ready(&mut state, 1, READ, 0, 0) },
            1
        );
        // A callback's nested wait may change the filter. Kqueue still invokes
        // only its original one callback before native ONCE deletion.
        assert_eq!(
            unsafe { swr_v1_reactor_ready(&mut state, 1, WRITE, 0, 1) },
            4
        );
    }
    #[test]
    fn interest_publication_and_add_branch_flag_loss_are_explicit() {
        let mut out = Interest::default();
        assert_eq!(
            unsafe { swr_v1_reactor_interest(2, SW_READ | SW_WRITE | 4096, 0, &mut out) },
            0
        );
        assert_eq!(
            out,
            Interest {
                events: SW_WRITE | 4096,
                action: 1,
                publish: 1
            }
        );
        assert_eq!(unsafe { swr_v1_reactor_interest(4, 4096, 0, &mut out) }, 0);
        assert_eq!(
            out,
            Interest {
                events: SW_READ,
                action: 2,
                publish: 0
            }
        );
        let before = out;
        assert_eq!(
            unsafe { swr_v1_reactor_interest(6, 0, 0, &mut out) },
            INVALID
        );
        assert_eq!(out, before);
    }
    #[test]
    fn filters_observe_fresh_events_and_invalid_state_is_unchanged() {
        let mut state = ReadyState::default();
        assert_eq!(
            unsafe { swr_v1_reactor_filter(&mut state, 2, SW_READ | SW_WRITE) },
            3
        );
        assert_eq!(unsafe { swr_v1_reactor_filter(&mut state, 2, 0) }, 0);
        let mut state = ReadyState::default();
        assert_eq!(unsafe { swr_v1_reactor_filter(&mut state, 1, SW_READ) }, 1);
        assert_eq!(unsafe { swr_v1_reactor_filter(&mut state, 1, SW_WRITE) }, 2);
        assert_eq!(unsafe { swr_v1_reactor_filter(&mut state, 1, 0) }, 0);
        let mut state = ReadyState::default();
        assert_eq!(unsafe { swr_v1_reactor_filter(&mut state, 0, 0) }, 1);
        assert_eq!(unsafe { swr_v1_reactor_filter(&mut state, 0, 0) }, 0);
        let mut state = ReadyState::default();
        assert_eq!(unsafe { swr_v1_reactor_filter(&mut state, 1, 256) }, 3);
        let mut state = ReadyState { phase: 3 };
        assert_eq!(
            unsafe { swr_v1_reactor_filter(&mut state, 0, SW_READ) },
            INVALID
        );
        assert_eq!(state.phase, 3);
    }
}

mod blocking;
pub use blocking::*;

mod iov_progress;
pub use iov_progress::*;

#[cfg(unix)]
mod ordinary_io;
#[cfg(unix)]
pub use ordinary_io::*;

#[cfg(unix)]
mod socket_policy;
#[cfg(unix)]
pub use socket_policy::*;

#[cfg(unix)]
mod fd_options;
#[cfg(unix)]
pub use fd_options::*;

#[cfg(unix)]
mod socket_options;
#[cfg(unix)]
pub use socket_options::*;

#[cfg(unix)]
mod iov_owned;
#[cfg(unix)]
pub use iov_owned::*;

mod signal_dispatch;
pub use signal_dispatch::*;

mod connect;
pub use connect::*;
