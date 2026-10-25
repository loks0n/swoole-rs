//! Marker bytes and exponential sampling for native-owned coroutine stacks.

use std::ptr;

const START: usize = 64 * 1024;
const MAGIC: &[u8] = b"swoole_coroutine#5652a7fb2b38be";

fn offsets() -> impl Iterator<Item = usize> {
    std::iter::successors(Some(START), |offset| offset.checked_mul(2))
}

/// # Safety
/// `stack` names `size` writable native-owned bytes, without concurrent access.
/// Bytes outside the marker spans may be uninitialized. No pointer is retained.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_context_stack_mark(stack: *mut u8, size: usize) {
    unsafe { mark(stack, size) };
}

pub(crate) unsafe fn mark(stack: *mut u8, size: usize) {
    for offset in offsets().take_while(|&offset| offset <= size) {
        let index = size - offset + MAGIC.len();
        unsafe { ptr::copy_nonoverlapping(MAGIC.as_ptr(), stack.add(index), MAGIC.len()) };
    }
}

/// # Safety
/// `stack` names `size` native-owned bytes without concurrent mutation. Each
/// sampled marker span is initialized, normally by `context_stack_mark` before
/// native stack execution. No other stack bytes are read; no borrow is retained.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_context_stack_usage(stack: *const u8, size: usize) -> usize {
    unsafe { usage(stack, size) }
}

pub(crate) unsafe fn usage(stack: *const u8, size: usize) -> usize {
    let mut usage = START;
    for offset in offsets().take_while(|&offset| offset < size) {
        let index = size - offset + MAGIC.len();
        let marker = unsafe { std::slice::from_raw_parts(stack.add(index), MAGIC.len()) };
        let matches = marker == MAGIC;
        if !matches {
            usage = offset * 2;
        }
    }
    usage
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn marker_boundaries_and_last_changed_sample_preserve_original_accounting() {
        for size in [
            0,
            1,
            START - 1,
            START,
            START + 1,
            START * 2,
            START * 2 + 1,
            START * 16,
        ] {
            let mut memory = vec![0xa5; size];
            unsafe { swr_v1_context_stack_mark(memory.as_mut_ptr(), size) };
            for (index, &byte) in memory.iter().enumerate() {
                let expected = offsets()
                    .take_while(|&offset| offset <= size)
                    .find_map(|offset| {
                        let start = size - offset + MAGIC.len();
                        (start..start + MAGIC.len())
                            .contains(&index)
                            .then(|| MAGIC[index - start])
                    })
                    .unwrap_or(0xa5);
                assert_eq!(byte, expected);
            }
            assert_eq!(
                unsafe { swr_v1_context_stack_usage(memory.as_ptr(), size) },
                START
            );
            let mut expected = START;
            for offset in offsets().take_while(|&offset| offset <= size) {
                memory[size - offset + MAGIC.len()] ^= 1;
                if offset < size {
                    expected = offset * 2;
                }
                assert_eq!(
                    unsafe { swr_v1_context_stack_usage(memory.as_ptr(), size) },
                    expected
                );
            }
        }
    }
}
