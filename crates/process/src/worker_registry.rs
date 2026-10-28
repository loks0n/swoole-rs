//! The server's worker lookup, owned in Rust behind an opaque handle. It maps a
//! worker's pid to its native `Worker*`, replacing `Server::get_worker_by_pid`'s
//! event-worker scan and user-map branch. Native registers a worker when it spawns
//! and unregisters it when it is reaped or detached; fork and every `Worker` field
//! stay native. The detached-process set stays C++ for now (see the follow-up).

use std::collections::HashMap;
use std::ffi::{c_int, c_void};

/// pid -> native `Worker*`.
#[derive(Default)]
pub struct WorkerRegistry {
    workers: HashMap<c_int, *mut c_void>,
}

/// Create an empty registry. Native frees it with [`swr_v1_process_worker_registry_free`].
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_process_worker_registry_new() -> *mut WorkerRegistry {
    Box::into_raw(Box::<WorkerRegistry>::default())
}

/// Free a registry.
///
/// # Safety
/// `registry` is null or a live handle from `_new`, not freed before.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_process_worker_registry_free(registry: *mut WorkerRegistry) {
    if registry.is_null() {
        return;
    }
    // SAFETY: the caller lends a live handle previously leaked by `_new`.
    drop(unsafe { Box::from_raw(registry) });
}

/// Register (or overwrite) the worker at `pid` with its native pointer.
///
/// # Safety
/// `registry` is a live handle; `worker` is an opaque pointer the registry only stores.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_process_worker_registry_register(
    registry: *mut WorkerRegistry,
    pid: c_int,
    worker: *mut c_void,
) {
    // SAFETY: the caller lends a live registry handle.
    let registry = unsafe { &mut *registry };
    registry.workers.insert(pid, worker);
}

/// Remove the worker at `pid`. Returns whether one was present.
///
/// # Safety
/// `registry` is a live handle.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_process_worker_registry_unregister(
    registry: *mut WorkerRegistry,
    pid: c_int,
) -> bool {
    // SAFETY: the caller lends a live registry handle.
    let registry = unsafe { &mut *registry };
    registry.workers.remove(&pid).is_some()
}

/// The native pointer registered for `pid`, or null.
///
/// # Safety
/// `registry` is a live handle.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_process_worker_registry_lookup(
    registry: *const WorkerRegistry,
    pid: c_int,
) -> *mut c_void {
    // SAFETY: the caller lends a live registry handle.
    let registry = unsafe { &*registry };
    registry
        .workers
        .get(&pid)
        .copied()
        .unwrap_or(std::ptr::null_mut())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn registry() -> *mut WorkerRegistry {
        swr_v1_process_worker_registry_new()
    }

    #[test]
    fn registers_looks_up_and_unregisters() {
        let reg = registry();
        let mut worker_a = 0u8;
        let a = std::ptr::from_mut(&mut worker_a).cast::<c_void>();
        unsafe {
            swr_v1_process_worker_registry_register(reg, 100, a);
            assert_eq!(swr_v1_process_worker_registry_lookup(reg, 100), a);
            assert!(swr_v1_process_worker_registry_lookup(reg, 999).is_null());
            assert!(swr_v1_process_worker_registry_unregister(reg, 100));
            assert!(!swr_v1_process_worker_registry_unregister(reg, 100));
            assert!(swr_v1_process_worker_registry_lookup(reg, 100).is_null());
            swr_v1_process_worker_registry_free(reg);
        }
    }

    #[test]
    fn free_handles_null() {
        unsafe { swr_v1_process_worker_registry_free(std::ptr::null_mut()) };
    }
}
