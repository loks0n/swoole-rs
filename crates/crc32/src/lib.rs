//! IEEE CRC32, ported from Swoole v6.2.2 src/core/crc32.cc (Apache-2.0).
//! Original author: Tianfeng Han <rango@swoole.com>.
//! The lookup table is immutable and generated during compilation.

// Use instructions only when the compiler's target contract already guarantees
// IEEE CRC support. No runtime CPU query, lazy state or OS effect is introduced.
// Other targets retain the exact slicing-by-eight implementation below.
#[cfg(any(test, not(all(target_arch = "aarch64", target_feature = "crc"))))]
mod portable {
    // Row n is the byte contribution followed by n zero bytes. Divide the base
    // row once, then append each zero byte using that same immutable recurrence.
    const fn tables() -> [[u32; 256]; 8] {
        let mut entries = [[0; 256]; 8];
        let mut index = 0;
        while index < 256 {
            let mut value = index as u32;
            let mut bit = 0;
            while bit < 8 {
                value = (value >> 1) ^ (0xedb8_8320 * (value & 1));
                bit += 1;
            }
            entries[0][index] = value;
            index += 1;
        }
        let mut row = 1;
        while row < entries.len() {
            index = 0;
            while index < 256 {
                let value = entries[row - 1][index];
                entries[row][index] = (value >> 8) ^ entries[0][(value & 0xff) as usize];
                index += 1;
            }
            row += 1;
        }
        entries
    }

    pub(super) static TABLES: [[u32; 256]; 8] = tables();

    /// Return IEEE CRC32 with the upstream initial and final XOR.
    pub(super) fn crc32(input: &[u8]) -> u32 {
        let mut crc = u32::MAX;
        let mut blocks = input.chunks_exact(8);
        for block in blocks.by_ref() {
            // Exact chunks establish the conversion length. Explicit little-endian
            // decoding retains the same byte recurrence on either host endianness.
            let bytes =
                (u64::from_le_bytes(block.try_into().unwrap()) ^ u64::from(crc)).to_le_bytes();
            crc = TABLES[7][bytes[0] as usize]
                ^ TABLES[6][bytes[1] as usize]
                ^ TABLES[5][bytes[2] as usize]
                ^ TABLES[4][bytes[3] as usize]
                ^ TABLES[3][bytes[4] as usize]
                ^ TABLES[2][bytes[5] as usize]
                ^ TABLES[1][bytes[6] as usize]
                ^ TABLES[0][bytes[7] as usize];
        }
        !blocks.remainder().iter().fold(crc, |crc, &byte| {
            (crc >> 8) ^ TABLES[0][((crc ^ u32::from(byte)) & 0xff) as usize]
        })
    }
}

/// Return IEEE CRC32 with the upstream initial and final XOR.
pub fn crc32(input: &[u8]) -> u32 {
    #[cfg(all(target_arch = "aarch64", target_feature = "crc"))]
    // SAFETY: the selected compile target already guarantees the crc feature.
    unsafe {
        crc32_instructions(input)
    }
    #[cfg(not(all(target_arch = "aarch64", target_feature = "crc")))]
    portable::crc32(input)
}

#[cfg(all(target_arch = "aarch64", target_feature = "crc"))]
#[target_feature(enable = "crc")]
unsafe fn crc32_instructions(input: &[u8]) -> u32 {
    use core::arch::aarch64::{__crc32b, __crc32d, __crc32h, __crc32w};
    let mut crc = u32::MAX;
    let mut blocks = input.chunks_exact(8);
    for block in blocks.by_ref() {
        crc = __crc32d(crc, u64::from_le_bytes(block.try_into().unwrap()));
    }
    let mut tail = blocks.remainder();
    if let Some((word, remaining)) = tail.split_first_chunk::<4>() {
        crc = __crc32w(crc, u32::from_le_bytes(*word));
        tail = remaining;
    }
    if let Some((half, remaining)) = tail.split_first_chunk::<2>() {
        crc = __crc32h(crc, u16::from_le_bytes(*half));
        tail = remaining;
    }
    if let Some(&byte) = tail.first() {
        crc = __crc32b(crc, byte);
    }
    !crc
}

/// Borrow input for one call; no allocations, callbacks, or retained pointers.
///
/// # Safety
/// Nonempty input must point to `length` readable bytes in one allocation.
/// Empty input may be null. Invalid null/oversized input returns zero.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_crc32(input: *const u8, length: usize) -> u32 {
    if length == 0
        || input.is_null()
        || length > isize::MAX as usize
        || (input as usize).checked_add(length).is_none()
    {
        return 0;
    }
    // SAFETY: null, representability and address wrap checked; caller provides extent.
    crc32(unsafe { core::slice::from_raw_parts(input, length) })
}

#[cfg(test)]
mod tests {
    use super::portable::TABLES;
    use super::*;

    #[test]
    fn every_table_row_matches_independent_polynomial_division() {
        for (row, entries) in TABLES.iter().enumerate() {
            for (byte, &actual) in entries.iter().enumerate() {
                let mut expected = byte as u32;
                for _ in 0..8 * (row + 1) {
                    expected = if expected & 1 == 0 {
                        expected >> 1
                    } else {
                        (expected >> 1) ^ 0xedb8_8320
                    };
                }
                assert_eq!(actual, expected, "row={row}, byte={byte}");
            }
        }
    }

    #[test]
    fn standard_vectors() {
        assert_eq!(crc32(b""), 0);
        assert_eq!(crc32(b"123456789"), 0xcbf4_3926);
        assert_eq!(
            crc32(b"The quick brown fox jumps over the lazy dog"),
            0x414f_a339
        );
        assert_eq!(crc32(&[0; 32]), 0x190a_55ad);
        assert_eq!(crc32(&[255; 32]), 0xff6c_ab0b);
    }

    #[test]
    fn exhaustive_two_byte_bitwise_oracle() {
        // Independent polynomial division, without the implementation's table.
        for value in 0..=u16::MAX {
            let bytes = value.to_le_bytes();
            let mut expected = u32::MAX;
            for byte in bytes {
                expected ^= u32::from(byte);
                for _ in 0..8 {
                    expected = if expected & 1 == 0 {
                        expected >> 1
                    } else {
                        (expected >> 1) ^ 0xedb8_8320
                    };
                }
            }
            assert_eq!(crc32(&bytes), !expected);
            assert_eq!(portable::crc32(&bytes), !expected);
        }
    }

    #[test]
    fn sliced_blocks_and_tails_match_bitwise_oracle() {
        fn bitwise(input: &[u8]) -> u32 {
            let mut crc = u32::MAX;
            for &byte in input {
                crc ^= u32::from(byte);
                for _ in 0..8 {
                    crc = (crc >> 1) ^ (0xedb8_8320u32.wrapping_mul(crc & 1));
                }
            }
            !crc
        }
        let mut data = vec![0u8; 65536 + 16];
        let mut seed = 0x1234_abcdu32;
        for byte in &mut data {
            seed ^= seed << 13;
            seed ^= seed >> 17;
            seed ^= seed << 5;
            *byte = seed as u8;
        }
        for offset in 0..16 {
            for length in
                (0..=129).chain([255, 256, 257, 1023, 1024, 1025, 4095, 4096, 4097, 65536])
            {
                let bytes = &data[offset..offset + length];
                let expected = bitwise(bytes);
                assert_eq!(crc32(bytes), expected, "offset={offset}, length={length}");
                assert_eq!(
                    portable::crc32(bytes),
                    expected,
                    "portable offset={offset}, length={length}"
                );
                // The same actual C entrypoint is linked by production callers.
                assert_eq!(
                    unsafe { swr_v1_crc32(bytes.as_ptr(), bytes.len()) },
                    expected
                );
            }
        }
    }

    #[test]
    fn defensive_bounds() {
        unsafe {
            assert_eq!(swr_v1_crc32(core::ptr::null(), 0), 0);
            assert_eq!(swr_v1_crc32(core::ptr::null(), 1), 0);
            assert_eq!(swr_v1_crc32(core::ptr::dangling(), usize::MAX), 0);
            assert_eq!(swr_v1_crc32(usize::MAX as *const u8, 1), 0);
            assert_eq!(swr_v1_crc32((usize::MAX - 7) as *const u8, 8), 0);
        }
    }
}
