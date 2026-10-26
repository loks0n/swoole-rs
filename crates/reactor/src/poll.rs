//! Private, bounded poll snapshot. Native retains the authoritative socket map,
//! copies/iterates it at its original point, and performs poll outside Rust.
use crate::owner::{release, try_owner};
use std::ptr;

pub struct PollSnapshot {
    entries: Vec<libc::pollfd>,
    limit: usize,
}

#[repr(C)]
pub struct PollLayout {
    pub size: usize,
    pub alignment: usize,
    pub fd: usize,
    pub events: usize,
    pub revents: usize,
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_reactor_poll_layout() -> PollLayout {
    PollLayout {
        size: size_of::<libc::pollfd>(),
        alignment: align_of::<libc::pollfd>(),
        fd: std::mem::offset_of!(libc::pollfd, fd),
        events: std::mem::offset_of!(libc::pollfd, events),
        revents: std::mem::offset_of!(libc::pollfd, revents),
    }
}

/// Fallible owner/storage allocation; no panic or native effect is executed.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_reactor_poll_new(limit: usize) -> *mut PollSnapshot {
    let mut entries = Vec::new();
    if entries.try_reserve_exact(limit).is_err() {
        return ptr::null_mut();
    }
    try_owner(|| PollSnapshot { entries, limit }).map_or(ptr::null_mut(), Box::into_raw)
}

/// # Safety
/// Owner is null or a live owner from new, exclusively held and no longer used
/// by native poll. Native must never delete/free the borrowed entries pointer.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_poll_free(owner: *mut PollSnapshot) {
    // SAFETY: null or a live, exclusive owner from new, no longer used by native poll.
    unsafe { release(owner) };
}

/// # Safety
/// Owner is live/exclusive. Any previous poll call has returned. No references
/// or tokens to native sockets are retained; fd values are snapshot facts only.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_poll_reset(owner: *mut PollSnapshot) -> i32 {
    // SAFETY: `owner` is null or live, aligned and exclusively lent for this call.
    let Some(owner) = (unsafe { owner.as_mut() }) else {
        return -1;
    };
    owner.entries.clear();
    0
}

/// # Safety
/// Owner is live/exclusive and the original native registry snapshot is being
/// iterated. Capacity is fixed at construction: append never allocates.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_poll_push(
    owner: *mut PollSnapshot,
    fd: i32,
    events: i32,
) -> i32 {
    // SAFETY: `owner` is null or live, aligned and exclusively lent for this call.
    let Some(owner) = (unsafe { owner.as_mut() }) else {
        return -1;
    };
    if owner.entries.len() == owner.limit {
        return -1;
    }
    owner.entries.push(libc::pollfd {
        fd,
        events: swr_v1_reactor_poll_to(events),
        revents: 0,
    });
    0
}

/// # Safety
/// Owner is live and exclusively held. Result is the actual libc pollfd array;
/// native may access initialized entries and let poll mutate their revents.
/// Address stays stable until free, even across reset/rebuild and nested waits.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_poll_data(owner: *mut PollSnapshot) -> *mut libc::pollfd {
    // SAFETY: `owner` is null or live, aligned and exclusively lent for this call.
    let Some(owner) = (unsafe { owner.as_mut() }) else {
        return ptr::null_mut();
    };
    owner.entries.as_mut_ptr()
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_reactor_poll_to(events: i32) -> i16 {
    (if events & super::SW_READ != 0 {
        libc::POLLIN
    } else {
        0
    }) | (if events & super::SW_WRITE != 0 {
        libc::POLLOUT
    } else {
        0
    })
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_reactor_poll_from(events: i16) -> i32 {
    let mut result = 0;
    if events & libc::POLLIN != 0 {
        result |= super::SW_READ;
    }
    if events & libc::POLLOUT != 0 {
        result |= super::SW_WRITE;
    }
    if events & (libc::POLLERR | libc::POLLHUP) != 0 && events & (libc::POLLIN | libc::POLLOUT) == 0
    {
        result |= 1 << 11;
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn fixed_capacity_rebuild_resets_revents_without_moving_storage() {
        unsafe {
            let owner = swr_v1_reactor_poll_new(2);
            assert!(!owner.is_null());
            let data = swr_v1_reactor_poll_data(owner);
            assert_eq!(
                swr_v1_reactor_poll_push(owner, 11, super::super::SW_READ),
                0
            );
            assert_eq!(
                swr_v1_reactor_poll_push(owner, 12, super::super::SW_WRITE),
                0
            );
            assert_eq!(swr_v1_reactor_poll_push(owner, 13, 0), -1);
            assert_eq!((*data).fd, 11);
            assert_eq!((*data).events, libc::POLLIN);
            (*data).revents = libc::POLLHUP;
            assert_eq!(swr_v1_reactor_poll_reset(owner), 0);
            assert_eq!(swr_v1_reactor_poll_push(owner, 17, 0), 0);
            assert_eq!(swr_v1_reactor_poll_data(owner), data);
            assert_eq!((*data).fd, 17);
            assert_eq!((*data).revents, 0);
            swr_v1_reactor_poll_free(owner);
        }
    }
    #[test]
    fn translation_preserves_read_write_and_error_suppression() {
        for bits in 0..65536u32 {
            let input = bits as i16;
            let output = swr_v1_reactor_poll_from(input);
            assert_eq!(
                output & (1 << 11) != 0,
                input & (libc::POLLERR | libc::POLLHUP) != 0
                    && input & (libc::POLLIN | libc::POLLOUT) == 0
            );
            assert_eq!(
                swr_v1_reactor_poll_to(output),
                input & (libc::POLLIN | libc::POLLOUT)
            );
        }
    }
    #[test]
    fn empty_and_invalid_ffi_inputs_fail_without_storage_effects() {
        unsafe {
            assert!(swr_v1_reactor_poll_new(usize::MAX).is_null());
            assert_eq!(swr_v1_reactor_poll_reset(ptr::null_mut()), -1);
            assert_eq!(swr_v1_reactor_poll_push(ptr::null_mut(), 1, 0), -1);
            assert!(swr_v1_reactor_poll_data(ptr::null_mut()).is_null());
            swr_v1_reactor_poll_free(ptr::null_mut());
            let owner = swr_v1_reactor_poll_new(0);
            assert!(!owner.is_null());
            assert_eq!(swr_v1_reactor_poll_push(owner, 1, 0), -1);
            swr_v1_reactor_poll_free(owner);
        }
    }
}
