//! Actual target C backend event arrays; Native owns kernel handles, waits and
//! all token interpretation. Rust never resolves or destroys a Socket token.
use crate::owner::{release, try_owner};
use std::mem::MaybeUninit;
use std::ptr;

pub struct BackendEvents<T> {
    entries: Vec<MaybeUninit<T>>,
}

#[repr(C)]
pub struct BackendLayout {
    pub size: usize,
    pub alignment: usize,
    pub fields: [usize; 6],
}

// The kernel initializes returned records after Rust returns. MaybeUninit
// preserves the original output-array initialization contract without inventing
// all-zero validity or reading/dropping any stored Native token.
fn new_events<T>(count: usize) -> *mut BackendEvents<T> {
    let mut entries = Vec::new();
    if entries.try_reserve_exact(count).is_err() {
        return ptr::null_mut();
    }
    entries.resize_with(count, MaybeUninit::uninit);
    try_owner(|| BackendEvents { entries }).map_or(ptr::null_mut(), Box::into_raw)
}

unsafe fn free_events<T>(owner: *mut BackendEvents<T>) {
    // SAFETY: the caller passes null or a live, exclusive owner from `new_events`.
    unsafe { release(owner) };
}

unsafe fn event_data<T>(owner: *mut BackendEvents<T>) -> *mut T {
    // SAFETY: `owner` is null or live, aligned and exclusively lent for this call.
    let Some(owner) = (unsafe { owner.as_mut() }) else {
        return ptr::null_mut();
    };
    owner.entries.as_mut_ptr().cast::<T>()
}

#[cfg(target_os = "linux")]
mod epoll {
    use super::{BackendEvents, BackendLayout, event_data, free_events, new_events};
    pub type EpollEvents = BackendEvents<libc::epoll_event>;

    #[unsafe(no_mangle)]
    pub extern "C" fn swr_v1_reactor_epoll_new(count: usize) -> *mut EpollEvents {
        new_events(count)
    }
    /// # Safety
    /// Owner is null or live/exclusive; no Native wait or array use is active.
    #[unsafe(no_mangle)]
    pub unsafe extern "C" fn swr_v1_reactor_epoll_free(owner: *mut EpollEvents) {
        // SAFETY: forwards the caller's null-or-live, exclusive owner.
        unsafe { free_events(owner) }
    }
    /// # Safety
    /// Owner is live/exclusive. Native may access exactly its construction count
    /// of actual target `epoll_event` records until free. No Rust borrow is held.
    #[unsafe(no_mangle)]
    pub unsafe extern "C" fn swr_v1_reactor_epoll_data(
        owner: *mut EpollEvents,
    ) -> *mut libc::epoll_event {
        // SAFETY: forwards the caller's live, exclusive owner.
        unsafe { event_data(owner) }
    }
    #[unsafe(no_mangle)]
    pub extern "C" fn swr_v1_reactor_epoll_layout() -> BackendLayout {
        BackendLayout {
            size: size_of::<libc::epoll_event>(),
            alignment: align_of::<libc::epoll_event>(),
            fields: [
                std::mem::offset_of!(libc::epoll_event, events),
                std::mem::offset_of!(libc::epoll_event, u64),
                0,
                0,
                0,
                0,
            ],
        }
    }
}
#[cfg(target_os = "linux")]
pub use epoll::*;

#[cfg(any(
    target_os = "macos",
    target_os = "freebsd",
    target_os = "openbsd",
    target_os = "netbsd",
    target_os = "dragonfly"
))]
mod kqueue {
    use super::{BackendEvents, BackendLayout, event_data, free_events, new_events};
    pub type KqueueEvents = BackendEvents<libc::kevent>;

    #[unsafe(no_mangle)]
    pub extern "C" fn swr_v1_reactor_kqueue_new(count: usize) -> *mut KqueueEvents {
        new_events(count)
    }
    /// # Safety
    /// Owner is null or live/exclusive; no Native wait or array use is active.
    #[unsafe(no_mangle)]
    pub unsafe extern "C" fn swr_v1_reactor_kqueue_free(owner: *mut KqueueEvents) {
        // SAFETY: forwards the caller's null-or-live, exclusive owner.
        unsafe { free_events(owner) }
    }
    /// # Safety
    /// Owner is live/exclusive. Native may access exactly its construction count
    /// of actual target kevent records until free. No Rust borrow is held.
    #[unsafe(no_mangle)]
    pub unsafe extern "C" fn swr_v1_reactor_kqueue_data(
        owner: *mut KqueueEvents,
    ) -> *mut libc::kevent {
        // SAFETY: forwards the caller's live, exclusive owner.
        unsafe { event_data(owner) }
    }
    #[unsafe(no_mangle)]
    pub extern "C" fn swr_v1_reactor_kqueue_layout() -> BackendLayout {
        BackendLayout {
            size: size_of::<libc::kevent>(),
            alignment: align_of::<libc::kevent>(),
            fields: [
                std::mem::offset_of!(libc::kevent, ident),
                std::mem::offset_of!(libc::kevent, filter),
                std::mem::offset_of!(libc::kevent, flags),
                std::mem::offset_of!(libc::kevent, fflags),
                std::mem::offset_of!(libc::kevent, data),
                std::mem::offset_of!(libc::kevent, udata),
            ],
        }
    }
}
#[cfg(any(
    target_os = "macos",
    target_os = "freebsd",
    target_os = "openbsd",
    target_os = "netbsd",
    target_os = "dragonfly"
))]
pub use kqueue::*;

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn backend_positive_fixed_arrays_keep_address_and_native_written_records() {
        for count in [1, 3, 17, 65] {
            #[cfg(target_os = "linux")]
            unsafe {
                let owner = swr_v1_reactor_epoll_new(count);
                assert!(!owner.is_null());
                let events = swr_v1_reactor_epoll_data(owner);
                for i in 0..count {
                    (*events.add(i)).events = libc::EPOLLIN as u32;
                }
                assert_eq!(events, swr_v1_reactor_epoll_data(owner));
                for i in 0..count {
                    assert_eq!({ (*events.add(i)).events }, libc::EPOLLIN as u32);
                }
                swr_v1_reactor_epoll_free(owner);
            }
            #[cfg(target_os = "macos")]
            unsafe {
                let owner = swr_v1_reactor_kqueue_new(count);
                assert!(!owner.is_null());
                let events = swr_v1_reactor_kqueue_data(owner);
                for i in 0..count {
                    (*events.add(i)).ident = i;
                }
                assert_eq!(events, swr_v1_reactor_kqueue_data(owner));
                for i in 0..count {
                    assert_eq!({ (*events.add(i)).ident }, i);
                }
                swr_v1_reactor_kqueue_free(owner);
            }
        }
    }
}
