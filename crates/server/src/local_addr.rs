//! The server's local interface addresses, numbered from 1 in `getifaddrs` order
//! across both families. A connection stores the number of its local address
//! (`Connection::local_addr_index`) and `Server::get_local_addr` reads its text.
use core::ffi::{c_char, c_int};
use std::ffi::{CStr, CString};

struct Entry {
    index: u16,
    v6: bool,
    /// `in_addr` or `in6_addr` bytes.
    bytes: Vec<u8>,
    text: CString,
}

/// Owned by `Server::local_addrs`.
pub struct LocalAddrs {
    entries: Vec<Entry>,
}

impl LocalAddrs {
    fn push(&mut self, v6: bool, bytes: &[u8]) {
        let index = u16::try_from(self.entries.len() + 1).unwrap_or(u16::MAX);
        self.entries.push(Entry {
            index,
            v6,
            bytes: bytes.to_vec(),
            text: ntop(v6, bytes),
        });
    }

    fn index(&self, v6: bool, bytes: &[u8]) -> u16 {
        self.entries
            .iter()
            .find(|entry| entry.v6 == v6 && entry.bytes == bytes)
            .map_or(0, |entry| entry.index)
    }

    fn text(&self, v6: bool, index: u16) -> Option<&CStr> {
        self.entries
            .iter()
            .find(|entry| entry.v6 == v6 && entry.index == index)
            .map(|entry| entry.text.as_c_str())
    }
}

unsafe extern "C" {
    // The `libc` crate does not bind it.
    fn inet_ntop(
        af: c_int,
        src: *const core::ffi::c_void,
        dst: *mut c_char,
        size: libc::socklen_t,
    ) -> *const c_char;
}

/// `inet_ntop`, as `network::Address::get_addr` formats.
fn ntop(v6: bool, bytes: &[u8]) -> CString {
    let family = if v6 { libc::AF_INET6 } else { libc::AF_INET };
    let mut out = [0 as c_char; 64];
    let len = libc::socklen_t::try_from(out.len()).unwrap_or(0);
    // SAFETY: `bytes` holds an address of `family` and `out` has `len` bytes.
    let text = unsafe { inet_ntop(family, bytes.as_ptr().cast(), out.as_mut_ptr(), len) };
    if text.is_null() {
        return CString::default();
    }
    // SAFETY: `inet_ntop` wrote a terminated string into `out`.
    unsafe { CStr::from_ptr(out.as_ptr()) }.to_owned()
}

/// # Safety
/// `addr` points at an `in_addr`, or an `in6_addr` when `v6`, live for `'a`.
unsafe fn address_bytes<'a>(v6: bool, addr: *const u8) -> &'a [u8] {
    let len = if v6 { 16 } else { 4 };
    // SAFETY: the caller passes an address of the family.
    unsafe { core::slice::from_raw_parts(addr, len) }
}

/// Reads the interfaces that are up. Null when `getifaddrs` fails, with `errno` set.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_server_local_addrs_new() -> *mut LocalAddrs {
    let mut list: *mut libc::ifaddrs = core::ptr::null_mut();
    // SAFETY: `list` is a valid out pointer.
    if unsafe { libc::getifaddrs(&raw mut list) } != 0 {
        return core::ptr::null_mut();
    }
    let mut addrs = LocalAddrs {
        entries: Vec::new(),
    };
    let mut cursor = list;
    while !cursor.is_null() {
        // SAFETY: `cursor` is a node of the list `getifaddrs` returned.
        let ifa = unsafe { &*cursor };
        cursor = ifa.ifa_next;
        if ifa.ifa_addr.is_null() || ifa.ifa_flags & libc::IFF_UP.cast_unsigned() == 0 {
            continue;
        }
        // SAFETY: a non-null `ifa_addr` points at a socket address.
        let family = c_int::from(unsafe { (*ifa.ifa_addr).sa_family });
        if family == libc::AF_INET {
            // SAFETY: an `AF_INET` address is a `sockaddr_in`.
            let sin = unsafe { &*ifa.ifa_addr.cast::<libc::sockaddr_in>() };
            addrs.push(false, &sin.sin_addr.s_addr.to_ne_bytes());
        } else if family == libc::AF_INET6 {
            // SAFETY: an `AF_INET6` address is a `sockaddr_in6`.
            let sin6 = unsafe { &*ifa.ifa_addr.cast::<libc::sockaddr_in6>() };
            addrs.push(true, &sin6.sin6_addr.s6_addr);
        }
    }
    // SAFETY: `list` came from `getifaddrs` and is freed once.
    unsafe { libc::freeifaddrs(list) };
    Box::into_raw(Box::new(addrs))
}

/// # Safety
/// `addrs` is null or came from `swr_v1_server_local_addrs_new` and is not used again.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_server_local_addrs_free(addrs: *mut LocalAddrs) {
    if !addrs.is_null() {
        // SAFETY: the caller transfers the box back.
        drop(unsafe { Box::from_raw(addrs) });
    }
}

/// The number of the local address `addr` (`in_addr`, or `in6_addr` when `v6`), 0 when unknown.
///
/// # Safety
/// `addrs` is null or live; `addr` points at an address of the family.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_server_local_addr_index(
    addrs: *const LocalAddrs,
    v6: bool,
    addr: *const u8,
) -> u16 {
    // SAFETY: the caller passes a live table or null.
    let Some(addrs) = (unsafe { addrs.as_ref() }) else {
        return 0;
    };
    // SAFETY: the caller passes an address of the family.
    let bytes = unsafe { address_bytes(v6, addr) };
    addrs.index(v6, bytes)
}

/// The text of local address `index`; the loopback address when unknown. Valid
/// while `addrs` lives.
///
/// # Safety
/// `addrs` is null or live.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_server_local_addr(
    addrs: *const LocalAddrs,
    v6: bool,
    index: u16,
) -> *const c_char {
    // SAFETY: the caller passes a live table or null.
    let found = unsafe { addrs.as_ref() }.and_then(|addrs| addrs.text(v6, index));
    found
        .unwrap_or(if v6 { c"::1" } else { c"127.0.0.1" })
        .as_ptr()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn numbers_both_families_in_order() {
        let mut addrs = LocalAddrs {
            entries: Vec::new(),
        };
        addrs.push(false, &[127, 0, 0, 1]);
        let mut six = [0u8; 16];
        six[15] = 1;
        addrs.push(true, &six);
        addrs.push(false, &[10, 0, 0, 2]);
        assert_eq!(addrs.index(false, &[10, 0, 0, 2]), 3, "v4 after v6");
        assert_eq!(addrs.index(true, &six), 2, "v6");
        assert_eq!(addrs.index(false, &[1, 2, 3, 4]), 0, "unknown");
        assert_eq!(addrs.text(false, 3), Some(c"10.0.0.2"), "inet_ntop text");
        assert_eq!(addrs.text(true, 2), Some(c"::1"), "v6 text");
        assert_eq!(addrs.text(true, 3), None, "index of the other family");
    }

    #[test]
    fn reads_the_interfaces_and_falls_back_to_loopback() {
        let addrs = swr_v1_server_local_addrs_new();
        assert!(!addrs.is_null(), "getifaddrs works here");
        let loopback = [127u8, 0, 0, 1];
        // SAFETY: live table and a 4-byte address.
        let index = unsafe { swr_v1_server_local_addr_index(addrs, false, loopback.as_ptr()) };
        assert_ne!(index, 0, "lo is up");
        // SAFETY: live table; the text lives with it.
        let text = unsafe { CStr::from_ptr(swr_v1_server_local_addr(addrs, false, index)) };
        assert_eq!(text, c"127.0.0.1", "loopback text");
        // SAFETY: live table.
        let missing = unsafe { CStr::from_ptr(swr_v1_server_local_addr(addrs, true, 0)) };
        assert_eq!(missing, c"::1", "unknown v6 index");
        // SAFETY: freed once.
        unsafe { swr_v1_server_local_addrs_free(addrs) };
    }
}
