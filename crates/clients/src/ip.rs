//! Numeric address grammar over borrowed initialized bytes. Native sockaddr
//! layouts, publication and resolver/errno effects stay outside Rust.
use std::net::{Ipv4Addr, Ipv6Addr};
#[repr(C)]
pub struct ClientsIp {
    pub bytes: [u8; 16],
    pub length: u32,
}
fn ipv4(text: &str, allow_zeroes: bool) -> Option<Ipv4Addr> {
    let mut octets = [0u8; 4];
    let mut parts = text.split('.');
    for octet in &mut octets {
        let part = parts.next()?;
        if part.is_empty() || (!allow_zeroes && part.len() > 1 && part.starts_with('0')) {
            return None;
        }
        let mut value = 0u16;
        for byte in part.bytes() {
            if !byte.is_ascii_digit() {
                return None;
            }
            value = value.checked_mul(10)?.checked_add(u16::from(byte - b'0'))?;
            if value > 255 {
                return None;
            }
        }
        *octet = value as u8;
    }
    if parts.next().is_some() {
        return None;
    }
    Some(Ipv4Addr::from(octets))
}
fn ipv6(text: &str, allow_zeroes: bool) -> Option<Ipv6Addr> {
    if !text.contains('.') {
        return text.parse().ok();
    }
    let colon = text.rfind(':')?;
    let suffix = ipv4(&text[colon + 1..], allow_zeroes)?.octets();
    // Replace the dotted tail with two hex groups in bounded caller-local
    // storage. This preserves native Apple decimal-leading-zero grammar without
    // introducing an allocation/formatting effect into numeric parsing.
    let prefix = &text.as_bytes()[..=colon];
    let mut normalized = [0u8; 128];
    if prefix.len() > normalized.len() - 9 {
        return None;
    }
    normalized[..prefix.len()].copy_from_slice(prefix);
    let mut end = prefix.len();
    for (index, value) in [
        u16::from_be_bytes([suffix[0], suffix[1]]),
        u16::from_be_bytes([suffix[2], suffix[3]]),
    ]
    .into_iter()
    .enumerate()
    {
        if index != 0 {
            normalized[end] = b':';
            end += 1;
        }
        let mut started = false;
        for shift in [12, 8, 4, 0] {
            let nibble = ((value >> shift) & 15) as usize;
            if nibble != 0 || started || shift == 0 {
                normalized[end] = b"0123456789abcdef"[nibble];
                end += 1;
                started = true;
            }
        }
    }
    std::str::from_utf8(&normalized[..end]).ok()?.parse().ok()
}
/// # Safety
/// Input denotes `length` initialized readable bytes, or null for length0. Native
/// std::string callers pass their full bytes; parsing stops at the first NUL to
/// preserve their original c_str/inet_pton boundary. No pointer is retained.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_clients_ip(
    version: u8,
    data: *const u8,
    length: usize,
    allow_zeroes: u8,
) -> ClientsIp {
    let mut result = ClientsIp {
        bytes: [0; 16],
        length: 0,
    };
    if data.is_null() || length > isize::MAX as usize {
        return result;
    }
    let input = unsafe { std::slice::from_raw_parts(data, length) };
    let input = &input[..input.iter().position(|&b| b == 0).unwrap_or(input.len())];
    let Ok(text) = std::str::from_utf8(input) else {
        return result;
    };
    match version {
        4 => {
            if let Ok(ip) = ipv4(text, allow_zeroes != 0).ok_or(()) {
                result.bytes[..4].copy_from_slice(&ip.octets());
                result.length = 4;
            }
        }
        6 => {
            if let Ok(ip) = ipv6(text, allow_zeroes != 0).ok_or(()) {
                result.bytes = ip.octets();
                result.length = 16;
            }
        }
        _ => {}
    }
    result
}
/// # Safety
/// Address denotes exactly4 (version4) or16 (version6) initialized bytes. No
/// pointer is retained. Original IPv4 policy recognizes only127.0.0.1, not /8.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_clients_loopback(version: u8, address: *const u8) -> u8 {
    let length = match version {
        4 => 4,
        6 => 16,
        _ => return 0,
    };
    if address.is_null() {
        return 0;
    }
    let bytes = unsafe { std::slice::from_raw_parts(address, length) };
    u8::from(if version == 4 {
        bytes == [127, 0, 0, 1]
    } else {
        bytes[..15].iter().all(|&b| b == 0) && bytes[15] == 1
    })
}

#[repr(C)]
pub struct ClientsIpText {
    pub bytes: [u8; 40],
    pub length: u32,
}
/// # Safety
/// Input denotes4 (version4) or16 (version6) initialized address bytes. No pointer
/// is retained. DNS IPv6 output deliberately keeps all eight four-digit groups.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_clients_ip_text(version: u8, address: *const u8) -> ClientsIpText {
    let mut output = ClientsIpText {
        bytes: [0; 40],
        length: 0,
    };
    let length = match version {
        4 => 4,
        6 => 16,
        _ => return output,
    };
    if address.is_null() {
        return output;
    }
    let bytes = unsafe { std::slice::from_raw_parts(address, length) };
    let mut end = 0;
    if version == 4 {
        for (index, &byte) in bytes.iter().enumerate() {
            if index != 0 {
                output.bytes[end] = b'.';
                end += 1;
            }
            if byte >= 100 {
                output.bytes[end] = b'0' + byte / 100;
                end += 1;
            }
            if byte >= 10 {
                output.bytes[end] = b'0' + byte / 10 % 10;
                end += 1;
            }
            output.bytes[end] = b'0' + byte % 10;
            end += 1;
        }
    } else {
        for (index, &byte) in bytes.iter().enumerate() {
            if index != 0 && index % 2 == 0 {
                output.bytes[end] = b':';
                end += 1;
            }
            output.bytes[end] = b"0123456789abcdef"[usize::from(byte >> 4)];
            output.bytes[end + 1] = b"0123456789abcdef"[usize::from(byte & 15)];
            end += 2;
        }
    }
    output.length = end as u32;
    output
}
