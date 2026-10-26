//! Backend registration policy. Native executes kernel/map/log effects only
//! after each decision returns. In particular removal observers may change
//! errno, which must be supplied freshly before the cleanup decision.
#[repr(C)]
#[derive(Default)]
pub struct RegistrationState {
    pub phase: u32,
    pub filter: u32,
}

/// Poll operation0add/1set/2del. Return0publication;1alreadyexists;2capacity;
///3missing-set;4alreadyremoved;5missing-delete. Native retains exact log formats.
#[unsafe(no_mangle)]
#[expect(clippy::cast_sign_loss, reason = "native int count compared as size_t")]
pub extern "C" fn swr_v1_reactor_poll_registration(
    operation: u32,
    exists: u32,
    removed: u32,
    count: usize,
    capacity: i32,
) -> i32 {
    match operation {
        0 if exists != 0 => 1,
        0 if count == capacity as usize => 2,
        0 => 0,
        1 if exists == 0 => 3,
        1 => 0,
        2 if removed != 0 => 4,
        2 if exists == 0 => 5,
        2 => 0,
        _ => -1,
    }
}

/// Epoll operation0add/1set/2del. Actions0kernel-control,1removed-warning,
///2Native-removal-observer,3syscall-warning,4publish. Return after every effect.
/// # Safety
/// State is live/zero-initialized/exclusive; no native object or borrow retained.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_epoll_registration(
    state: *mut RegistrationState,
    operation: u32,
    removed: u32,
    result: i32,
    error: i32,
) -> i32 {
    // SAFETY: `state` is null or live, aligned and exclusively lent for this call.
    let Some(state) = (unsafe { state.as_mut() }) else {
        return -1;
    };
    if operation > 2 {
        return -1;
    }
    match state.phase {
        0 if operation == 2 && removed != 0 => {
            state.phase = 4;
            1
        }
        0 => {
            state.phase = 1;
            0
        }
        1 if result >= 0 => {
            state.phase = 4;
            4
        }
        1 if operation == 2 => {
            state.phase = 2;
            2
        }
        1 => {
            state.phase = 4;
            3
        }
        2 if error == libc::EBADF || error == libc::ENOENT => {
            state.phase = 4;
            4
        }
        2 => {
            state.phase = 4;
            3
        }
        _ => -1,
    }
}

#[cfg(target_os = "linux")]
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_reactor_epoll_mask(events: i32) -> u32 {
    let mut mask = 0;
    if events < 256 || events & super::SW_READ != 0 {
        mask |= libc::EPOLLIN;
    }
    if events & super::SW_WRITE != 0 {
        mask |= libc::EPOLLOUT;
    }
    if events & (1 << 12) != 0 {
        mask |= libc::EPOLLONESHOT;
    }
    if events & (1 << 11) != 0 {
        mask |= libc::EPOLLRDHUP | libc::EPOLLHUP | libc::EPOLLERR;
    }
    mask.cast_unsigned()
}

/// Kqueue actions0publish,1removed-warning,2removal-observer,5filter-warning,
///6return-error,7fresh-filter-facts;11read-add/12write-add/13read-delete/14write-delete.
/// Supply requested events for add/set and fresh socket.events for delete.
/// # Safety
/// State is live/zero-initialized/exclusive. Native effects and fresh errno after
/// removal observer occur between calls; no native pointer or borrow escapes.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_kqueue_registration(
    state: *mut RegistrationState,
    operation: u32,
    events: i32,
    removed: u32,
    result: i32,
    error: i32,
) -> i32 {
    // SAFETY: `state` is null or live, aligned and exclusively lent for this call.
    let Some(state) = (unsafe { state.as_mut() }) else {
        return -1;
    };
    if operation > 2 || state.filter > 2 {
        return -1;
    }
    if state.phase == 0 {
        if operation == 2 && removed != 0 {
            state.phase = 4;
            return 1;
        }
        state.phase = 1;
    }
    if state.phase == 2 {
        if result >= 0 {
            state.phase = 1;
        } else if operation == 2 {
            state.phase = 3;
            return 2;
        } else {
            state.phase = 4;
            return 5;
        }
    }
    if state.phase == 3 {
        if error == libc::EBADF || error == libc::ENOENT {
            state.phase = 1;
            return 7; // Ask Native to observe the next filter only after this decision.
        } else {
            state.phase = 4;
            return 6;
        }
    }
    if state.phase != 1 {
        return -1;
    }
    let filter = super::next_filter(&mut state.filter, operation, events);
    if filter == 0 {
        state.phase = 4;
        0
    } else {
        state.phase = 2;
        10 + filter
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn registration_positive_publication_and_filter_order() {
        assert_eq!(swr_v1_reactor_poll_registration(0, 0, 0, 1, 17), 0);
        assert_eq!(swr_v1_reactor_poll_registration(1, 1, 0, 1, 17), 0);
        assert_eq!(swr_v1_reactor_poll_registration(2, 1, 0, 1, 17), 0);
        unsafe {
            for operation in 0..3 {
                let mut state = RegistrationState::default();
                assert_eq!(
                    swr_v1_reactor_epoll_registration(&mut state, operation, 0, 0, 0),
                    0
                );
                assert_eq!(
                    swr_v1_reactor_epoll_registration(&mut state, operation, 0, 0, 0),
                    4
                );
                let mut state = RegistrationState::default();
                let expected = if operation == 2 {
                    [13, 14, 0]
                } else {
                    [11, 12, 0]
                };
                for action in expected {
                    assert_eq!(
                        swr_v1_reactor_kqueue_registration(
                            &mut state,
                            operation,
                            super::super::SW_READ | super::super::SW_WRITE,
                            0,
                            0,
                            0
                        ),
                        action
                    );
                }
            }
        }
    }
}
