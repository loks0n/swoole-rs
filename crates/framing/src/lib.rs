//! Callback-free packet decisions and immutable MIME policy; native IO stays native.
#![expect(
    clippy::missing_safety_doc,
    reason = "every export is covered by the module-local C contract"
)]
use std::slice;
mod mime;

#[repr(C)]
#[derive(Default)]
pub struct State {
    pub mode: u32,
    pub phase: u32,
    pub head: u32,
    pub recv: u32,
    pub packet: i64,
    pub again: u32,
}
#[repr(C)]
pub struct Snapshot {
    pub len: usize,
    pub cap: usize,
    pub offset: i64,
    pub result: i64,
    pub data: *const u8,
    pub eof: *const u8,
    pub eof_len: u32,
    pub max: u32,
    pub length_offset: u32,
    pub page: u32,
    pub flags: u32,
}
#[repr(C)]
pub struct Action {
    pub kind: u32,
    pub status: i32,
    pub value: u64,
}
// Actions: done0, recv1, catch2, advance3, get-length4, resize5, arm6,
// dispatch7, clear-wait8, reduce9, clear10, split11, offset12, pending13,
// log-system14, log-malformed15, log-no-length16, log-too-large17, clear-skip18.
const REMOVED: u32 = 1;
const WAIT: u32 = 2;
const SKIP: u32 = 4;
const TLS: u32 = 8;
const SPLIT: u32 = 16;
const DYNAMIC: u32 = 32;
fn done(status: i32) -> Action {
    Action {
        kind: 0,
        status,
        value: 0,
    }
}
fn emit(s: &mut State, next: u32, kind: u32, value: u64) -> Action {
    s.phase = next;
    Action {
        kind,
        status: 0,
        value,
    }
}
unsafe fn bytes<'a>(p: *const u8, n: usize) -> Option<&'a [u8]> {
    if n == 0 {
        Some(&[])
    } else if p.is_null() || n > isize::MAX as usize {
        None
    } else {
        Some(unsafe { slice::from_raw_parts(p, n) })
    }
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_framing_step(state: *mut State, input: *const Snapshot) -> Action {
    let (Some(s), Some(i)) = (unsafe { state.as_mut() }, unsafe { input.as_ref() }) else {
        return done(-1);
    };
    if i.len > i.cap {
        return done(-1);
    }
    loop {
        match (s.mode, s.phase) {
            (_, 900) => return done(-1),
            (_, 901) => return done(0),
            (0, 0) => {
                if i.flags & DYNAMIC != 0 && s.head == 0 {
                    return done(-1);
                };
                s.recv = 0;
                if i.flags & SKIP != 0 {
                    return emit(s, 2, 18, 0);
                }
                s.phase = 1;
            }
            (0, 1) => {
                if i.flags & REMOVED != 0 {
                    return done(0);
                };
                s.recv = if i.offset > 0 {
                    (i.offset as u64).wrapping_sub(i.len as u64) as u32
                } else {
                    i.length_offset.wrapping_add(s.head)
                };
                if s.recv as usize > i.cap - i.len {
                    return done(-1);
                };
                return emit(s, 3, 1, s.recv as u64);
            }
            (0, 2) => return emit(s, 6, 4, 0),
            (0, 3) => {
                if i.result < 0 {
                    return emit(s, 4, 2, 0);
                }
                if i.result == 0 {
                    return done(-1);
                };
                return emit(s, 5, 3, i.result as u64);
            }
            (0, 4) | (1, 2) => {
                if i.result == 3 {
                    return done(-1);
                }
                if i.result == 4 {
                    return emit(s, 901, 14, s.recv as u64);
                }
                return done(0);
            }
            (0, 5) => {
                if i.flags & WAIT != 0 {
                    if i.offset >= 0 && i.len >= i.offset as usize {
                        s.phase = 9
                    } else if i.flags & TLS != 0 {
                        s.phase = 1
                    } else {
                        return done(0);
                    }
                } else {
                    s.phase = 2
                }
            }
            (0, 6) => {
                s.packet = i.result;
                if s.packet < 0 {
                    return emit(s, 900, 15, 0);
                }
                if s.packet == 0 {
                    return if i.len == s.recv as usize {
                        emit(s, 900, 16, 0)
                    } else {
                        done(0)
                    };
                }
                if s.packet > i.max as i64 {
                    return emit(s, 900, 17, s.packet as u64);
                }
                if i.cap < (s.packet as usize) {
                    return emit(s, 7, 5, s.packet as u64);
                }
                s.phase = 7;
            }
            (0, 7) => return emit(s, 8, 6, s.packet as u64),
            (0, 8) => {
                s.phase = if i.offset >= 0 && i.len >= i.offset as usize {
                    9
                } else {
                    1
                };
            }
            (0, 9) => return emit(s, 10, 7, i.offset as u64),
            (0, 10) => {
                if i.result < 0 {
                    return done(-1);
                }
                if i.flags & REMOVED != 0 {
                    return done(0);
                }
                return emit(s, 11, 8, 0);
            }
            (0, 11) => {
                if i.offset >= 0 && i.len > i.offset as usize {
                    return emit(s, 2, 9, i.offset as u64);
                }
                return emit(s, 12, 10, 0);
            }
            (0, 12) => {
                if i.flags & TLS != 0 {
                    s.phase = 1
                } else {
                    return done(0);
                }
            }
            (1, 0) => {
                let n = (i.cap - i.len).min(8192);
                return emit(s, 1, 1, n as u64);
            }
            (1, 1) => {
                if i.result < 0 {
                    return emit(s, 2, 2, 0);
                }
                if i.result == 0 {
                    return done(-1);
                }
                return emit(s, 3, 3, i.result as u64);
            }
            (1, 3) => {
                if i.len < (i.eof_len as usize) {
                    return done(0);
                }
                if i.flags & SPLIT != 0 {
                    return emit(s, 4, 11, 0);
                }
                let (Some(data), Some(eof)) = (unsafe { bytes(i.data, i.len) }, unsafe {
                    bytes(i.eof, i.eof_len as usize)
                }) else {
                    return done(-1);
                };
                if data.ends_with(eof) {
                    return emit(s, 5, 12, i.len as u64);
                }
                s.phase = 9;
            }
            (1, 4) => {
                match i.result {
                    1 => s.again = 1,
                    3 => return done(-1),
                    _ => return done(0),
                }
                s.phase = 9;
            }
            (1, 5) => return emit(s, 6, 7, i.len as u64),
            (1, 6) => {
                if i.result < 0 {
                    return done(-1);
                }
                if i.flags & REMOVED != 0 {
                    return done(0);
                }
                return emit(s, 7, 10, 0);
            }
            (1, 7) => {
                if i.flags & TLS != 0 {
                    return emit(s, 8, 13, 0);
                }
                return done(0);
            }
            (1, 8) => {
                if i.result > 0 {
                    s.phase = 0
                } else {
                    return done(0);
                }
            }
            (1, 9) => {
                if i.len == i.max as usize {
                    return emit(s, 900, 17, i.len as u64);
                }
                if i.len == i.cap {
                    s.again = 1;
                    if i.cap < (i.max as usize) {
                        if i.page == 0 {
                            return done(-1);
                        }
                        let p = i.page as usize;
                        let n = i
                            .cap
                            .wrapping_mul(2)
                            .wrapping_add(p - (i.cap.wrapping_mul(2) % p))
                            as u32;
                        return emit(s, 10, 5, n.min(i.max) as u64);
                    }
                }
                s.phase = 10;
            }
            (1, 10) => {
                if s.again != 0 {
                    s.phase = 0
                } else {
                    return done(0);
                }
            }
            (2, 0) => {
                if i.len < (i.eof_len as usize) {
                    return done(1);
                }
                return emit(s, 1, 11, 0);
            }
            (2, 1) => {
                if i.flags & REMOVED != 0 || i.result < 0 {
                    return done(3);
                }
                if i.result == 0 {
                    return done(1);
                }
                if (i.result as usize) < i.len {
                    return emit(s, 2, 9, i.result as u64);
                }
                return emit(s, 3, 10, 0);
            }
            (2, 2) => return emit(s, 3, 12, i.len.saturating_sub(i.eof_len as usize) as u64),
            (2, 3) => return done(if i.flags & TLS != 0 { 1 } else { 0 }),
            _ => return done(-1),
        }
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_framing_width(format: u8) -> usize {
    match format {
        b'c' | b'C' => 1,
        b's' | b'S' | b'n' | b'v' => 2,
        b'i' | b'I' | b'l' | b'L' | b'N' | b'V' => 4,
        b'q' | b'Q' | b'J' | b'P' => 8,
        _ => 0,
    }
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_framing_unpack(
    format: u8,
    data: *const u8,
    len: usize,
    out: *mut i64,
) -> i32 {
    let width = swr_v1_framing_width(format);
    if width == 0 {
        return -1;
    }
    let (Some(v), Some(out)) = (unsafe { bytes(data, len) }, unsafe { out.as_mut() }) else {
        return -2;
    };
    if v.len() < width {
        return -2;
    }
    let mut raw = [0u8; 8];
    raw[..width].copy_from_slice(&v[..width]);
    *out = match format {
        b'c' => v[0] as i8 as i64,
        b'C' => v[0] as i64,
        b's' => i16::from_ne_bytes([raw[0], raw[1]]) as i64,
        b'S' => u16::from_ne_bytes([raw[0], raw[1]]) as i64,
        b'n' => u16::from_be_bytes([raw[0], raw[1]]) as i64,
        b'v' => u16::from_le_bytes([raw[0], raw[1]]) as i64,
        b'i' | b'l' => i32::from_ne_bytes([raw[0], raw[1], raw[2], raw[3]]) as i64,
        b'I' | b'L' => u32::from_ne_bytes([raw[0], raw[1], raw[2], raw[3]]) as i64,
        b'N' => u32::from_be_bytes([raw[0], raw[1], raw[2], raw[3]]) as i64,
        b'V' => u32::from_le_bytes([raw[0], raw[1], raw[2], raw[3]]) as i64,
        b'q' | b'Q' => i64::from_ne_bytes(raw),
        b'J' => u64::from_be_bytes(raw) as i64,
        b'P' => u64::from_le_bytes(raw) as i64,
        _ => return -1,
    };
    0
}
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_framing_hton64(value: u64) -> u64 {
    value.to_be()
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_framing_default(
    format: u8,
    data: *const u8,
    len: usize,
    offset: u32,
    size: u32,
    body_offset: u32,
    out: *mut i64,
) -> i32 {
    if size == 0 {
        return -1;
    }
    let Some(out) = (unsafe { out.as_mut() }) else {
        return -1;
    };
    let need = offset as usize + size as usize;
    if len < need {
        *out = need as i64;
        return 0;
    }
    let Some(v) = (unsafe { bytes(data, len) }) else {
        return -1;
    };
    let width = swr_v1_framing_width(format);
    if width == 0 {
        return -2;
    }
    if width > len - offset as usize {
        return -1;
    }
    let mut value = 0;
    let result =
        unsafe { swr_v1_framing_unpack(format, v[offset as usize..].as_ptr(), width, &mut value) };
    if result != 0 || value < 0 {
        return -1;
    }
    let Some(total) = value.checked_add(body_offset as i64) else {
        return -1;
    };
    *out = total;
    1
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct Span {
    pub data: *const u8,
    pub len: usize,
}
fn span(v: &'static [u8]) -> Span {
    Span {
        data: v.as_ptr(),
        len: v.len(),
    }
}
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_framing_mime_count() -> usize {
    mime::CATALOG.len()
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_framing_mime_entry(
    index: usize,
    key: *mut Span,
    value: *mut Span,
) -> u8 {
    let (Some(&(k, v)), Some(key), Some(value)) =
        (mime::CATALOG.get(index), unsafe { key.as_mut() }, unsafe {
            value.as_mut()
        })
    else {
        return 0;
    };
    *key = span(k);
    *value = span(v);
    1
}
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_framing_mime_fallback() -> Span {
    span(b"application/octet-stream")
}
unsafe extern "C" {
    fn tolower(c: i32) -> i32;
}
/// Locate the borrowed suffix before native std::string allocation. No pointer
/// or borrow survives return; usize::MAX rejects an inaccessible input extent.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_framing_mime_suffix_offset(data: *const u8, len: usize) -> usize {
    unsafe { bytes(data, len) }.map_or(usize::MAX, |input| {
        input
            .iter()
            .rposition(|&c| c == b'.')
            .map_or(0, |at| at + 1)
    })
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_framing_mime_suffix(
    data: *const u8,
    len: usize,
    out: *mut u8,
    cap: usize,
    native_signed: u8,
) -> usize {
    let Some(data) = (unsafe { bytes(data, len) }) else {
        return usize::MAX;
    };
    let start = data.iter().rposition(|&c| c == b'.').map_or(0, |n| n + 1);
    let suffix = &data[start..];
    if suffix.len() > cap || (!suffix.is_empty() && out.is_null()) {
        return usize::MAX;
    }
    for (n, &c) in suffix.iter().enumerate() {
        // Native signed-char values below EOF violate C tolower's contract. Keep
        // those bytes well-defined through unsigned input, rather than C UB.
        let input = if native_signed != 0 && c == 255 {
            -1
        } else {
            c as i32
        };
        unsafe { out.add(n).write(tolower(input) as u8) };
    }
    suffix.len()
}
