//! Sole opt-in deferred-task queue. Native owns every payload and effect.
use crate::owner::{publish, release};
use std::collections::VecDeque;
use std::ptr;

pub struct ReactorDeferred {
    tasks: VecDeque<usize>,
}
/// Append one Native-owned payload identity; publish only after fallible reserve.
/// 0 committed, -2 allocation refusal, -1 invalid. Null owner is lazy empty.
/// # Safety
/// Slot is live/exclusive/aligned. Token is a stable nonzero Native Task identity,
/// transferred only on success; no payload is dereferenced or dropped by Rust.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_deferred_push(
    slot: *mut *mut ReactorDeferred,
    token: usize,
) -> i32 {
    let Some(slot) = (unsafe { slot.as_mut() }) else {
        return -1;
    };
    if token == 0 {
        return -1;
    }
    unsafe {
        publish(
            slot,
            || ReactorDeferred {
                tasks: VecDeque::new(),
            },
            |owner| {
                owner.tasks.try_reserve(1).map_err(|_| -2)?;
                owner.tasks.push_back(token);
                Ok((0, true))
            },
        )
    }
    .unwrap_or_else(|status| status)
}
/// Select front for Native stack-copy, then freshly detach for Native deletion.
/// Actions0done/1copyfront/2destroy-detached, -1 invalid. Native then performs
/// the fixed original delete/invoke/scoped-copy-destruction effect recipe;
/// no queue observation occurs until those effects finish.
/// # Safety
/// Owner is null/live/exclusive; phase/output aligned/exclusive/disjoint and
/// phase initially zero. Native completes each action after return. Source
/// payloads are live while copied; Rust never holds a span across any effect.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_deferred_step(
    owner: *mut ReactorDeferred,
    phase: *mut u32,
    token: *mut usize,
) -> i32 {
    let (Some(phase), Some(token)) = ((unsafe { phase.as_mut() }), (unsafe { token.as_mut() }))
    else {
        return -1;
    };
    *token = 0;
    match *phase {
        0 => {
            let Some(owner) = (unsafe { owner.as_ref() }) else {
                return 0;
            };
            if let Some(front) = owner.tasks.front() {
                *token = *front;
                *phase = 1;
                1
            } else {
                0
            }
        }
        1 => {
            let Some(owner) = (unsafe { owner.as_mut() }) else {
                return -1;
            };
            if let Some(front) = owner.tasks.pop_front() {
                *token = front;
                *phase = 0;
                2
            } else {
                -1
            }
        }
        _ => -1,
    }
}
/// Normal metadata cleanup: detach next token for Native deletion, or free empty
/// metadata and publish null. 1delete/0complete/-1invalid. Never invokes a task.
/// # Safety
/// Live exclusive/disjoint slot/output. Native deletes each returned payload
/// after Rust returns. Custom destruction/reentry/lifetime behavior unqualified.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_reactor_deferred_clear(
    slot: *mut *mut ReactorDeferred,
    token: *mut usize,
) -> i32 {
    let (Some(slot), Some(token)) = ((unsafe { slot.as_mut() }), (unsafe { token.as_mut() }))
    else {
        return -1;
    };
    *token = 0;
    let Some(owner) = (unsafe { (*slot).as_mut() }) else {
        return 0;
    };
    if let Some(front) = owner.tasks.pop_front() {
        *token = front;
        return 1;
    }
    unsafe { release(*slot) };
    *slot = ptr::null_mut();
    0
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn deferred_positive_fifo_and_separate_round_identity() {
        unsafe {
            let mut first = ptr::null_mut();
            let mut next = ptr::null_mut();
            for value in [101, 102, 103] {
                assert_eq!(swr_v1_reactor_deferred_push(&mut first, value), 0);
            }
            let mut phase = 0;
            let mut token = 0;
            let mut trace = Vec::new();
            while swr_v1_reactor_deferred_step(first, &mut phase, &mut token) == 1 {
                let copied = token;
                assert_eq!(
                    swr_v1_reactor_deferred_step(first, &mut phase, &mut token),
                    2
                );
                assert_eq!(token, copied);
                trace.push((2, token));
                // Native invokes the copied Task only after the fresh pop;
                // no Native payload is executed by this Rust token unit.
                trace.push((3, copied));
                if copied == 101 {
                    assert_eq!(swr_v1_reactor_deferred_push(&mut next, 201), 0);
                }
                trace.push((4, copied));
            }
            assert_eq!(
                trace,
                [
                    (2, 101),
                    (3, 101),
                    (4, 101),
                    (2, 102),
                    (3, 102),
                    (4, 102),
                    (2, 103),
                    (3, 103),
                    (4, 103)
                ]
            );
            assert_eq!(swr_v1_reactor_deferred_clear(&mut first, &mut token), 0);
            assert!(first.is_null());
            assert_eq!(
                swr_v1_reactor_deferred_step(next, &mut phase, &mut token),
                1
            );
            assert_eq!(token, 201);
            assert_eq!(
                swr_v1_reactor_deferred_step(next, &mut phase, &mut token),
                2
            );
            assert_eq!(token, 201);
            assert_eq!(
                swr_v1_reactor_deferred_step(next, &mut phase, &mut token),
                0
            );
            assert_eq!(swr_v1_reactor_deferred_clear(&mut next, &mut token), 0);
            assert!(next.is_null());
        }
    }
}
