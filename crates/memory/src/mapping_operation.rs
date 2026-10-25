//! Complete shared-mapping operation control; Native executes every external
//! File/OS/errno/warning effect after return. No mapping resource is Rust-owned.
use super::{
    extent, swr_v1_memory_mapping_initialize, swr_v1_memory_mapping_relocate,
    swr_v1_memory_mapping_size,
};
use std::{ffi::c_void, ptr};

const ALLOCATE: u32 = 0;
const RELEASE: u32 = 1;
const PROTECT: u32 = 2;
const REALLOCATE: u32 = 3;
const DONE: u32 = u32::MAX;

#[repr(C)]
#[derive(Default)]
pub struct MappingOperation {
    pub requested: usize,
    pub source: *mut u8,
    pub memory: *mut u8,
    pub total: usize,
    pub kind: u32,
    pub phase: u32,
    pub flags: i32,
    pub descriptor: i32,
    pub result: i32,
    pub anonymous: u32,
    pub anonymous_flags: i32,
}
#[repr(C)]
#[derive(Default)]
pub struct MappingEffect {
    pub memory: *mut c_void,
    pub size: usize,
    pub descriptor: i32,
    pub flags: i32,
    pub action: u32,
    pub result: i32,
}
fn effect(state: &MappingOperation, output: &mut MappingEffect, action: u32) -> i32 {
    output.memory = state.memory.cast();
    output.size = state.total;
    output.descriptor = state.descriptor;
    output.flags = state.flags;
    output.action = action;
    1
}
fn finish(
    state: &mut MappingOperation,
    output: &mut MappingEffect,
    memory: *mut u8,
    result: i32,
) -> i32 {
    state.phase = DONE;
    output.memory = memory.cast();
    output.result = result;
    0
}

/// Advance one single-use allocation/calloc, release, protect or relocation.
///1 requests a Native effect,0 completes with output,-1 rejects invalid control.
/// The Native caller resumes only after completing the requested effect. File
/// construction/destruction and syscall errno remain in that original scope.
/// # Safety
/// Independent initialized exclusive state/output. Native supplies actual fresh
/// effect results only, preserving kind/phase and all other cursor fields. Source
/// is a live initialized mapping when used; successful map/allocate results are
/// valid independent extents of the requested size, disjoint from control/output.
/// No class object, callback or borrow crosses this call. OS/free effects happen
/// only after return; later phases never dereference an already released token.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_memory_mapping_step(
    state: *mut MappingOperation,
    output: *mut MappingEffect,
) -> i32 {
    let Some(output) = (unsafe { output.as_mut() }) else {
        return -1;
    };
    *output = MappingEffect::default();
    let Some(state) = (unsafe { state.as_mut() }) else {
        return -1;
    };
    match (state.kind, state.phase) {
        (ALLOCATE, 0) => {
            if unsafe { swr_v1_memory_mapping_size(state.requested, &mut state.total) } != 0 {
                return finish(state, output, ptr::null_mut(), -1);
            }
            state.descriptor = -1;
            if state.anonymous != 0 {
                state.flags |= state.anonymous_flags;
                state.phase = 2;
                effect(state, output, 2)
            } else {
                state.phase = 1;
                effect(state, output, 1)
            }
        }
        (ALLOCATE, 1) => {
            if state.result == 0 {
                return finish(state, output, ptr::null_mut(), -1);
            }
            state.phase = 2;
            effect(state, output, 2)
        }
        (ALLOCATE, 2) => {
            if state.result == 0 {
                state.phase = 3;
                return effect(state, output, 3);
            }
            let payload = unsafe { swr_v1_memory_mapping_initialize(state.memory, state.total) };
            if payload.is_null() {
                state.phase = 4;
                effect(state, output, 4)
            } else {
                finish(state, output, payload, 0)
            }
        }
        (ALLOCATE, 3 | 4) => finish(state, output, ptr::null_mut(), -1),
        (RELEASE | PROTECT, 0) => {
            let Some(value) = (unsafe { extent(state.source) }) else {
                if state.kind == PROTECT {
                    state.phase = 2;
                    return effect(state, output, 7);
                }
                return -1;
            };
            state.memory = value.base.cast();
            state.total = value.total;
            state.phase = 1;
            effect(state, output, if state.kind == RELEASE { 4 } else { 6 })
        }
        (RELEASE, 1) => {
            if state.result < 0 {
                state.phase = 2;
                effect(state, output, 5)
            } else {
                finish(state, output, ptr::null_mut(), 0)
            }
        }
        (RELEASE, 2) => finish(state, output, ptr::null_mut(), 0),
        (PROTECT, 1) => {
            let result = state.result;
            finish(state, output, ptr::null_mut(), result)
        }
        (PROTECT, 2) => finish(state, output, ptr::null_mut(), -1),
        (REALLOCATE, 0) => {
            state.phase = 1;
            state.total = state.requested;
            effect(state, output, 8)
        }
        (REALLOCATE, 1) => {
            if state.memory.is_null() {
                return finish(state, output, ptr::null_mut(), -1);
            }
            if unsafe { swr_v1_memory_mapping_relocate(state.source, state.memory) } != 0 {
                state.phase = 2;
                effect(state, output, 9)
            } else {
                state.phase = 3;
                effect(state, output, 10);
                output.memory = state.source.cast();
                1
            }
        }
        (REALLOCATE, 2) => finish(state, output, ptr::null_mut(), -1),
        (REALLOCATE, 3) => {
            let memory = state.memory;
            finish(state, output, memory, 0)
        }
        _ => -1,
    }
}

#[cfg(test)]
#[path = "../../../tests/modules/memory/mapping_operation.rs"]
mod tests;
