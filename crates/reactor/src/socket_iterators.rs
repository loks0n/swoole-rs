//! Inline typed iterator metadata for the selected registry's real C++ views.
//! Socket tokens stay opaque. Native reads its stable owner slot and performs
//! pair materialization/abort only after Rust returns; no Native borrow is held.
use crate::sockets::{next_entry, snapshot_entry};
use crate::{ReactorSocketCursor, ReactorSocketEntry, ReactorSocketSnapshot, ReactorSockets};

#[repr(C)]
#[derive(Clone, Copy)]
pub struct ReactorSocketLiveIterator {
    pub slot_identity: usize,
    pub cursor: ReactorSocketCursor,
    pub value: ReactorSocketEntry,
    pub done: u8,
}
#[repr(C)]
#[derive(Clone, Copy)]
pub struct ReactorSocketSnapshotIterator {
    pub owner: *const ReactorSocketSnapshot,
    pub index: usize,
}

impl ReactorSocketLiveIterator {
    fn advance(&mut self, owner: Option<&ReactorSockets>) -> i32 {
        let status = next_entry(owner, &mut self.cursor, &mut self.value);
        if status >= 0 {
            self.done = u8::from(status == 0);
        }
        status
    }
}

impl ReactorSocketSnapshotIterator {
    fn advance(&mut self) {
        self.index = self.index.wrapping_add(1);
    }
}

/// # Safety
/// Live, exclusive initialized POD state; owner is null/live Rust metadata,
/// disjoint from state. Native has just read its actual stable owner slot.
/// Socket tokens and slot_identity are never dereferenced by Rust.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_sockets_live_next(
    owner: *const ReactorSockets,
    state: *mut ReactorSocketLiveIterator,
) -> i32 {
    let Some(state) = (unsafe { state.as_mut() }) else {
        return -1;
    };
    state.advance(unsafe { owner.as_ref() })
}
/// # Safety
/// Same live_next contract; previous is a live writable initialized POD,
/// exclusive/disjoint from state and owner. Copy precedes advancement. There
/// are no payload constructors/destructors or Native effects in either action.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_sockets_live_post(
    owner: *const ReactorSockets,
    state: *mut ReactorSocketLiveIterator,
    previous: *mut ReactorSocketLiveIterator,
) -> i32 {
    if state.is_null() || previous.is_null() || state == previous {
        return -1;
    }
    let state = unsafe { &mut *state };
    unsafe { previous.write(*state) };
    state.advance(unsafe { owner.as_ref() })
}
/// # Safety
/// Both POD values are live/readable (may alias), initialized from a Native
/// typed iterator seed/these APIs. done is0/1. No slot/owner is dereferenced.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_sockets_live_compare(
    left: *const ReactorSocketLiveIterator,
    right: *const ReactorSocketLiveIterator,
    unequal: u32,
) -> u32 {
    let (Some(left), Some(right)) = ((unsafe { left.as_ref() }), (unsafe { right.as_ref() }))
    else {
        return 0;
    };
    let equal = if left.done != 0 && right.done != 0 {
        true
    } else {
        left.done == right.done
            && left.slot_identity == right.slot_identity
            && left.cursor.current == right.cursor.current
            && left.cursor.generation == right.cursor.generation
    };
    u32::from(equal != (unequal != 0))
}
/// # Safety
/// Snapshot iterator POD is live/readable and owner is null/live immutable Rust
/// snapshot storage. Output is live writable/disjoint, not a Native pair object.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_sockets_snapshot_iterator_entry(
    state: *const ReactorSocketSnapshotIterator,
    output: *mut ReactorSocketEntry,
) -> i32 {
    let Some(state) = (unsafe { state.as_ref() }) else {
        return -1;
    };
    let Some(output) = (unsafe { output.as_mut() }) else {
        return -1;
    };
    snapshot_entry(unsafe { state.owner.as_ref() }, state.index, output)
}
/// # Safety
/// Live exclusive initialized POD; the original unsigned cursor arithmetic is
/// preserved. Supported consumers advance valid iterators only. No owner read.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_sockets_snapshot_iterator_next(
    state: *mut ReactorSocketSnapshotIterator,
) {
    if let Some(state) = unsafe { state.as_mut() } {
        state.advance();
    }
}
/// # Safety
/// Both states are initialized live/exclusive/disjoint POD values. Native
/// constructor/copy/return ABI effects remain outside Rust; no owner is read.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_sockets_snapshot_iterator_post(
    state: *mut ReactorSocketSnapshotIterator,
    previous: *mut ReactorSocketSnapshotIterator,
) -> i32 {
    if state.is_null() || previous.is_null() || state == previous {
        return -1;
    }
    let state = unsafe { &mut *state };
    unsafe { previous.write(*state) };
    state.advance();
    0
}
/// # Safety
/// Live/readable initialized POD values, possibly aliased. Owner is compared as
/// identity only, never dereferenced; no Native Socket/object pointer is read.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_sockets_snapshot_iterator_compare(
    left: *const ReactorSocketSnapshotIterator,
    right: *const ReactorSocketSnapshotIterator,
    unequal: u32,
) -> u32 {
    let (Some(left), Some(right)) = ((unsafe { left.as_ref() }), (unsafe { right.as_ref() }))
    else {
        return 0;
    };
    let equal = left.owner == right.owner && left.index == right.index;
    u32::from(equal != (unequal != 0))
}

#[cfg(test)]
mod tests {
    use super::*;
    fn end() -> ReactorSocketLiveIterator {
        ReactorSocketLiveIterator {
            slot_identity: 0,
            cursor: ReactorSocketCursor::default(),
            value: ReactorSocketEntry::default(),
            done: 1,
        }
    }
    #[test]
    fn live_inline_state_uses_actual_store_and_postfix_copy_before_advance() {
        unsafe {
            let mut owner = std::ptr::null_mut();
            for fd in [3, 7, 11] {
                assert_eq!(
                    crate::swr_v1_reactor_sockets_put(&mut owner, fd, fd as usize + 100),
                    0
                );
            }
            let mut state = end();
            state.slot_identity = 17;
            assert_eq!(swr_v1_reactor_sockets_live_next(owner, &mut state), 1);
            let mut previous = end();
            let current = state.value;
            assert_eq!(
                swr_v1_reactor_sockets_live_post(owner, &mut state, &mut previous),
                1
            );
            assert_eq!(previous.value, current);
            assert_eq!(swr_v1_reactor_sockets_live_compare(&previous, &state, 0), 0);
            assert_eq!(swr_v1_reactor_sockets_live_compare(&previous, &state, 1), 1);
            while swr_v1_reactor_sockets_live_next(owner, &mut state) > 0 {}
            assert_eq!(swr_v1_reactor_sockets_live_compare(&state, &end(), 0), 1);
            crate::swr_v1_reactor_sockets_free(&mut owner);
        }
    }
    #[test]
    fn snapshot_inline_progression_and_lookup_use_real_owned_snapshot() {
        unsafe {
            let mut owner = std::ptr::null_mut();
            for fd in [2, 4, 8] {
                assert_eq!(
                    crate::swr_v1_reactor_sockets_put(&mut owner, fd, fd as usize),
                    0
                );
            }
            let mut snapshot = std::ptr::null_mut();
            assert_eq!(
                crate::swr_v1_reactor_sockets_snapshot(owner, &mut snapshot),
                0
            );
            let mut state = ReactorSocketSnapshotIterator {
                owner: snapshot,
                index: 0,
            };
            let mut previous = state;
            for index in 0..3 {
                let mut entry = ReactorSocketEntry::default();
                let mut expected = entry;
                assert_eq!(
                    swr_v1_reactor_sockets_snapshot_iterator_entry(&state, &mut entry),
                    1
                );
                assert_eq!(
                    crate::swr_v1_reactor_sockets_snapshot_entry(snapshot, index, &mut expected),
                    1
                );
                assert_eq!(entry, expected);
                assert_eq!(
                    swr_v1_reactor_sockets_snapshot_iterator_post(&mut state, &mut previous),
                    0
                );
                assert_eq!(previous.index, index);
                assert_eq!(
                    swr_v1_reactor_sockets_snapshot_iterator_compare(&state, &previous, 0),
                    0
                );
                assert_eq!(
                    swr_v1_reactor_sockets_snapshot_iterator_compare(&state, &previous, 1),
                    1
                );
            }
            crate::swr_v1_reactor_sockets_snapshot_free(snapshot);
            crate::swr_v1_reactor_sockets_free(&mut owner);
        }
    }
    #[test]
    fn live_comparison_preserves_done_slot_cursor_and_generation_rules() {
        unsafe {
            let mut a = end();
            let mut b = end();
            b.slot_identity = 97;
            b.cursor.current = 31;
            b.cursor.generation = 2;
            assert_eq!(swr_v1_reactor_sockets_live_compare(&a, &b, 0), 1);
            a.done = 0;
            b.done = 0;
            assert_eq!(swr_v1_reactor_sockets_live_compare(&a, &b, 0), 0);
            a.slot_identity = b.slot_identity;
            a.cursor.current = b.cursor.current;
            a.cursor.generation = b.cursor.generation;
            assert_eq!(swr_v1_reactor_sockets_live_compare(&a, &b, 0), 1);
            a.cursor.generation += 1;
            assert_eq!(swr_v1_reactor_sockets_live_compare(&a, &b, 0), 0);
        }
    }
    #[test]
    fn native_pod_layout_keeps_existing_selected_iterator_footprints() {
        assert_eq!(std::mem::size_of::<ReactorSocketLiveIterator>(), 56);
        assert_eq!(std::mem::offset_of!(ReactorSocketLiveIterator, cursor), 8);
        assert_eq!(std::mem::offset_of!(ReactorSocketLiveIterator, value), 32);
        assert_eq!(std::mem::offset_of!(ReactorSocketLiveIterator, done), 48);
        assert_eq!(std::mem::size_of::<ReactorSocketSnapshotIterator>(), 16);
        assert_eq!(
            std::mem::offset_of!(ReactorSocketSnapshotIterator, index),
            8
        );
    }
}
