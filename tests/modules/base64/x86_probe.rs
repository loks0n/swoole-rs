// Freestanding x86 Linux correctness witness, executed through Linux binfmt.
// This is no_std test scaffolding; the production source is included unchanged.
#![no_std]
#![no_main]
extern crate core as std;
#[path = "../../../crates/base64/src/lib.rs"]
mod base64;
use core::mem::MaybeUninit;
#[panic_handler]
fn panic(_: &core::panic::PanicInfo) -> ! {
    exit(101)
}
fn exit(code: u64) -> ! {
    unsafe { core::arch::asm!("syscall", in("rax") 60_u64, in("rdi") code, options(noreturn)) }
}
const fn input() -> [u8; 256] {
    let mut bytes = [0; 256];
    let mut i = 0;
    while i < bytes.len() {
        bytes[i] = i as u8;
        i += 1;
    }
    bytes
}
static BINARY: [u8; 256] = input();
static CODED: &[u8] = b"AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8gISIjJCUmJygpKissLS4vMDEyMzQ1Njc4OTo7PD0+P0BBQkNERUZHSElKS0xNTk9QUVJTVFVWV1hZWltcXV5fYGFiY2RlZmdoaWprbG1ub3BxcnN0dXZ3eHl6e3x9fn+AgYKDhIWGh4iJiouMjY6PkJGSk5SVlpeYmZqbnJ2en6ChoqOkpaanqKmqq6ytrq+wsbKztLW2t7i5uru8vb6/wMHCw8TFxsfIycrLzM3Oz9DR0tPU1dbX2Nna29zd3t/g4eLj5OXm5+jp6uvs7e7v8PHy8/T19vf4+fr7/P3+/w==";

fn check(plain: &[u8], coded: &[u8]) {
    // Only read bytes the callee actually initializes; no initialized sentinel
    // fixture can accidentally cover an implementation read of uninitialized IO.
    let mut output = MaybeUninit::<[u8; 1024]>::uninit();
    let pointer = output.as_mut_ptr().cast::<u8>();
    unsafe {
        let n = base64::swr_v1_base64_encode(plain.as_ptr(), plain.len(), pointer);
        if n != coded.len()
            || core::slice::from_raw_parts(pointer, n) != coded
            || *pointer.add(n) != 0
        {
            exit(1);
        }
        let n = base64::swr_v1_base64_decode(coded.as_ptr(), coded.len(), pointer);
        if n != plain.len()
            || core::slice::from_raw_parts(pointer, n) != plain
            || *pointer.add(n) != 0
        {
            exit(2);
        }
    }
}
#[unsafe(no_mangle)]
pub extern "C" fn _start() -> ! {
    for (plain, coded) in [
        (b"".as_slice(), b"".as_slice()),
        (b"f", b"Zg=="),
        (b"fo", b"Zm8="),
        (b"foo", b"Zm9v"),
        (b"foob", b"Zm9vYg=="),
        (b"fooba", b"Zm9vYmE="),
        (b"foobar", b"Zm9vYmFy"),
    ] {
        check(plain, coded);
    }
    check(&BINARY, CODED);
    let mut output = MaybeUninit::<[u8; 8]>::uninit();
    let pointer = output.as_mut_ptr().cast::<u8>();
    unsafe {
        if base64::swr_v1_base64_decode(b"Zh!".as_ptr(), 3, pointer) != 0
            || *pointer != b'f'
            || *pointer.add(1) != 16
        {
            exit(3);
        }
        if base64::swr_v1_base64_decode(b"Z".as_ptr(), 1, pointer) != 0 || *pointer != 0 {
            exit(4);
        }
        if base64::swr_v1_base64_decode(b"Zh".as_ptr(), 2, pointer) != 1
            || *pointer != b'f'
            || *pointer.add(1) != 0
        {
            exit(5);
        }
    }
    let mut sentinel = [0xa5; 16];
    for function in [base64::swr_v1_base64_encode, base64::swr_v1_base64_decode] {
        unsafe {
            if function(usize::MAX as *const u8, 1, sentinel.as_mut_ptr()) != 0 {
                exit(6);
            }
            if function(BINARY.as_ptr(), usize::MAX, sentinel.as_mut_ptr()) != 0 {
                exit(7);
            }
        }
        if sentinel.iter().any(|&b| b != 0xa5) {
            exit(8);
        }
    }
    exit(0)
}

// Minimal freestanding linker support for the test's slice comparisons. Never
// accept an unwind: invoking the personality stub is a failing process exit.
#[unsafe(no_mangle)]
pub extern "C" fn rust_eh_personality() {
    exit(102)
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn bcmp(a: *const u8, b: *const u8, n: usize) -> i32 {
    for i in 0..n {
        if unsafe { a.add(i).read_volatile() != b.add(i).read_volatile() } {
            return 1;
        }
    }
    0
}
