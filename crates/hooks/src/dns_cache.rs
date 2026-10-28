//! `System::gethostbyname`'s DNS cache: a least-recently-used map from
//! `IPv4.`/`IPv6.` plus the host name to its address, with an optional expiry in
//! seconds, created on first lookup and counting hits and misses. Native code
//! resolves on a miss (c-ares or the async pool) and stores the answer here.
use std::collections::{BTreeMap, HashMap};
use std::ffi::c_void;
use std::sync::{Mutex, MutexGuard, PoisonError};
use std::time::{SystemTime, UNIX_EPOCH};

struct Entry {
    address: Vec<u8>,
    /// Unix time it expires at, or 0 for never.
    expires: i64,
    /// Its place in `Lru::order`.
    used: u64,
}

/// Upstream's `LRUCache`: expired entries keep their slot until replaced or evicted.
struct Lru {
    capacity: usize,
    entries: HashMap<Vec<u8>, Entry>,
    /// Least recently used first.
    order: BTreeMap<u64, Vec<u8>>,
    clock: u64,
}

impl Lru {
    fn new(capacity: usize) -> Self {
        Self {
            capacity,
            entries: HashMap::new(),
            order: BTreeMap::new(),
            clock: 0,
        }
    }

    fn touch(&mut self, key: &[u8]) {
        self.clock += 1;
        if let Some(entry) = self.entries.get_mut(key) {
            self.order.remove(&entry.used);
            entry.used = self.clock;
            self.order.insert(self.clock, key.to_vec());
        }
    }

    fn get(&mut self, key: &[u8], now: i64) -> Option<Vec<u8>> {
        let entry = self.entries.get(key)?;
        if entry.expires < now && entry.expires > 0 {
            return None;
        }
        let address = entry.address.clone();
        self.touch(key);
        Some(address)
    }

    fn set(&mut self, key: &[u8], address: &[u8], expire: i64, now: i64) {
        let expires = if expire <= 0 { 0 } else { now + expire };
        if let Some(entry) = self.entries.get_mut(key) {
            entry.address = address.to_vec();
            entry.expires = expires;
        } else {
            if self.entries.len() == self.capacity
                && let Some((_, oldest)) = self.order.pop_first()
            {
                self.entries.remove(&oldest);
            }
            let entry = Entry {
                address: address.to_vec(),
                expires,
                used: 0,
            };
            self.entries.insert(key.to_vec(), entry);
        }
        self.touch(key);
    }

    fn clear(&mut self) {
        self.entries.clear();
        self.order.clear();
    }
}

struct Cache {
    capacity: usize,
    expire: i64,
    lru: Option<Lru>,
    hits: usize,
    misses: usize,
}

static CACHE: Mutex<Cache> = Mutex::new(Cache {
    capacity: 1000,
    expire: 60,
    lru: None,
    hits: 0,
    misses: 0,
});

fn cache() -> MutexGuard<'static, Cache> {
    CACHE.lock().unwrap_or_else(PoisonError::into_inner)
}

fn now() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0, |elapsed| elapsed.as_secs().cast_signed())
}

/// # Safety
/// `name` holds `length` bytes.
unsafe fn key(domain: i32, name: *const u8, length: usize) -> Vec<u8> {
    let mut key = if domain == libc::AF_INET {
        b"IPv4.".to_vec()
    } else {
        b"IPv6.".to_vec()
    };
    if length > 0 {
        // SAFETY: the caller's precondition.
        key.extend_from_slice(unsafe { std::slice::from_raw_parts(name, length) });
    }
    key
}

/// `System::set_dns_cache_expire`: entries stored from now on live `expire` seconds
/// (none: forever).
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_dns_cache_expire(expire: i64) {
    cache().expire = expire;
}

/// `System::set_dns_cache_capacity`: clears and drops the cache; 0 disables it.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_dns_cache_capacity(capacity: usize) {
    let mut cache = cache();
    cache.capacity = capacity;
    cache.lru = None;
    cache.hits = 0;
    cache.misses = 0;
}

/// `System::clear_dns_cache`.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_dns_cache_clear() {
    let mut cache = cache();
    if let Some(lru) = &mut cache.lru {
        lru.clear();
    }
    cache.hits = 0;
    cache.misses = 0;
}

/// `System::get_dns_cache_hit_ratio`.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_hook_dns_cache_hit_ratio() -> f32 {
    let cache = cache();
    let total = cache.hits + cache.misses;
    #[expect(
        clippy::cast_precision_loss,
        reason = "upstream divides the counters as float"
    )]
    if total == 0 {
        0.0
    } else {
        cache.hits as f32 / total as f32
    }
}

/// Looks `name` up for `domain`, creating the cache first if enabled. On a hit,
/// `assign(out, address, length)` receives the address and this returns true.
///
/// # Safety
/// `name` holds `length` bytes; `assign` accepts `out`.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_hook_dns_cache_get(
    domain: i32,
    name: *const u8,
    length: usize,
    out: *mut c_void,
    assign: unsafe extern "C" fn(*mut c_void, *const u8, usize),
) -> bool {
    let address = {
        let mut cache = cache();
        let capacity = cache.capacity;
        if cache.lru.is_none() && capacity != 0 {
            cache.lru = Some(Lru::new(capacity));
        }
        let Some(lru) = &mut cache.lru else {
            return false;
        };
        // SAFETY: the caller's precondition.
        let found = lru.get(&unsafe { key(domain, name, length) }, now());
        if found.is_some() {
            cache.hits += 1;
        } else {
            cache.misses += 1;
        }
        found
    };
    let Some(address) = address else {
        return false;
    };
    // SAFETY: the caller's precondition; `address` is alive for the call.
    unsafe { assign(out, address.as_ptr(), address.len()) };
    true
}

/// Stores a resolved, non-empty `address` for `name`, if the cache exists.
///
/// # Safety
/// `name` holds `length` bytes and `address` `address_length`.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_hook_dns_cache_set(
    domain: i32,
    name: *const u8,
    length: usize,
    address: *const u8,
    address_length: usize,
) {
    let mut cache = cache();
    let expire = cache.expire;
    let Some(lru) = &mut cache.lru else {
        return;
    };
    if address_length == 0 {
        return;
    }
    // SAFETY: the caller's precondition.
    let address = unsafe { std::slice::from_raw_parts(address, address_length) };
    // SAFETY: the caller's precondition.
    lru.set(
        &unsafe { key(domain, name, length) },
        address,
        expire,
        now(),
    );
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn evicts_least_recently_used_and_honours_expiry() {
        let mut lru = Lru::new(2);
        lru.set(b"a", b"1", 0, 100);
        lru.set(b"b", b"2", 10, 100);
        assert_eq!(lru.get(b"a", 105), Some(b"1".to_vec()));
        lru.set(b"c", b"3", 0, 105);
        assert_eq!(lru.get(b"b", 105), None, "b was least recently used");
        assert_eq!(lru.get(b"c", 105), Some(b"3".to_vec()));
        lru.set(b"d", b"4", 1, 100);
        assert_eq!(
            lru.get(b"d", 101),
            Some(b"4".to_vec()),
            "expiry is exclusive"
        );
        assert_eq!(lru.get(b"d", 102), None);
        lru.set(b"d", b"5", 0, 102);
        assert_eq!(lru.get(b"d", 999), Some(b"5".to_vec()));
        assert_eq!(lru.entries.len(), 2);
    }

    unsafe extern "C" fn assign(out: *mut c_void, address: *const u8, length: usize) {
        let out = unsafe { &mut *out.cast::<Vec<u8>>() };
        *out = unsafe { std::slice::from_raw_parts(address, length) }.to_vec();
    }

    fn get(domain: i32, name: &str) -> Option<Vec<u8>> {
        let mut out = Vec::new();
        let hit = unsafe {
            swr_v1_hook_dns_cache_get(
                domain,
                name.as_ptr(),
                name.len(),
                (&raw mut out).cast(),
                assign,
            )
        };
        hit.then_some(out)
    }

    fn set(domain: i32, name: &str, address: &str) {
        unsafe {
            swr_v1_hook_dns_cache_set(
                domain,
                name.as_ptr(),
                name.len(),
                address.as_ptr(),
                address.len(),
            );
        }
    }

    /// One test owns the process-wide cache.
    #[test]
    fn caches_per_family_and_counts() {
        swr_v1_hook_dns_cache_capacity(1000);
        set(libc::AF_INET, "x", "1.2.3.4");
        assert_eq!(
            get(libc::AF_INET, "x"),
            None,
            "nothing is stored before the cache exists"
        );
        set(libc::AF_INET, "x", "1.2.3.4");
        set(libc::AF_INET, "y", "");
        assert_eq!(get(libc::AF_INET, "x"), Some(b"1.2.3.4".to_vec()));
        assert_eq!(get(libc::AF_INET6, "x"), None);
        assert_eq!(
            get(libc::AF_INET, "y"),
            None,
            "empty answers are not cached"
        );
        assert!((swr_v1_hook_dns_cache_hit_ratio() - 0.25).abs() < f32::EPSILON);
        swr_v1_hook_dns_cache_clear();
        assert_eq!(swr_v1_hook_dns_cache_hit_ratio(), 0.0);
        assert_eq!(get(libc::AF_INET, "x"), None);
        swr_v1_hook_dns_cache_capacity(0);
        set(libc::AF_INET, "x", "1.2.3.4");
        assert_eq!(get(libc::AF_INET, "x"), None);
        assert_eq!(
            swr_v1_hook_dns_cache_hit_ratio(),
            0.0,
            "a disabled cache counts nothing"
        );
        swr_v1_hook_dns_cache_capacity(1000);
    }
}
