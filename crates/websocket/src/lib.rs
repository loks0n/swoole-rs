//! Allocation-free WebSocket codec and message/control policy. Native callers
//! retain storage, connection ownership, PHP dispatch and socket I/O.

mod codec;
pub use codec::*;

/// Query header plus payload length, preserving upstream's incremental output.
///
/// # Safety
/// `data` must cover `length` readable bytes (null is allowed only at length 0).
/// `header_length` must be a valid, aligned, exclusive writable `u32`, disjoint
/// from the input. Pointers are borrowed only for this call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_ws_frame_length(
    data: *const u8,
    length: usize,
    header_length: *mut u32,
) -> i64 {
    if header_length.is_null() || length > isize::MAX as usize || (data.is_null() && length != 0) {
        return -1;
    }
    if length < 2 {
        return 0;
    }
    // SAFETY: The caller supplies the readable input and exclusive output.
    let bytes = unsafe { std::slice::from_raw_parts(data, length) };
    let mut header = 2;
    let mut payload = u64::from(bytes[1] & 0x7f);
    if payload == 126 {
        header = 4;
    } else if payload == 127 {
        header = 10;
    }
    unsafe { header_length.write(header as u32) };
    if length < header {
        return 0;
    }
    if header == 4 {
        payload = u64::from(u16::from_be_bytes([bytes[2], bytes[3]]));
    } else if header == 10 {
        payload = u64::from_be_bytes([
            bytes[2], bytes[3], bytes[4], bytes[5], bytes[6], bytes[7], bytes[8], bytes[9],
        ]);
    }
    if bytes[1] & 0x80 != 0 {
        header += 4;
        unsafe { header_length.write(header as u32) };
        if length < header {
            return 0;
        }
    }
    // Subtract before adding: even a positive payload can overflow ssize_t once
    // the header is included. Upstream's signed addition is undefined there.
    if payload > (isize::MAX as u64) - header as u64 {
        return -1;
    }
    (payload + header as u64) as i64
}

/// Write a wire header without a mask key or payload; return 0 without writes
/// when the output is null, oversized, or too short.
///
/// # Safety
/// A non-null `output` must cover `capacity` exclusive writable bytes, borrowed
/// only for this call. No alignment beyond byte alignment is required.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_ws_write_header(
    payload_length: u64,
    opcode: u8,
    flags: u8,
    output: *mut u8,
    capacity: usize,
) -> usize {
    let size = if payload_length < 126 {
        2
    } else if payload_length <= u16::MAX as u64 {
        4
    } else {
        10
    };
    if output.is_null() || capacity < size || capacity > isize::MAX as usize {
        return 0;
    }
    let mut header = [0u8; 10];
    header[0] = (opcode & 0xf) | (u8::from(flags & 1 != 0) << 7) | (u8::from(flags & 4 != 0) << 6);
    header[1] = u8::from(flags & 32 != 0) << 7;
    match size {
        2 => header[1] |= payload_length as u8,
        4 => {
            header[1] |= 126;
            header[2..4].copy_from_slice(&(payload_length as u16).to_be_bytes());
        }
        _ => {
            header[1] |= 127;
            header[2..10].copy_from_slice(&payload_length.to_be_bytes());
        }
    }
    // SAFETY: The caller's exclusive output has enough capacity. The local
    // header cannot overlap it, and only the encoded header bytes are written.
    unsafe { std::ptr::copy_nonoverlapping(header.as_ptr(), output, size) };
    size
}

/// XOR a payload with a four-byte key; zero length permits null pointers.
///
/// # Safety
/// For nonzero length, `data` must cover `length` exclusive writable bytes and
/// `key` four readable bytes. The key may overlap data: it is copied before any
/// mutable borrow. All other aliases must remain unused for this call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_ws_mask(data: *mut u8, length: usize, key: *const u8) -> i32 {
    if length == 0 {
        return 0;
    }
    if data.is_null() || key.is_null() || length > isize::MAX as usize {
        return -1;
    }
    // SAFETY: Copy all four key bytes before the mutable payload borrow so
    // overlap is valid. read_unaligned preserves byte-aligned key support.
    let key_word = unsafe { key.cast::<u32>().read_unaligned() };
    let mask = key_word.to_ne_bytes();
    let payload = unsafe { std::slice::from_raw_parts_mut(data, length) };
    let word_mask = u64::from(key_word) | (u64::from(key_word) << 32);
    let mut words = payload.chunks_exact_mut(8);
    for bytes in &mut words {
        let word = u64::from_ne_bytes([
            bytes[0], bytes[1], bytes[2], bytes[3], bytes[4], bytes[5], bytes[6], bytes[7],
        ]);
        bytes.copy_from_slice(&(word ^ word_mask).to_ne_bytes());
    }
    // Each complete word consumes two whole keys, so the tail restarts at 0.
    for (index, byte) in words.into_remainder().iter_mut().enumerate() {
        *byte ^= mask[index & 3];
    }
    0
}
