//! Copied worker/process transitions. Native alone executes callbacks and owns stores.
#![cfg_attr(
    not(test),
    deny(
        clippy::undocumented_unsafe_blocks,
        clippy::multiple_unsafe_ops_per_block
    )
)]
pub mod affinity;
pub mod signal;
#[cfg(target_os = "linux")]
pub mod signalfd;
pub mod task_file;
pub mod wait;
pub mod worker_registry;
use std::ffi::c_int;
#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ExitObservation {
    ///0 stop;1 invoke `WorkerExit` then observe reactor again;2 capture fresh clock/settings.
    pub action: u32,
    pub callback_called: bool,
}
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_process_worker_exit(
    can_exit: bool,
    callback_present: bool,
    callback_called: bool,
) -> ExitObservation {
    if can_exit {
        ExitObservation {
            action: 0,
            callback_called,
        }
    } else if callback_present && !callback_called {
        ExitObservation {
            action: 1,
            callback_called: true,
        }
    } else {
        ExitObservation {
            action: 2,
            callback_called,
        }
    }
}
#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ExitBudget {
    pub timed_out: bool,
    pub update_timeout: bool,
    pub timeout_msec: i32,
}
/// Native preserves its original narrowing to int before entry. Signed overflow
/// of positive remaining*1000 is an original undefined-input exclusion.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_process_exit_budget(remaining: i32, timeout_msec: i32) -> ExitBudget {
    if remaining <= 0 {
        ExitBudget {
            timed_out: true,
            update_timeout: false,
            timeout_msec,
        }
    } else {
        let limit = remaining.wrapping_mul(1000);
        ExitBudget {
            timed_out: false,
            update_timeout: timeout_msec < 0 || timeout_msec > limit,
            timeout_msec: if timeout_msec < 0 || timeout_msec > limit {
                limit
            } else {
                timeout_msec
            },
        }
    }
}
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_process_discard_data(
    present: bool,
    closed: bool,
    disable_notify: bool,
    discard_timeout: bool,
) -> bool {
    if present {
        closed
    } else {
        !disable_notify || discard_timeout
    }
}
///0 ordinary task,1 pipe message,2 shutdown,3 command. No callback executes here.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_process_task_action(pipe: bool, shutdown: bool, command: bool) -> u32 {
    if pipe {
        1
    } else if shutdown {
        2
    } else if command {
        3
    } else {
        0
    }
}
/// Pipe-message prohibition precedes NOREPLY, matching native diagnostic order.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_process_finish_error(pipe: bool, no_reply: bool) -> u32 {
    if pipe {
        1
    } else if no_reply {
        2
    } else {
        0
    }
}
/// The callback result flag wins over the coroutine result flag.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_process_result_flags(
    flags: i32,
    callback: bool,
    coroutine: bool,
    callback_flag: i32,
    coroutine_flag: i32,
) -> i32 {
    flags
        | if callback {
            callback_flag
        } else if coroutine {
            coroutine_flag
        } else {
            0
        }
}
/// Ordinary manager-loop reload selection:0none,1all workers,2task workers.
/// Signal callbacks and `Server::reload` itself stay native.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_process_reload_action(all: bool, task: bool) -> u32 {
    if all {
        1
    } else if task {
        2
    } else {
        0
    }
}
/// Reload kill result:0 finish this attempt,1 erase stale PID and continue,2 warn then stop.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_process_reload_kill(
    failed: bool,
    no_child: bool,
    no_process: bool,
) -> u32 {
    if !failed {
        0
    } else if no_child || no_process {
        1
    } else {
        2
    }
}
/// SIGRTMIN is a runtime value on Linux and undefined elsewhere (upstream guards
/// it with `#ifdef SIGRTMIN`).
#[cfg(target_os = "linux")]
fn is_sigrtmin(signo: c_int) -> bool {
    signo == libc::SIGRTMIN()
}
#[cfg(not(target_os = "linux"))]
fn is_sigrtmin(_signo: c_int) -> bool {
    false
}
/// `Manager::signal_handler`'s action for `signo`:0 none,1 stop (SIGTERM),
/// 2 reload all workers (SIGUSR1),3 reload workers only (SIGUSR2),4 read a worker
/// message (SIGIO),5 force-kill if armed (SIGALRM),6 reopen the logger (SIGWINCH or
/// SIGRTMIN). The manager-pid guard and every effect stay native.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_process_manager_signal_action(signo: c_int) -> u32 {
    if signo == libc::SIGTERM {
        1
    } else if signo == libc::SIGUSR1 {
        2
    } else if signo == libc::SIGUSR2 {
        3
    } else if signo == libc::SIGIO {
        4
    } else if signo == libc::SIGALRM {
        5
    } else if signo == libc::SIGWINCH || is_sigrtmin(signo) {
        6
    } else {
        0
    }
}
/// `Server::worker_signal_handler`'s action for `signo`:0 none,1 terminate
/// (SIGTERM),2 reopen the logger (SIGWINCH or SIGRTMIN). The running/worker guard
/// and every effect stay native; SIGTERM's async-vs-sync stop is a native detail.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_process_worker_signal_action(signo: c_int) -> u32 {
    if signo == libc::SIGTERM {
        1
    } else if signo == libc::SIGWINCH || is_sigrtmin(signo) {
        2
    } else {
        0
    }
}
/// Held by tests that install process-wide signal state (handlers, the signalfd
/// mask), which `cargo test`'s parallel threads would otherwise race on (#534).
#[cfg(test)]
pub(crate) fn signal_state_lock() -> std::sync::MutexGuard<'static, ()> {
    static STATE: std::sync::Mutex<()> = std::sync::Mutex::new(());
    STATE
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn worker_exit_refreshes_after_callback() {
        let first = swr_v1_process_worker_exit(false, true, false);
        assert_eq!(
            first,
            ExitObservation {
                action: 1,
                callback_called: true
            }
        );
        assert_eq!(
            swr_v1_process_worker_exit(true, true, first.callback_called).action,
            0
        );
        assert_eq!(
            swr_v1_process_worker_exit(false, true, first.callback_called).action,
            2
        );
        assert_eq!(
            swr_v1_process_exit_budget(3, -1),
            ExitBudget {
                timed_out: false,
                update_timeout: true,
                timeout_msec: 3000
            }
        );
        assert_eq!(
            swr_v1_process_exit_budget(0, 20),
            ExitBudget {
                timed_out: true,
                update_timeout: false,
                timeout_msec: 20
            }
        );
    }
    #[test]
    fn diagnostic_and_mode_precedence() {
        assert_eq!(swr_v1_process_finish_error(true, true), 1);
        assert_eq!(swr_v1_process_task_action(true, true, true), 1);
        assert_eq!(swr_v1_process_reload_action(true, true), 1);
        assert_eq!(swr_v1_process_reload_action(false, true), 2);
        assert_eq!(swr_v1_process_reload_kill(false, true, true), 0);
    }
}
