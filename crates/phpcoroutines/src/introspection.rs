//! Whole self/target introspection routing with native executor custody.
#[repr(C)]
pub struct TracePlan {
    pub action: u32,
    pub skip_last: i32,
}

/// No context/executor pointer enters Rust. Native captures its backup, publishes
/// the target, performs Zend tracing, and restores only after each plan returns.
/// # Safety
/// Stage is exclusive writable native POD, initially zero. Observation answers
/// the last requested scalar fact; printing is the stable caller mode.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_trace(
    stage: *mut u32,
    cid: i64,
    observation: i64,
    printing: u8,
) -> TracePlan {
    // SAFETY: per this function's `# Safety` contract, `stage` is live, aligned and exclusive.
    let stage = unsafe { &mut *stage };
    let current = *stage;
    *stage = current.saturating_add(1);
    let mut skip_last = 0;
    let action = match current {
        0 if cid == 0 => {
            *stage = 99;
            skip_last = i32::from(printing != 0);
            2
        }
        0 => 1, // native current cid only for nonzero request
        1 if cid == observation => {
            *stage = 99;
            skip_last = i32::from(printing != 0);
            2
        }
        1 => 3, // native context lookup
        2 if observation == 0 => {
            *stage = 5;
            4
        } // native missing error
        2 => 5, // native backup and executor switch
        3 => 6, // native target trace
        4 => {
            *stage = 99;
            7
        } // native restoration
        5 => 8, // fresh native return-value presence after missing error
        6 if observation != 0 => {
            *stage = 99;
            9
        } // native false publication
        _ => {
            *stage = 99;
            0
        }
    };
    TracePlan { action, skip_last }
}
