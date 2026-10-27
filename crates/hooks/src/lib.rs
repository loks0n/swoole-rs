//! Coroutine I/O policy over copied scalars. No native callbacks, storage,
//! syscalls, errno, allocation, retained borrows or context switching.
#![cfg_attr(
    not(test),
    deny(
        clippy::undocumented_unsafe_blocks,
        clippy::multiple_unsafe_ops_per_block
    )
)]

/// The original per-hook guard. Some DNS hooks intentionally do not use it.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_no_coro(reactor: bool, coroutine: bool) -> bool {
    !reactor || !coroutine
}

/// 1 install, -1 restore, 0 retain. Requested flags and installed flags differ.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_transition(requested: u32, installed: u32, bit: u32) -> i32 {
    match (requested & bit != 0, installed & bit != 0) {
        (true, false) => 1,
        (false, true) => -1,
        _ => 0,
    }
}

/// Filter only unavailable families, after native before-hook callbacks.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_filter(flags: u32, unavailable: u32) -> u32 {
    flags & !unavailable
}

/// File operation result: open's fd zero rejection is deliberate pinned policy.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_file_result(open: bool, result: i64) -> bool {
    if open { result > 0 } else { result == 0 }
}

/// Lock action: 0 syscall unchanged, 1 cooperative exclusive, 2 shared,
/// 3 unlock, -1 invalid operation. Native supplies host constants.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_flock(
    cooperative: bool,
    operation: i32,
    nonblock: i32,
    exclusive: i32,
    shared: i32,
    unlock: i32,
) -> i32 {
    if !cooperative || operation & nonblock != 0 {
        return 0;
    }
    if operation == exclusive {
        1
    } else if operation == shared {
        2
    } else if operation == unlock {
        3
    } else {
        -1
    }
}

/// -1 completed with error, 0 retry, 1 completed successfully. Unexpected
/// nonzero flock results preserve the original error completion.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_lock_result(result: i32, would_block: bool) -> i32 {
    if result == 0 {
        1
    } else if result == -1 && would_block {
        0
    } else {
        -1
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_backoff(current: f64, initial: f64, maximum: f64) -> f64 {
    if current >= maximum {
        initial
    } else {
        let doubled = current * 2.0;
        // Preserve native SW_MIN rather than f64::min's different NaN policy.
        if doubled < maximum { doubled } else { maximum }
    }
}

/// Return the native partial-progress result, preserving unsigned `size_t` to
/// `ssize_t` conversion on the supported LP64 targets.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_transfer_result(result: i64, total: u64) -> i64 {
    if result < 0 && total == 0 {
        -1
    } else {
        total.cast_signed()
    }
}

#[repr(C)]
#[derive(Debug, PartialEq, Eq)]
pub struct Transfer {
    pub total: u64,
    pub again: bool,
}

/// Receive/send-all barrier. The native catch-error call is evaluated first
/// only for a negative result; its copied `SW_WAIT` fact comes here afterward.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_transfer(
    result: i64,
    total: u64,
    requested: u64,
    wait: bool,
) -> Transfer {
    let total = total.wrapping_add(if result > 0 { result.unsigned_abs() } else { 0 });
    Transfer {
        total,
        again: (result < 0 && wait) || (result > 0 && total < requested),
    }
}

/// `io_uring` submit result: 0 finish, 1 defer, 2 sleep and retry, 3 retry,
/// -1 diagnose. Host errno constants are classified natively, without mutation.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_submit(
    result: i32,
    again: bool,
    busy: bool,
    interrupted: bool,
) -> i32 {
    if result >= 0 {
        0
    } else if again {
        1
    } else if busy {
        2
    } else if interrupted {
        3
    } else {
        -1
    }
}

#[repr(C)]
#[derive(Debug, PartialEq, Eq)]
pub struct Completion {
    pub result: i64,
    pub error: i32,
}

/// `io_uring` reports negative errno. ECANCELED intentionally maps to timeout.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_completion(result: i64, canceled: i32, timeout: i32) -> Completion {
    if result < 0 {
        #[expect(
            clippy::cast_possible_truncation,
            reason = "io_uring results are an i32 cqe.res"
        )]
        let error = result.wrapping_neg() as i32;
        Completion {
            result: -1,
            error: if error == canceled { timeout } else { error },
        }
    } else {
        Completion { result, error: 0 }
    }
}

/// Coalesce native poll readiness. Error readiness becomes requested read/write
/// only when the caller did not request the explicit error bit.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_poll_revents(
    requested: u32,
    received: u32,
    event: u32,
    read_write: u32,
    error: u32,
) -> u32 {
    received
        | if event == error && requested & error == 0 {
            requested & read_write
        } else {
            event
        }
}

/// Timer-controller actions: 1 enable, 2 add native timer, 4 install negative
/// timeout sentinel, 8 delete native timer, 16 clear native pointer.
/// operation0 starts, operation1 destroys. Native retains timer node custody.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_timer(
    operation: u32,
    enabled: bool,
    present: bool,
    sentinel: bool,
    timeout: f64,
) -> u32 {
    match operation {
        0 if timeout != 0.0 && !present => 1 | if timeout > 0.0 { 2 } else { 4 },
        1 if enabled && present => 16 | if sentinel { 0 } else { 8 },
        _ => 0,
    }
}

#[repr(C)]
#[derive(Debug, PartialEq)]
pub struct WaitForPlan {
    pub delay: f64,
    pub phase: u32,
    /// 1 native callback, 2 native sleep, 0 success, -1 cancellation, -2 invalid.
    pub action: i32,
}

/// Caller-local `wait_for` cursor. Every callback and sleep is native and finishes
/// before the next copied-fact transition; Rust keeps no closure or task pointer.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_wait_for(
    phase: u32,
    delay: f64,
    result: bool,
    initial: f64,
    maximum: f64,
) -> WaitForPlan {
    let (delay, phase, action) = match phase {
        0 => (initial, 1, 1),
        1 if result => (delay, 3, 0),
        1 => (delay, 2, 2),
        2 if result => (swr_v1_hook_backoff(delay, initial, maximum), 1, 1),
        2 => (delay, 4, -1),
        3 => (delay, 3, 0),
        4 => (delay, 4, -1),
        _ => (delay, phase, -2),
    };
    WaitForPlan {
        delay,
        phase,
        action,
    }
}

#[repr(C)]
#[derive(Debug, PartialEq, Eq)]
pub struct EventPlan {
    pub revents: u32,
    pub wake: bool,
}

/// Native `EventWaiter` queues at most one deferred wake before publishing bits.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_event_waiter(received: u32, event: u32) -> EventPlan {
    EventPlan {
        revents: received | event,
        wake: received == 0,
    }
}

/// `System::wait_event` strips error readiness and adds only requested IO bits.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_wait_revents(
    requested: u32,
    received: u32,
    read_write: u32,
    error: u32,
) -> u32 {
    if received & error != 0 {
        (received ^ error) | (requested & read_write)
    } else {
        received
    }
}

/// Native retry cursor: 1 observe IO, 2 classifier, 3 timer, 4 wait.
/// Each action completes in native code before the next copied result arrives.
#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct RetryPlan {
    pub phase: u32,
    pub action: i32,
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_retry(phase: u32, result: i64, success: bool) -> RetryPlan {
    let (phase, action) = match phase {
        1 if result < 0 => (2, 2),
        2 if success => (3, 3),
        3 if success => (4, 4),
        4 if success => (1, 1),
        1..=5 => (5, 0),
        _ => (5, -1),
    };
    RetryPlan { phase, action }
}

#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct CurlPlan {
    pub flags: u32,
    pub conflict: bool,
}

/// Local-by-value normalization; native warning must finish before installed
/// hook flags are observed again because its PHP handler may reenter hooks.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_curl_flags(flags: u32, native: u32, php: u32) -> CurlPlan {
    let conflict = flags & native != 0 && flags & php != 0;
    CurlPlan {
        flags: if conflict { flags ^ php } else { flags },
        conflict,
    }
}

/// Datagram EINTR retries bypass classification, timers and suspension.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_retry_interrupt(
    phase: u32,
    result: i64,
    success: bool,
    interrupted: bool,
) -> RetryPlan {
    if phase == 1 && result < 0 && interrupted {
        RetryPlan {
            phase: 1,
            action: 1,
        }
    } else {
        swr_v1_hook_retry(phase, result, success)
    }
}

/// Select a native coroutine field; read binding wins when both are requested.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_bound(
    event: u32,
    read: u32,
    write: u32,
    read_bound: bool,
    write_bound: bool,
) -> u32 {
    if event & read != 0 && read_bound {
        1
    } else if event & write != 0 && write_bound {
        2
    } else {
        0
    }
}

/// Closed sockets take precedence without requiring a native socket dereference.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_socket_status(closed: bool, close_wait: bool) -> u32 {
    if closed {
        1
    } else if close_wait {
        2
    } else {
        0
    }
}

/// Native error publication: retain, clear, or publish the current errno.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_check_result(result: i64, has_error: bool) -> u32 {
    if result >= 0 {
        1
    } else if !has_error {
        2
    } else {
        0
    }
}

/// Native static diagnostic string: reading, writing, or both.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_event_name(
    event: u32,
    read: u32,
    write: u32,
    read_bound: bool,
    write_bound: bool,
) -> u32 {
    if event == read {
        0
    } else if event == write {
        1
    } else if read_bound && write_bound {
        2
    } else {
        u32::from(!read_bound)
    }
}

/// Preserve the pinned two divisions rather than changing timeout rounding.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_timeval(seconds: f64, micros: f64) -> f64 {
    seconds + micros / 1000.0 / 1000.0
}

/// 0 no timeout, 1 initialize native clock, 2 inspect native elapsed time.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_timeout_action(timeout: f64, startup: f64) -> u32 {
    if timeout > 0.0 {
        if startup == 0.0 { 1 } else { 2 }
    } else {
        0
    }
}

#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct TimeoutPlan {
    pub remaining: f64,
    pub expired: bool,
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_timeout_remaining(
    timeout: f64,
    elapsed: f64,
    minimum: f64,
) -> TimeoutPlan {
    let remaining = timeout - elapsed;
    TimeoutPlan {
        remaining,
        expired: remaining < minimum,
    }
}

/// Async phases: dispatch admission, cancellable yield, completion callback.
/// 0 stop, 1 yield, 2 publish completion, 3 publish cancellation, 4 resume.
/// Native dispatch/event storage, error publication and context execution stay native.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_async_action(phase: u32, cancellable: bool, success: bool) -> i32 {
    match phase {
        0 => i32::from(success),
        1 if cancellable && !success => 3,
        1 => 2,
        2 if success => 0,
        2 => 4,
        _ => -1,
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_dns_error(
    error: i32,
    asynchronous_timeout: i32,
    resolve_timeout: i32,
) -> i32 {
    if error == asynchronous_timeout {
        resolve_timeout
    } else {
        error
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_sleep_timeout(seconds: f64, minimum: f64) -> f64 {
    if seconds < minimum { minimum } else { seconds }
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_packet_start(buffered: u64, header: u32, custom: bool) -> bool {
    buffered > 0 && (buffered >= u64::from(header) || custom)
}

/// Negative length: missing protocol length; zero: receive another header;
/// positive oversize: reject; otherwise receive/return the known packet.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_packet_length(length: i64, maximum: u32) -> i32 {
    if length < 0 {
        -1
    } else if length == 0 {
        0
    } else if length > i64::from(maximum) {
        2
    } else {
        1
    }
}

/// Result of a length-protocol body read: the packet length once complete,
/// otherwise -1 after a timeout or 0 (upstream 0f96dc478).
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_packet_result(buffered: u64, expected: i64, timed_out: bool) -> i64 {
    if buffered == expected.cast_unsigned() {
        expected
    } else if timed_out {
        -1
    } else {
        0
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_packet_window(size: u64, buffered: u64, maximum: u64) -> u64 {
    size.wrapping_sub(buffered).min(maximum)
}

#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct EofPlan {
    pub offset: u64,
    pub grow: u64,
    pub action: i32,
}

/// Native scanning has finished. Select return, overflow, bounded growth or read.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_packet_eof(
    found: i64,
    eof_length: u32,
    buffered: u64,
    size: u64,
    maximum: u32,
) -> EofPlan {
    let (offset, grow, action) = if found >= 0 {
        (
            found.unsigned_abs().wrapping_add(u64::from(eof_length)),
            0,
            1,
        )
    } else if buffered == u64::from(maximum) {
        (0, 0, -1)
    } else if buffered == size && size < u64::from(maximum) {
        (0, size.wrapping_mul(2).min(u64::from(maximum)), 2)
    } else {
        (0, 0, 0)
    };
    EofPlan {
        offset,
        grow,
        action,
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_packet_kind(length: bool, eof: bool) -> u32 {
    if length {
        1
    } else if eof {
        2
    } else {
        0
    }
}

/// Accumulate only positive vectored progress within the pinned defined `ssize_t` domain.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_vector_progress(result: i64, total: i64) -> i64 {
    if result > 0 {
        total.wrapping_add(result)
    } else {
        total
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_vector_continue(result: i64, remaining: u64) -> bool {
    result > 0 && remaining > 0
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_shutdown_admit(
    connected: bool,
    how: i32,
    read: bool,
    write: bool,
    shut_read: i32,
    shut_write: i32,
) -> bool {
    connected && !(how == shut_read && read) && !(how == shut_write && write)
}

/// Bit1 publishes read shutdown, bit2 write; zero retains native syscall failure.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_shutdown_mask(
    success: bool,
    disconnected: bool,
    how: i32,
    shut_read: i32,
    shut_write: i32,
) -> u32 {
    if !success && !disconnected {
        0
    } else if disconnected {
        3
    } else if how == shut_read {
        1
    } else if how == shut_write {
        2
    } else {
        3
    }
}

/// No binding precedes event validation, including combined/unknown event bits.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_cancel_action(bound: bool, event: u32, read: u32, write: u32) -> u32 {
    if !bound {
        0
    } else if event == read {
        1
    } else if event == write {
        2
    } else {
        3
    }
}

/// Stateless selectors over the existing native close fields. Stage1 facts are
/// acquired only after the native shutdown has returned; no shadow close state.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_close_action(
    stage: u32,
    closed: bool,
    connected: bool,
    bound: bool,
) -> i32 {
    match stage {
        0 if closed => -1,
        0 if connected => 1,
        0 => 0,
        1 if bound => 2,
        1 => 3,
        _ => -2,
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_connect_action(
    result: i32,
    interrupted: bool,
    in_progress: bool,
) -> i32 {
    if result >= 0 {
        0
    } else if interrupted {
        1
    } else if in_progress {
        2
    } else {
        -1
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_connect_option(result: i32, error: i32) -> bool {
    result < 0 || error != 0
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_liveness_error(alive: bool, error: i32, reset: i32) -> i32 {
    if alive {
        0
    } else if error != 0 {
        error
    } else {
        reset
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn packet_result_reports_timeout_on_partial_body() {
        assert_eq!(swr_v1_hook_packet_result(8, 8, false), 8);
        assert_eq!(swr_v1_hook_packet_result(8, 8, true), 8);
        assert_eq!(swr_v1_hook_packet_result(5, 8, false), 0);
        assert_eq!(swr_v1_hook_packet_result(5, 8, true), -1);
    }
    #[test]
    fn transfer_preserves_partial_error_and_wrap() {
        assert_eq!(swr_v1_hook_transfer_result(-1, 0), -1);
        assert_eq!(swr_v1_hook_transfer_result(-1, 12), 12);
        assert_eq!(
            swr_v1_hook_transfer(3, 4, 10, false),
            Transfer {
                total: 7,
                again: true
            }
        );
        assert_eq!(
            swr_v1_hook_transfer(3, 7, 10, false),
            Transfer {
                total: 10,
                again: false
            }
        );
        assert_eq!(
            swr_v1_hook_transfer(-1, 7, 10, true),
            Transfer {
                total: 7,
                again: true
            }
        );
        assert_eq!(
            swr_v1_hook_transfer(0, 7, 10, true),
            Transfer {
                total: 7,
                again: false
            }
        );
        assert_eq!(swr_v1_hook_transfer(2, u64::MAX, 10, false).total, 1);
    }
    #[test]
    fn flags_are_installed_vs_requested() {
        assert_eq!(swr_v1_hook_transition(1, 0, 1), 1);
        assert_eq!(swr_v1_hook_transition(0, 1, 1), -1);
        assert_eq!(swr_v1_hook_transition(1, 1, 1), 0);
        assert_eq!(swr_v1_hook_filter(u32::MAX, 5), u32::MAX ^ 5);
    }
    #[test]
    fn timer_sentinel_and_allocation_actions() {
        assert_eq!(swr_v1_hook_timer(0, false, false, false, 0.0), 0);
        assert_eq!(swr_v1_hook_timer(0, false, false, false, -1.0), 5);
        assert_eq!(swr_v1_hook_timer(0, false, false, false, f64::NAN), 5);
        assert_eq!(swr_v1_hook_timer(0, false, false, false, 1.0), 3);
        assert_eq!(swr_v1_hook_timer(0, false, true, false, 1.0), 0);
        assert_eq!(swr_v1_hook_timer(1, false, true, false, 1.0), 0);
        assert_eq!(swr_v1_hook_timer(1, true, true, false, 1.0), 24);
        assert_eq!(swr_v1_hook_timer(1, true, true, true, -1.0), 16);
    }

    #[test]
    fn distinct_completion_and_submit_results() {
        assert_eq!(
            swr_v1_hook_completion(-125, 125, 110),
            Completion {
                result: -1,
                error: 110
            }
        );
        assert_eq!(
            swr_v1_hook_completion(0, 125, 110),
            Completion {
                result: 0,
                error: 0
            }
        );
        assert_eq!(swr_v1_hook_submit(-1, true, true, true), 1);
        assert_eq!(swr_v1_hook_submit(1, true, true, true), 0);
    }
}
