//! Packet membership owns opaque native holder tokens, never native objects.
//! Removal returns ownership to C++; callbacks only run after the call returns.
use std::alloc::{Layout, alloc, dealloc};
use std::collections::HashMap;
use std::hash::{BuildHasherDefault, Hasher};

// IPC message IDs are native-generated u64 counters, not attacker-chosen strings.
// Match the native integer-key map without SipHash per packet lookup.
#[derive(Default)]
struct PacketIdHasher(u64);
impl Hasher for PacketIdHasher {
    fn write(&mut self, bytes: &[u8]) {
        for &byte in bytes {
            self.0 = self.0.wrapping_mul(257).wrapping_add(u64::from(byte));
        }
    }
    fn write_u64(&mut self, id: u64) {
        self.0 = id;
    }
    fn finish(&self) -> u64 {
        self.0.wrapping_mul(0x9e3779b97f4a7c15)
    }
}

#[derive(Clone, Copy)]
struct Location {
    index: usize,
    value: usize,
}
#[derive(Default)]
pub struct PacketPool {
    indices: HashMap<u64, Location, BuildHasherDefault<PacketIdHasher>>,
    entries: Vec<(u64, usize)>,
}
impl PacketPool {
    fn insert(&mut self, id: u64, token: usize) -> bool {
        self.insert_many(&[PoolEntry { id, token }])
    }
    fn insert_many(&mut self, values: &[PoolEntry]) -> bool {
        self.insert_values(values.iter().map(|&entry| (entry, entry.token)))
    }
    fn insert_values(
        &mut self,
        values: impl ExactSizeIterator<Item = (PoolEntry, usize)> + Clone,
    ) -> bool {
        if values.clone().any(|(entry, _)| entry.token == 0)
            || self.indices.try_reserve(values.len()).is_err()
            || self.entries.try_reserve(values.len()).is_err()
        {
            return false;
        }
        let original = self.entries.len();
        for (PoolEntry { id, token }, value) in values {
            match self.indices.entry(id) {
                std::collections::hash_map::Entry::Vacant(slot) => {
                    slot.insert(Location {
                        index: self.entries.len(),
                        value,
                    });
                    self.entries.push((id, token));
                }
                std::collections::hash_map::Entry::Occupied(_) => {
                    // Capacity may grow, but membership/ownership roll back fully.
                    for (id, _) in self.entries.drain(original..) {
                        self.indices.remove(&id);
                    }
                    return false;
                }
            }
        }
        true
    }
    fn remove(&mut self, id: u64) -> usize {
        let Some(Location { index, .. }) = self.indices.remove(&id) else {
            return 0;
        };
        let (_, token) = self.entries.swap_remove(index);
        if let Some(&(moved_id, _)) = self.entries.get(index)
            && let Some(location) = self.indices.get_mut(&moved_id)
        {
            location.index = index;
        }
        token
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_bus_pool_create() -> *mut PacketPool {
    swr_v1_bus_pool_create_capacity(0)
}
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_bus_pool_create_capacity(capacity: usize) -> *mut PacketPool {
    let mut pool = PacketPool::default();
    if pool.indices.try_reserve(capacity).is_err() || pool.entries.try_reserve(capacity).is_err() {
        return std::ptr::null_mut();
    }
    // SAFETY: `PacketPool` is not zero-sized; null is handled below.
    let pointer = unsafe { alloc(Layout::new::<PacketPool>()).cast::<PacketPool>() };
    if !pointer.is_null() {
        // SAFETY: `pointer` is a fresh, non-null allocation with `PacketPool`'s layout.
        unsafe { pointer.write(pool) };
    }
    pointer
}
/// # Safety
/// Pool is null or a live exclusive handle. Release succeeds only when empty.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_bus_pool_release(pool: *mut PacketPool) -> i32 {
    if pool.is_null() {
        return 0;
    }
    // SAFETY: non-null (checked above); a live, exclusively owned pool from create.
    if !unsafe { &*pool }.entries.is_empty() {
        return -1;
    }
    // SAFETY: as above; released exactly once.
    unsafe { pool.drop_in_place() };
    // SAFETY: allocated with this layout by create; its value was just dropped.
    unsafe { dealloc(pool.cast(), Layout::new::<PacketPool>()) };
    0
}
/// # Safety
/// Pool is null or a live handle with no concurrent mutation.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_bus_pool_len(pool: *const PacketPool) -> usize {
    // SAFETY: `pool` is null or a live pool from create.
    unsafe { pool.as_ref() }.map_or(0, |pool| pool.entries.len())
}
/// # Safety
/// Pool is null or a live handle with no concurrent mutation.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_bus_pool_find(pool: *const PacketPool, id: u64) -> usize {
    // SAFETY: `pool` is null or a live pool from create.
    unsafe { pool.as_ref() }
        .and_then(|pool| {
            pool.indices
                .get(&id)
                .map(|location| pool.entries[location.index].1)
        })
        .unwrap_or(0)
}
/// Lookup borrows the supplied native value, never its ownership token.
/// # Safety
/// Pool is null or live with no concurrent mutation. The returned opaque value
/// remains valid only while native ownership and pool membership remain live.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_bus_pool_find_value(pool: *const PacketPool, id: u64) -> usize {
    // SAFETY: `pool` is null or a live pool from create.
    unsafe { pool.as_ref() }
        .and_then(|pool| pool.indices.get(&id).map(|location| location.value))
        .unwrap_or(0)
}
/// # Safety
/// Pool is null or a live exclusive handle. Nonzero token ownership transfers
/// only on success (0); duplicates/allocation failures return -1 without transfer.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_bus_pool_insert(
    pool: *mut PacketPool,
    id: u64,
    token: usize,
) -> i32 {
    // SAFETY: `pool` is null or a live pool from create, exclusively accessed.
    if unsafe { pool.as_mut() }.is_some_and(|pool| pool.insert(id, token)) {
        0
    } else {
        -1
    }
}
/// # Safety
/// Pool is null or a live exclusive handle. Returned nonzero token is removed.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_bus_pool_take(pool: *mut PacketPool, id: u64) -> usize {
    // SAFETY: `pool` is null or a live pool from create, exclusively accessed.
    unsafe { pool.as_mut() }.map_or(0, |pool| pool.remove(id))
}
/// # Safety
/// Pool is null or a live exclusive handle. Returned nonzero token is removed.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_bus_pool_pop(pool: *mut PacketPool) -> usize {
    // SAFETY: `pool` is null or a live pool from create, exclusively accessed.
    let Some(pool) = (unsafe { pool.as_mut() }) else {
        return 0;
    };
    let Some((id, token)) = pool.entries.pop() else {
        return 0;
    };
    pool.indices.remove(&id);
    token
}
/// # Safety
/// Pool is null or a live borrowed handle; output is exclusive writable. Output
/// is unchanged on an invalid index. Enumeration order is unspecified.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_bus_pool_at(
    pool: *const PacketPool,
    index: usize,
    id: *mut u64,
) -> usize {
    // SAFETY: `pool` is null or a live pool from create.
    let Some(&(key, token)) = (unsafe { pool.as_ref() }).and_then(|pool| pool.entries.get(index))
    else {
        return 0;
    };
    if id.is_null() {
        return 0;
    }
    // SAFETY: `id` is non-null (checked above), aligned and writable per the export's contract.
    unsafe { id.write(key) };
    token
}

/// Bounded borrowed snapshot; tokens still belong to the pool.
#[repr(C)]
#[derive(Clone, Copy, Debug, Default)]
pub struct PoolEntry {
    pub id: u64,
    pub token: usize,
}

/// # Safety
/// Pool is null or a live exclusive handle. Entries are a borrowed readable,
/// disjoint array. On success all tokens transfer; on failure none transfer.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_bus_pool_insert_many(
    pool: *mut PacketPool,
    entries: *const PoolEntry,
    length: usize,
) -> i32 {
    if length > isize::MAX as usize / std::mem::size_of::<PoolEntry>()
        || (entries.is_null() && length != 0)
    {
        return -1;
    }
    // SAFETY: `pool` is null or a live pool from create, exclusively accessed.
    let Some(pool) = (unsafe { pool.as_mut() }) else {
        return -1;
    };
    let values = if length == 0 {
        &[]
    } else {
        // SAFETY: non-null and size-bounded (checked above); `length` readable entries.
        unsafe { std::slice::from_raw_parts(entries, length) }
    };
    if pool.insert_many(values) { 0 } else { -1 }
}

/// Insert owners and parallel borrowed lookup values transactionally. Rust
/// never dereferences either token. Existing inserts use owner as lookup value.
/// # Safety
/// Pool is a live exclusive handle; entries and lookup arrays cover length
/// readable elements, disjoint from the pool. On failure no owners transfer.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_bus_pool_insert_values(
    pool: *mut PacketPool,
    entries: *const PoolEntry,
    lookups: *const usize,
    length: usize,
) -> i32 {
    if length > isize::MAX as usize / std::mem::size_of::<PoolEntry>()
        || ((entries.is_null() || lookups.is_null()) && length != 0)
    {
        return -1;
    }
    // SAFETY: `pool` is null or a live pool from create, exclusively accessed.
    let Some(pool) = (unsafe { pool.as_mut() }) else {
        return -1;
    };
    let (entries, lookups) = if length == 0 {
        (&[][..], &[][..])
    } else {
        // Both are non-null and size-bounded (checked above), with `length` readable elements.
        (
            // SAFETY: as above.
            unsafe { std::slice::from_raw_parts(entries, length) },
            // SAFETY: as above.
            unsafe { std::slice::from_raw_parts(lookups, length) },
        )
    };
    if pool.insert_values(
        entries
            .iter()
            .zip(lookups)
            .map(|(&entry, &value)| (entry, value)),
    ) {
        0
    } else {
        -1
    }
}

/// # Safety
/// Pool is null or a live borrowed handle. Output is disjoint/exclusive writable
/// for capacity entries. No pointers into Rust storage escape this call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_bus_pool_snapshot(
    pool: *const PacketPool,
    start: usize,
    output: *mut PoolEntry,
    capacity: usize,
) -> usize {
    if output.is_null() || capacity > isize::MAX as usize / std::mem::size_of::<PoolEntry>() {
        return 0;
    }
    // SAFETY: `pool` is null or a live pool from create.
    let Some(pool) = (unsafe { pool.as_ref() }) else {
        return 0;
    };
    let Some(entries) = pool.entries.get(start..) else {
        return 0;
    };
    let count = entries.len().min(capacity);
    for (index, &(id, token)) in entries[..count].iter().enumerate() {
        // SAFETY: `index < count <= capacity`; `output` is non-null with `capacity` writable slots.
        unsafe { output.wrapping_add(index).write(PoolEntry { id, token }) };
    }
    count
}

/// # Safety
/// Pool is null or a live exclusive handle. Output covers capacity disjoint
/// writable tokens. Returned tokens are removed; disposal happens after return.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_bus_pool_drain(
    pool: *mut PacketPool,
    output: *mut usize,
    capacity: usize,
) -> usize {
    if output.is_null() || capacity > isize::MAX as usize / std::mem::size_of::<usize>() {
        return 0;
    }
    // SAFETY: `pool` is null or a live pool from create, exclusively accessed.
    let Some(pool) = (unsafe { pool.as_mut() }) else {
        return 0;
    };
    let count = pool.entries.len().min(capacity);
    if count == pool.entries.len() {
        for (index, &(_, token)) in pool.entries.iter().enumerate() {
            // SAFETY: `index < count <= capacity`; `output` is non-null with `capacity` writable slots.
            unsafe { output.wrapping_add(index).write(token) };
        }
        pool.entries.clear();
        pool.indices.clear();
    } else {
        let kept = pool.entries.len() - count;
        for (index, (id, token)) in pool.entries.drain(kept..).rev().enumerate() {
            pool.indices.remove(&id);
            // SAFETY: `index < count <= capacity`; `output` is non-null with `capacity` writable slots.
            unsafe { output.wrapping_add(index).write(token) };
        }
    }
    count
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeMap;
    #[test]
    fn swap_removal_and_duplicate_ownership_match_model() {
        let mut pool = PacketPool::default();
        let mut model = BTreeMap::new();
        let mut random = 0x6d2b79f5u64;
        for step in 1..=30000 {
            random = random.wrapping_mul(6364136223846793005).wrapping_add(1);
            let key = (random >> 32) % 113;
            let id = if random & 4 == 0 { key } else { u64::MAX - key };
            if random & 1 == 0 {
                let available = !model.contains_key(&id);
                assert_eq!(pool.insert(id, step), available);
                if available {
                    model.insert(id, step);
                }
            } else {
                assert_eq!(pool.remove(id), model.remove(&id).unwrap_or(0));
            }
            assert_eq!(pool.entries.len(), model.len());
            for (&key, &token) in &model {
                assert_eq!(pool.entries[pool.indices[&key].index], (key, token));
                assert_eq!(unsafe { swr_v1_bus_pool_find(&pool, key) }, token);
            }
        }
        assert!(!pool.insert(1000, 0));
    }
    #[test]
    fn bulk_insert_failure_rolls_back_membership_and_token_ownership() {
        unsafe {
            assert!(swr_v1_bus_pool_create_capacity(usize::MAX).is_null());
            let pool = swr_v1_bus_pool_create_capacity(3);
            assert!(!pool.is_null());
            assert_eq!(swr_v1_bus_pool_insert(pool, 1, 11), 0);
            for values in [
                vec![
                    PoolEntry { id: 2, token: 22 },
                    PoolEntry { id: 1, token: 99 },
                ],
                vec![
                    PoolEntry { id: 2, token: 22 },
                    PoolEntry { id: 2, token: 99 },
                ],
                vec![
                    PoolEntry { id: 2, token: 22 },
                    PoolEntry { id: 3, token: 0 },
                ],
            ] {
                assert_eq!(
                    swr_v1_bus_pool_insert_many(pool, values.as_ptr(), values.len()),
                    -1
                );
                assert_eq!(swr_v1_bus_pool_len(pool), 1);
                assert_eq!(swr_v1_bus_pool_find(pool, 1), 11);
                assert_eq!(swr_v1_bus_pool_find(pool, 2), 0);
            }
            let values = [
                PoolEntry { id: 2, token: 22 },
                PoolEntry { id: 3, token: 33 },
            ];
            assert_eq!(swr_v1_bus_pool_insert_many(pool, values.as_ptr(), 2), 0);
            assert_eq!(swr_v1_bus_pool_take(pool, 2), 22);
            assert_eq!(swr_v1_bus_pool_find(pool, 3), 33);
            assert_eq!(swr_v1_bus_pool_take(pool, 1), 11);
            assert_eq!(swr_v1_bus_pool_take(pool, 3), 33);
            assert_eq!(swr_v1_bus_pool_release(pool), 0);
        }
    }
    #[test]
    fn borrowed_values_never_replace_owner_tokens_or_grow_map_locations() {
        assert_eq!(
            std::mem::size_of::<Location>(),
            2 * std::mem::size_of::<usize>()
        );
        unsafe {
            let pool = swr_v1_bus_pool_create();
            let entries: Vec<_> = (0..257)
                .map(|id| PoolEntry {
                    id,
                    token: id as usize + 1,
                })
                .collect();
            let values: Vec<_> = (0..257).map(|id| id * 1000).collect();
            assert_eq!(
                swr_v1_bus_pool_insert_values(
                    pool,
                    entries.as_ptr(),
                    values.as_ptr(),
                    entries.len()
                ),
                0
            );
            for id in 0..257 {
                assert_eq!(swr_v1_bus_pool_find(pool, id), id as usize + 1);
                assert_eq!(swr_v1_bus_pool_find_value(pool, id), id as usize * 1000);
            }
            // Zero is a valid borrowed value; ownership remains distinguishable.
            assert_eq!(swr_v1_bus_pool_find(pool, 0), 1);
            let duplicate = [
                PoolEntry {
                    id: 999,
                    token: 123,
                },
                PoolEntry { id: 1, token: 999 },
            ];
            assert_eq!(
                swr_v1_bus_pool_insert_values(pool, duplicate.as_ptr(), values.as_ptr(), 2),
                -1
            );
            assert_eq!(swr_v1_bus_pool_find(pool, 999), 0);
            assert_eq!(swr_v1_bus_pool_find_value(pool, 1), 1000);
            assert_eq!(
                swr_v1_bus_pool_insert_values(pool, entries.as_ptr(), std::ptr::null(), 1),
                -1
            );
            assert_eq!(
                swr_v1_bus_pool_insert_values(pool, entries.as_ptr(), values.as_ptr(), usize::MAX),
                -1
            );
            for id in (0..257).step_by(2) {
                assert_eq!(swr_v1_bus_pool_take(pool, id), id as usize + 1);
                assert_eq!(swr_v1_bus_pool_find_value(pool, id), 0);
            }
            let mut remaining = [0; 257];
            let count = swr_v1_bus_pool_drain(pool, remaining.as_mut_ptr(), remaining.len());
            remaining[..count].sort_unstable();
            assert_eq!(
                &remaining[..count],
                &(1..257).step_by(2).map(|id| id + 1).collect::<Vec<_>>()
            );
            assert_eq!(swr_v1_bus_pool_find_value(pool, 1), 0);
            assert_eq!(swr_v1_bus_pool_release(pool), 0);
        }
    }
    #[test]
    fn bounded_snapshot_and_drain_transfer_every_token_once() {
        unsafe {
            let pool = swr_v1_bus_pool_create();
            assert!(!pool.is_null());
            for id in 0..97 {
                assert_eq!(swr_v1_bus_pool_insert(pool, id, id as usize + 1), 0);
            }
            let mut entries = [PoolEntry {
                id: u64::MAX,
                token: 999,
            }; 32];
            assert_eq!(
                swr_v1_bus_pool_snapshot(pool, 96, entries.as_mut_ptr(), 32),
                1
            );
            assert_eq!(
                (entries[0].id, entries[0].token, entries[1].token),
                (96, 97, 999)
            );
            assert_eq!(
                swr_v1_bus_pool_snapshot(pool, usize::MAX, entries.as_mut_ptr(), 32),
                0
            );
            assert_eq!(swr_v1_bus_pool_len(pool), 97);
            let mut seen = std::collections::BTreeSet::new();
            let mut tokens = [0; 32];
            loop {
                let count = swr_v1_bus_pool_drain(pool, tokens.as_mut_ptr(), 32);
                if count == 0 {
                    break;
                }
                for &token in &tokens[..count] {
                    assert!(seen.insert(token));
                    assert_eq!(swr_v1_bus_pool_find(pool, token as u64 - 1), 0);
                }
            }
            assert_eq!(seen, (1..=97).collect());
            assert_eq!(swr_v1_bus_pool_release(pool), 0);
        }
    }
    #[test]
    fn ffi_transfer_release_and_invalid_output() {
        unsafe {
            assert_eq!(swr_v1_bus_pool_len(std::ptr::null()), 0);
            let pool = swr_v1_bus_pool_create();
            assert!(!pool.is_null());
            assert_eq!(swr_v1_bus_pool_insert(pool, u64::MAX, 17), 0);
            assert_eq!(swr_v1_bus_pool_insert(pool, u64::MAX, 18), -1);
            assert_eq!(swr_v1_bus_pool_release(pool), -1);
            assert_eq!(swr_v1_bus_pool_find(pool, u64::MAX), 17);
            let mut id = 42;
            assert_eq!(swr_v1_bus_pool_at(pool, 1, &mut id), 0);
            assert_eq!(id, 42);
            assert_eq!(swr_v1_bus_pool_at(pool, 0, std::ptr::null_mut()), 0);
            assert_eq!(swr_v1_bus_pool_at(pool, 0, &mut id), 17);
            assert_eq!(id, u64::MAX);
            assert_eq!(swr_v1_bus_pool_pop(pool), 17);
            assert_eq!(swr_v1_bus_pool_pop(pool), 0);
            assert_eq!(swr_v1_bus_pool_release(pool), 0);
        }
    }
}
