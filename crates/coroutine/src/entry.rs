//! Whole core entry orchestration; all event/Coroutine effects are Native.
use core::ffi::c_long;
#[repr(C)]
pub struct CoroutineEntryCursor {
    pub mode: u32,
    pub phase: u32,
    pub managed: u8,
    pub cid: c_long,
}
#[repr(C)]
pub struct CoroutineEntryAction {
    pub action: u32,
    pub result: c_long,
}
/// # Safety
/// Exclusive initialized caller-local cursor, mode0(run) or1(create), phase0.
/// Native supplies fresh results only after requested effects; no Rust frame
/// survives event initialization, activation, function conversion/create, wait
/// or deactivation. There is no retained Native object/function reference.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_coroutine_entry_step(
    cursor: *mut CoroutineEntryCursor,
    observed: c_long,
) -> CoroutineEntryAction {
    // SAFETY: per this function's `# Safety` contract, `cursor` is live, aligned and exclusive.
    let c = unsafe { &mut *cursor };
    let action = match c.phase {
        0 if c.mode == 0 => {
            c.managed = 1;
            c.phase = 2;
            1
        }
        0 if c.mode == 1 => {
            c.phase = 1;
            0
        }
        1 if observed != 0 => {
            c.managed = 0;
            c.phase = 4;
            3
        }
        1 => {
            c.managed = 1;
            c.phase = 2;
            1
        }
        2 if observed < 0 => {
            c.cid = if c.mode == 0 { 0 } else { -1 };
            c.phase = 7;
            6
        }
        2 => {
            c.phase = 3;
            2
        }
        3 => {
            c.phase = 4;
            3
        }
        4 => {
            c.cid = observed;
            if c.managed == 0 {
                c.phase = 7;
                6
            } else {
                c.phase = 5;
                4
            }
        }
        5 => {
            c.phase = 6;
            5
        }
        6 => {
            if c.mode == 0 {
                c.cid = c_long::from(c.cid > 0)
            }
            c.phase = 7;
            6
        }
        _ => 6,
    };
    CoroutineEntryAction {
        action,
        result: c.cid,
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn complete_normal_entry_effect_order_and_return_policy() {
        for mode in 0..2 {
            for available in 0..2 {
                for cid in [0, 1, 7, 91] {
                    let mut c = CoroutineEntryCursor {
                        mode,
                        phase: 0,
                        managed: 0,
                        cid: 0,
                    };
                    let mut observed = 0;
                    let mut actions = Vec::new();
                    loop {
                        let a = unsafe { swr_v1_coroutine_entry_step(&mut c, observed) };
                        if a.action == 6 {
                            assert_eq!(
                                a.result,
                                if mode == 0 {
                                    c_long::from(cid > 0)
                                } else {
                                    cid
                                }
                            );
                            break;
                        }
                        actions.push(a.action);
                        observed = match a.action {
                            0 => available,
                            1 => 0,
                            3 => cid,
                            _ => observed,
                        };
                    }
                    assert_eq!(
                        actions,
                        if mode == 0 {
                            vec![1, 2, 3, 4, 5]
                        } else if available != 0 {
                            vec![0, 3]
                        } else {
                            vec![0, 1, 2, 3, 4, 5]
                        }
                    );
                }
            }
        }
    }
}
