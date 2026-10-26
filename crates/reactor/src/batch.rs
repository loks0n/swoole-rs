//! Borrow genuine target kernel arrays only during each decision. Native owns
//! registry lookup and all effects; a fresh record decode follows each callback.
#[repr(C)]
#[derive(Default)]
pub struct BatchCursor {
    pub next: usize,
    pub current: usize,
}
#[repr(C)]
#[derive(Default)]
pub struct BatchRecord {
    pub token: usize,
    pub fd: i32,
    pub mask: u32,
    pub filter: i32,
    ///0 skipped record,1 socket,2 signal,3 unknown kqueue filter.
    pub kind: u32,
}

unsafe fn record<T>(
    entries: *const T,
    count: usize,
    cursor: *mut BatchCursor,
    advance: u32,
    output: *mut BatchRecord,
    decode: fn(&T) -> BatchRecord,
) -> i32 {
    // SAFETY: `cursor` is null or live, aligned and exclusively lent for this call.
    let cursor = unsafe { cursor.as_mut() };
    // SAFETY: `output` is null or live, aligned and exclusively lent for this call.
    let output = unsafe { output.as_mut() };
    let (Some(cursor), Some(output)) = (cursor, output) else {
        return -1;
    };
    if entries.is_null() || advance > 1 {
        return -1;
    }
    if advance == 0 {
        if cursor.current >= count {
            return -1;
        }
        // SAFETY: `current < count`; `entries` is non-null with `count` initialized records.
        *output = decode(unsafe { &*entries.wrapping_add(cursor.current) });
        return 1;
    }
    while cursor.next < count {
        cursor.current = cursor.next;
        cursor.next += 1;
        // SAFETY: `current < count`; `entries` is non-null with `count` initialized records.
        let next = decode(unsafe { &*entries.wrapping_add(cursor.current) });
        if next.kind != 0 {
            *output = next;
            return 1;
        }
    }
    0
}

macro_rules! decoder {
    ($name:ident, $native:ty, $decode:expr) => {
        /// Decode the next record (advance1), or freshly decode the current one
        /// (advance0) after a Native effect. Cursor is zero initialized per batch.
        /// # Safety
        /// Entries is a genuine target C array with count initialized records,
        /// including retained initialized poll slots after a nested rebuild.
        /// Cursor/output are live, aligned, exclusive and disjoint from entries.
        /// No mutation runs during this call; no borrow survives its return.
        #[unsafe(no_mangle)]
        pub unsafe extern "C" fn $name(
            entries: *const $native,
            count: usize,
            cursor: *mut BatchCursor,
            advance: u32,
            output: *mut BatchRecord,
        ) -> i32 {
            let decode: fn(&$native) -> BatchRecord = $decode;
            // SAFETY: forwards the caller's entries, cursor and output contract.
            unsafe { record(entries, count, cursor, advance, output, decode) }
        }
    };
}
decoder!(swr_v1_reactor_poll_record, libc::pollfd, |entry| {
    let raw = entry.revents;
    BatchRecord {
        fd: entry.fd,
        kind: u32::from(raw != 0),
        mask: u32::from(raw & libc::POLLIN != 0)
            | (u32::from(raw & libc::POLLOUT != 0) << 1)
            | (u32::from(raw & (libc::POLLHUP | libc::POLLERR) != 0) << 2),
        ..BatchRecord::default()
    }
});
#[cfg(target_os = "linux")]
decoder!(swr_v1_reactor_epoll_record, libc::epoll_event, |entry| {
    BatchRecord {
        // SAFETY: `entry` is a live reference; `read_unaligned` handles the packed epoll field,
        // and `u64` holds the native token in its first `usize` bytes.
        token: unsafe { std::ptr::read_unaligned(std::ptr::addr_of!(entry.u64).cast::<usize>()) },
        mask: u32::from(entry.events & libc::EPOLLIN as u32 != 0)
            | (u32::from(entry.events & libc::EPOLLOUT as u32 != 0) << 1)
            | (u32::from(
                entry.events & (libc::EPOLLRDHUP | libc::EPOLLHUP | libc::EPOLLERR) as u32 != 0,
            ) << 2),
        kind: 1,
        ..BatchRecord::default()
    }
});
#[cfg(any(
    target_os = "macos",
    target_os = "freebsd",
    target_os = "openbsd",
    target_os = "netbsd",
    target_os = "dragonfly"
))]
decoder!(swr_v1_reactor_kqueue_record, libc::kevent, |entry| {
    let filter = entry.filter;
    BatchRecord {
        token: entry.udata as usize,
        filter: filter as i32,
        mask: u32::from(filter == libc::EVFILT_READ)
            | (u32::from(filter == libc::EVFILT_WRITE) << 1),
        kind: if entry.udata as usize == 0 {
            0
        } else if filter == libc::EVFILT_READ || filter == libc::EVFILT_WRITE {
            1
        } else if filter == libc::EVFILT_SIGNAL {
            2
        } else {
            3
        },
        ..BatchRecord::default()
    }
});

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn batch_positive_poll_skips_idle_and_freshly_decodes_current_record() {
        let mut entries = [
            libc::pollfd {
                fd: 7,
                events: libc::POLLIN,
                revents: 0,
            },
            libc::pollfd {
                fd: 8,
                events: libc::POLLIN,
                revents: libc::POLLIN,
            },
            libc::pollfd {
                fd: 9,
                events: libc::POLLOUT,
                revents: libc::POLLOUT,
            },
        ];
        let mut cursor = BatchCursor::default();
        let mut output = BatchRecord::default();
        unsafe {
            assert_eq!(
                swr_v1_reactor_poll_record(entries.as_ptr(), 3, &mut cursor, 1, &mut output),
                1
            );
            assert_eq!((output.fd, output.mask, cursor.current), (8, 1, 1));
            // Ordinary initialized record update, no callbacks or lifetime probe.
            entries[1].revents = libc::POLLOUT;
            assert_eq!(
                swr_v1_reactor_poll_record(entries.as_ptr(), 3, &mut cursor, 0, &mut output),
                1
            );
            assert_eq!((output.fd, output.mask, cursor.current), (8, 2, 1));
            assert_eq!(
                swr_v1_reactor_poll_record(entries.as_ptr(), 3, &mut cursor, 1, &mut output),
                1
            );
            assert_eq!((output.fd, output.mask), (9, 2));
            assert_eq!(
                swr_v1_reactor_poll_record(entries.as_ptr(), 3, &mut cursor, 1, &mut output),
                0
            );
        }
    }
}
