use std::collections::HashMap;
use std::hash::{BuildHasherDefault, DefaultHasher};

/// Opaque metadata only. Native owns every address value and all pointees.
pub struct PhpEventRegistry {
    // Deterministic native integer-key map: no RandomState entropy request in
    // this metadata operation. No hash/iteration order is part of the ABI.
    sockets: HashMap<i32, usize, BuildHasherDefault<DefaultHasher>>,
}

impl PhpEventRegistry {
    fn try_insert(&mut self, fd: i32, value: usize) -> Result<(), ()> {
        if let Some(stored) = self.sockets.get_mut(&fd) {
            *stored = value;
            return Ok(());
        }
        self.sockets.try_reserve(1).map_err(|_| ())?;
        self.sockets.insert(fd, value);
        Ok(())
    }
}

/// Fallible sole-owner admission; Native raises only after Rust returns.
/// Returns0 on success,-1 for a null slot,-3 for allocation/capacity refusal.
/// An existing key is replaced without table reservation. A first owner is
/// published only after its first entry exists; refusal leaves the slot intact.
/// # Safety
/// Slot is independent aligned initialized storage, null or a live module owner.
/// Access is serialized. Addresses are opaque; no Native pointee is interpreted.
unsafe fn try_insert_slot(slot: *mut *mut PhpEventRegistry, fd: i32, value: usize) -> i32 {
    if slot.is_null() {
        return -1;
    }
    unsafe {
        if (*slot).is_null() {
            let owner = std::alloc::alloc(std::alloc::Layout::new::<PhpEventRegistry>())
                .cast::<PhpEventRegistry>();
            if owner.is_null() {
                return -3;
            }
            owner.write(PhpEventRegistry {
                sockets: HashMap::default(),
            });
            let mut owner = Box::from_raw(owner);
            if owner.try_insert(fd, value).is_err() {
                return -3;
            }
            slot.write(Box::into_raw(owner));
        } else if (&mut **slot).try_insert(fd, value).is_err() {
            return -3;
        }
    }
    0
}

/// Fallible actual Native ABI. The raw slot policy stays in one internal helper.
/// # Safety
/// Same initialized, serialized slot/token custody as try_insert_slot.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpevents_registry_try_insert(
    slot: *mut *mut PhpEventRegistry,
    fd: i32,
    value: usize,
) -> i32 {
    unsafe { try_insert_slot(slot, fd, value) }
}

/// Frozen void ABI. Its historical allocation refusal remains terminating;
/// real selected Native callers use try_insert to raise outside Rust instead.
/// # Safety
/// Same serialized slot/token custody as registry_try_insert.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpevents_registry_insert(
    slot: *mut *mut PhpEventRegistry,
    fd: i32,
    value: usize,
) {
    if unsafe { try_insert_slot(slot, fd, value) } == -3 {
        std::alloc::handle_alloc_error(std::alloc::Layout::new::<PhpEventRegistry>());
    }
}

/// # Safety
/// Non-null registry is live, owned by this module, and not concurrently changed.
/// Null means the native owner has not inserted any metadata yet.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpevents_registry_contains(
    registry: *const PhpEventRegistry,
    fd: i32,
) -> u8 {
    unsafe { registry.as_ref() }.is_some_and(|registry| registry.sockets.contains_key(&fd)) as u8
}

/// Returns copied opaque address,0 when absent. Presence remains separately
/// queryable so even a stored0 preserves unordered_map semantics.
/// # Safety
/// Same serialized live-registry custody as registry_contains.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpevents_registry_get(
    registry: *const PhpEventRegistry,
    fd: i32,
) -> usize {
    unsafe { registry.as_ref() }
        .and_then(|registry| registry.sockets.get(&fd).copied())
        .unwrap_or(0)
}

/// Removes metadata only, without touching native pointees.
/// # Safety
/// Non-null registry is live, uniquely accessed for this call and module-owned.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpevents_registry_erase(
    registry: *mut PhpEventRegistry,
    fd: i32,
) -> u8 {
    unsafe { registry.as_mut() }.is_some_and(|registry| registry.sockets.remove(&fd).is_some())
        as u8
}

/// Releases metadata storage only; native Socket/Zend objects are untouched.
/// # Safety
/// Registry is null or a uniquely owned live pointer from registry_insert.
/// Native must stop using it and discard the pointer after this call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpevents_registry_drop(registry: *mut PhpEventRegistry) {
    if !registry.is_null() {
        drop(unsafe { Box::from_raw(registry) });
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn fallible_admission_and_replacement_have_one_owner() {
        let mut owner = std::ptr::null_mut();
        unsafe {
            assert_eq!(swr_v1_phpevents_registry_try_insert(&mut owner, -7, 0), 0);
            let first = owner;
            assert_eq!(swr_v1_phpevents_registry_contains(owner, -7), 1);
            assert_eq!(swr_v1_phpevents_registry_try_insert(&mut owner, -7, 41), 0);
            assert_eq!(owner, first);
            assert_eq!(swr_v1_phpevents_registry_get(owner, -7), 41);
            assert_eq!(swr_v1_phpevents_registry_try_insert(&mut owner, 0, 29), 0);
            assert_eq!(owner, first);
            assert_eq!(swr_v1_phpevents_registry_erase(owner, -7), 1);
            assert_eq!(swr_v1_phpevents_registry_get(owner, 0), 29);
            swr_v1_phpevents_registry_drop(owner);
        }
    }
}
