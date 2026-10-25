//! Opt-in owned POSIX descriptor storage. Public C++ fields retain their layout;
//! allocation-local release metadata is independent of those mutable fields.
use crate::ReactorIovProgress;
use crate::iov_progress::progress;
use std::alloc::{Layout, alloc, dealloc};
use std::ptr;

struct Header {
    layout: Layout,
}
#[repr(C)]
pub struct ReactorIovAllocation {
    pub original: *mut libc::iovec,
    pub iterator: *mut libc::iovec,
    ///0 ready, -1 invalid Native array bound, -2 allocation/capacity refusal.
    pub status: i32,
}
fn allocation_layout(count: usize) -> Option<(Layout, usize)> {
    let descriptors = Layout::array::<libc::iovec>(count.checked_mul(2)?).ok()?;
    let (layout, offset) = Layout::new::<Header>().extend(descriptors).ok()?;
    Some((layout.pad_to_align(), offset))
}
fn descriptor_offset() -> usize {
    std::mem::size_of::<Header>().next_multiple_of(std::mem::align_of::<libc::iovec>())
}
/// Construct both actual descriptor spans, not a Native mirror. Payload bytes
/// are neither read nor owned. Native throws only after this function returns.
/// # Safety
/// For count>0, source names count initialized, readable target C iovec objects.
/// Source objects/payloads remain Native-owned and disjoint from the new owner.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_iov_owned_new(
    source: *const libc::iovec,
    count: i32,
) -> ReactorIovAllocation {
    let refused = |status| ReactorIovAllocation {
        original: ptr::null_mut(),
        iterator: ptr::null_mut(),
        status,
    };
    if count < 0 {
        return refused(-1);
    }
    // The pinned Native expression count+count has no defined signed-overflow
    // behavior. This explicit refusal does not establish parity in that domain.
    if count > i32::MAX / 2 {
        return refused(-2);
    }
    let count = count as usize;
    let Some((layout, offset)) = allocation_layout(count) else {
        return refused(-2);
    };
    let allocation = unsafe { alloc(layout) };
    if allocation.is_null() {
        return refused(-2);
    }
    unsafe {
        allocation.cast::<Header>().write(Header { layout });
        let original = allocation.add(offset).cast::<libc::iovec>();
        let iterator = original.add(count);
        if count != 0 {
            ptr::copy_nonoverlapping(source, original, count);
            ptr::copy_nonoverlapping(source, iterator, count);
        }
        ReactorIovAllocation {
            original,
            iterator,
            status: 0,
        }
    }
}
/// Release only descriptor storage and allocation-local metadata. No payload,
/// Native callback, destructor or public counter is consulted.
/// # Safety
/// original is null or the unmodified base returned by owned_new, exclusively owned and
/// released exactly once. Foreign/replaced/shallow-copied owners are unsupported.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_iov_owned_free(original: *mut libc::iovec) {
    if original.is_null() {
        return;
    }
    let allocation = unsafe { original.cast::<u8>().sub(descriptor_offset()) };
    let header = unsafe { allocation.cast::<Header>().read() };
    unsafe { dealloc(allocation, header.layout) };
}
/// Sum the live original descriptor span with C size_t wrapping semantics.
/// # Safety
/// For positive count, original names count readable initialized C iovec objects.
/// No payload is dereferenced and no borrow survives this call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_iov_owned_length(
    original: *const libc::iovec,
    count: i32,
) -> usize {
    (0..count).fold(0usize, |total, i| {
        total.wrapping_add(unsafe { (*original.add(i as usize)).iov_len })
    })
}
/// Compute the existing progress policy and mutate the actual owned iterator
/// descriptor before returning new public cursor facts. The final completion
/// path never touches the iterator payload, matching the original behavior.
/// # Safety
/// For positive n/remaining, iterator names remaining writable initialized
/// descriptors with the same live C payload-pointer domain as the Native API.
/// Public counter/sum values are in the original defined integer domain.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_iov_owned_progress(
    iterator: *mut libc::iovec,
    n: isize,
    remaining: i32,
    index: i32,
    offset: usize,
) -> ReactorIovProgress {
    let reply = progress(
        (0..remaining).map(|i| unsafe { (*iterator.add(i as usize)).iov_len }),
        n,
        remaining,
        index,
        offset,
    );
    if reply.action == 1 {
        let current = unsafe { &mut *iterator.add(reply.advance) };
        current.iov_base = current
            .iov_base
            .cast::<u8>()
            .wrapping_add(reply.consumed)
            .cast();
        current.iov_len = current.iov_len.wrapping_sub(reply.consumed);
    }
    reply
}
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_reactor_iov_owned_layout(field: u32) -> usize {
    match field {
        0 => std::mem::size_of::<ReactorIovAllocation>(),
        1 => std::mem::align_of::<ReactorIovAllocation>(),
        2 => std::mem::offset_of!(ReactorIovAllocation, original),
        3 => std::mem::offset_of!(ReactorIovAllocation, iterator),
        4 => std::mem::offset_of!(ReactorIovAllocation, status),
        _ => usize::MAX,
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn iov_owned_positive_construct_copy_length_cursor_and_release() {
        for count in [1, 3, 17, 65] {
            let mut bytes = [0u8; 128];
            let source: Vec<_> = (0..count)
                .map(|i| libc::iovec {
                    iov_base: bytes.as_mut_ptr().wrapping_add(i).cast(),
                    iov_len: 1,
                })
                .collect();
            unsafe {
                let owner = swr_v1_reactor_iov_owned_new(source.as_ptr(), count as i32);
                assert_eq!(owner.status, 0);
                assert_eq!(owner.original.add(count), owner.iterator);
                assert_eq!(
                    owner.original as usize % std::mem::align_of::<libc::iovec>(),
                    0
                );
                assert_eq!(
                    swr_v1_reactor_iov_owned_length(owner.original, count as i32),
                    count
                );
                for (i, expected) in source.iter().enumerate() {
                    for span in [owner.original, owner.iterator] {
                        assert_eq!((*span.add(i)).iov_base, expected.iov_base);
                        assert_eq!((*span.add(i)).iov_len, expected.iov_len);
                    }
                }
                let reply =
                    swr_v1_reactor_iov_owned_progress(owner.iterator, 1, count as i32, 0, 0);
                assert_eq!(reply.remain_count, count as i32 - 1);
                assert_eq!(reply.index, 1);
                assert_eq!(reply.action, if count == 1 { 2 } else { 1 });
                assert_eq!(
                    swr_v1_reactor_iov_owned_length(owner.original, count as i32),
                    count
                );
                swr_v1_reactor_iov_owned_free(owner.original);
            }
        }
        // Normal positive partial consumption mutates only the iterator span;
        // final completion must not touch that descriptor again.
        let mut bytes = [0u8; 7];
        let source = libc::iovec {
            iov_base: bytes.as_mut_ptr().cast(),
            iov_len: 7,
        };
        unsafe {
            let owner = swr_v1_reactor_iov_owned_new(&source, 1);
            assert_eq!(owner.status, 0);
            let partial = swr_v1_reactor_iov_owned_progress(owner.iterator, 2, 1, 0, 0);
            assert_eq!(
                (partial.action, partial.offset_bytes, partial.remain_count),
                (1, 2, 1)
            );
            assert_eq!((*owner.iterator).iov_base, bytes.as_mut_ptr().add(2).cast());
            assert_eq!((*owner.iterator).iov_len, 5);
            assert_eq!(swr_v1_reactor_iov_owned_length(owner.original, 1), 7);
            let final_piece = swr_v1_reactor_iov_owned_progress(owner.iterator, 5, 1, 0, 2);
            assert_eq!(
                (
                    final_piece.action,
                    final_piece.index,
                    final_piece.remain_count
                ),
                (2, 1, 0)
            );
            assert_eq!((*owner.iterator).iov_len, 5);
            assert_eq!((*owner.iterator).iov_base, bytes.as_mut_ptr().add(2).cast());
            swr_v1_reactor_iov_owned_free(owner.original);
        }
    }
}
