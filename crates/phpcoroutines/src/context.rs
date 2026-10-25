//! Common frontend routing and stack accounting over copied native facts only.
/// Route a whole context query. Native context identity never enters Rust.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_phpcoroutines_context_route(kind: u32, cid: i64, present: u8) -> u32 {
    match kind {
        0 => u32::from(present != 0), // active/value admission: none or current
        1 if cid == 0 => 1,           // parent lookup: current
        1 => 2,                       // parent lookup: by id
        2 if present == 0 => 3,       // current/origin fallback: main
        2 => 1,
        3 if cid == -1 => 3, // id lookup: main
        3 => 2,
        _ => 0,
    }
}

/// Scheduler admission. Clock access and writes are native effects after return.
/// Signed subtraction is widened: the original defined int64 difference domain
/// is identical; native signed-overflow inputs are outside the parity claim.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_phpcoroutines_scheduler_policy(
    kind: u32,
    present: u8,
    enabled: u8,
    now: i64,
    last: i64,
    limit: u8,
) -> u8 {
    u8::from(match kind {
        0 => enabled != 0, // clock admission, preserving disabled short circuit
        1 => i128::from(now) - i128::from(last) > i128::from(limit),
        2 => present != 0 && enabled == 0, // enable
        3 => present != 0 && enabled != 0, // disable
        4 => present != 0,                 // record clock only while interrupt thread is running
        _ => false,
    })
}

#[repr(C)]
pub struct StackState {
    pub cid: i64,
    pub current_cid: i64,
    pub usage: usize,
    pub stage: u32,
}

/// Whole stack walk sequencing and size_t wrapping accounting. A page is never
/// borrowed by Rust: native reads valid pointer-difference facts and next links.
/// # Safety
/// State is exclusive writable native POD, with requested cid and zeroed stage.
/// Observation answers the previous request; bytes are the native page byte fact.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_stack_step(
    state: *mut StackState,
    observation: i64,
    bytes: usize,
) -> u32 {
    let state = unsafe { &mut *state };
    match state.stage {
        0 => {
            state.stage = 1;
            1
        } // current cid
        1 => {
            state.current_cid = observation;
            if state.cid == 0 {
                state.cid = observation;
            }
            state.stage = 2;
            2 // context by effective cid
        }
        2 if observation == 0 => {
            state.stage = 99;
            3
        } // native missing error
        2 => {
            state.stage = 3;
            if state.cid == state.current_cid { 4 } else { 5 } // live/saved page
        }
        3 | 5 if observation != 0 => {
            state.stage = 4;
            6
        } // native page bytes
        3 | 5 => {
            state.stage = 99;
            0
        }
        4 => {
            state.usage = state.usage.wrapping_add(bytes);
            state.stage = 5;
            7 // native next page
        }
        _ => 0,
    }
}

/// Complete PHP context-object query/lazy-publication and scalar query-result
/// policy. Native captures the context once and refreshes its object facts after
/// effects. No context/object pointer or Zend reference enters Rust.
/// # Safety
/// For context kind 0, stage is exclusive writable zero-initialized native POD.
/// For scalar parent/stack result kinds 1/2, stage may be null.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_context_query(
    kind: u32,
    stage: *mut u32,
    cid: i64,
    observation: i64,
) -> u32 {
    if kind != 0 {
        return if (kind == 1 && observation == 0) || (kind == 2 && observation < 0) {
            9 // false result
        } else {
            10
        }; // original signed long result
    }
    let stage = unsafe { &mut *stage };
    let current = *stage;
    *stage = current.saturating_add(1);
    match current {
        0 if cid == 0 => 1, // native current task
        0 => 2,             // native by-id task (no main-context substitution)
        1 if observation == 0 => {
            *stage = 99;
            3
        } // native missing error
        1 => 4,             // native destroyed-sentinel comparison
        2 if observation != 0 => {
            *stage = 99;
            5
        } // native destroyed warning
        2 => 6,             // fresh native object-presence observation
        3 if observation == 0 => 7, // native object initialization/field publication
        3 | 4 => {
            *stage = 99;
            8
        } // fresh native GC addref/return
        _ => 0,
    }
}
