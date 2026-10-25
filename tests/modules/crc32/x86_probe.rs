#![no_std]
#![no_main]
#[path = "../../../crates/crc32/src/lib.rs"]
mod crc32;
#[panic_handler]
fn panic(_: &core::panic::PanicInfo) -> ! {
    exit(101)
}
fn exit(code: u64) -> ! {
    unsafe { core::arch::asm!("syscall", in("rax") 60_u64, in("rdi") code, options(noreturn)) }
}
#[unsafe(no_mangle)]
pub extern "C" fn _start() -> ! {
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
        if crc32::crc32(&bytes) != !expected {
            exit(1);
        }
    }
    if crc32::crc32(b"123456789") != 0xcbf4_3926 {
        exit(2);
    }
    unsafe {
        if crc32::swr_v1_crc32(usize::MAX as *const u8, 1) != 0 {
            exit(3);
        }
    }
    let binary = [0, 255, 128, 1, 2, 3, 4, 5, 6, 7, 8, 9];
    for offset in 0..binary.len() {
        let mut expected = u32::MAX;
        for &byte in &binary[offset..] {
            expected ^= u32::from(byte);
            for _ in 0..8 {
                expected = if expected & 1 == 0 {
                    expected >> 1
                } else {
                    (expected >> 1) ^ 0xedb8_8320
                };
            }
        }
        if crc32::crc32(&binary[offset..]) != !expected {
            exit(4);
        }
    }
    exit(0)
}
