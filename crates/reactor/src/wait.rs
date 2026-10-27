//! kqueue's timeout policy. Native builds the `timespec`.
#[repr(C)]
pub struct KqueueTimeout {
    pub seconds: i64,
    pub nanoseconds: i64,
    pub finite: u32,
}

/// Preserve kqueue's positive-timeout priority over deferred work, unlike the
/// poll/epoll Native get_timeout_msec helper. Native constructs its timespec.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_reactor_kqueue_timeout(milliseconds: i32, deferred: u32) -> KqueueTimeout {
    if milliseconds > 0 {
        KqueueTimeout {
            seconds: i64::from(milliseconds / 1000),
            nanoseconds: i64::from(milliseconds % 1000) * 1_000_000,
            finite: 1,
        }
    } else {
        KqueueTimeout {
            seconds: 0,
            nanoseconds: 0,
            finite: u32::from(deferred != 0),
        }
    }
}
