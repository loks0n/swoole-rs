//! Private, bounded poll snapshot. Native retains the authoritative socket map,
//! copies/iterates it at its original point, and performs poll outside Rust.
use crate::owner::{release, try_owner};
use std::ptr;

pub struct PollSnapshot {
    entries: Vec<libc::pollfd>,
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
    try_owner(|| PollSnapshot { entries }).map_or(ptr::null_mut(), Box::into_raw)
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
