//! Complete context construction/invocation/cleanup policy over fresh scalar facts.
//! Native owns Zend storage, try/catch and effects; no context enters Rust.
#[repr(u32)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Action {
    Done,
    CtorInit,
    CtorFiber,
    CtorFiberInit,
    CtorFiberNone,
    CtorVm,
    CtorCallable,
    CtorCallableCopy,
    CtorCallableUndef,
    CtorPersist,
    CtorReturn,
    MainTrace,
    MainHook,
    MainHookCall,
    MainFiber,
    MainUserFunction,
    MainNotify,
    MainInvoke,
    MainDefer,
    MainDeferDrain,
    DeferValue,
    DeferParams,
    DeferInvoke,
    DeferWarn,
    DeferException,
    DeferBailout,
    DeferClean,
    DestroyHook,
    DestroyHookCall,
    DestroyOutput,
    DestroySaveHeaders,
    DestroyActive,
    DestroyEndOutput,
    DestroyRestartOutput,
    DestroyDefer,
    DestroyDeferDrain,
    DestroyObject,
    DestroyObjectRelease,
    DestroyResources,
    PostDestroy,
    PostException,
    PostBailout,
    RegisterContext,
    RegisterOwner,
    RegisterAllocate,
    RegisterPush,
}

/// # Safety
/// Stage is exclusive zeroed local POD, kind fixed in0..5; observation is the
/// requested fresh Native fact. For main invocation declare stage INSIDE the
/// Native zend_first_try block, discard it on Native longjmp and create fresh
/// post-try stage afterward. Native try/catch and exception-caught result carrier
/// stay Native, as do every Zend/VM/context/callback/queue payload and all effects.
/// No Rust borrow/frame spans Native allocation, callback, GC, yield or bailout.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_lifecycle(
    stage: *mut u32,
    kind: u32,
    observation: i64,
) -> u32 {
    use Action::*;
    let stage = unsafe { &mut *stage };
    loop {
        let current = *stage;
        *stage = current.saturating_add(1);
        let action = match kind {
            0 => match current {
                0 => CtorInit,
                1 => CtorFiber,
                2 => {
                    if observation != 0 {
                        CtorFiberInit
                    } else {
                        CtorFiberNone
                    }
                }
                3 => CtorVm,
                4 => CtorCallable,
                5 => {
                    if observation != 0 {
                        CtorCallableCopy
                    } else {
                        CtorCallableUndef
                    }
                }
                6 => CtorPersist,
                7 => CtorReturn,
                _ => Done,
            },
            1 => match current {
                0 => MainTrace,
                1 => MainHook,
                2 if observation != 0 => MainHookCall,
                2 => continue,
                3 => MainFiber,
                4 if observation != 0 => MainUserFunction,
                4 => {
                    *stage = 6;
                    continue;
                }
                5 if observation != 0 => MainNotify,
                5 => continue,
                6 => MainInvoke,
                7 => MainDefer,
                8 if observation != 0 => MainDeferDrain,
                _ => Done,
            },
            2 => match current {
                0 => DeferValue,
                1 if observation != 0 => DeferParams,
                1 => continue,
                2 => DeferInvoke,
                3 if observation != 0 => DeferWarn,
                3 => continue,
                4 => DeferException,
                5 if observation != 0 => DeferBailout,
                5 => continue,
                6 => DeferClean,
                _ => Done,
            },
            3 => match current {
                0 => DestroyHook,
                1 if observation != 0 => DestroyHookCall,
                1 => continue,
                2 => DestroyOutput,
                3 if observation != 0 => DestroySaveHeaders,
                3 => {
                    *stage = 7;
                    continue;
                }
                4 => DestroyActive,
                5 if observation != 0 => DestroyEndOutput,
                5 => continue,
                6 => DestroyRestartOutput,
                7 => DestroyDefer,
                8 if observation != 0 => DestroyDeferDrain,
                8 => continue,
                9 => DestroyObject,
                10 if observation != 0 => DestroyObjectRelease,
                10 => continue,
                11 => DestroyResources,
                _ => Done,
            },
            4 => match current {
                0 => PostDestroy,
                1 => PostException,
                2 if observation != 0 => PostBailout,
                _ => Done,
            },
            5 => match current {
                0 => RegisterContext,
                1 => RegisterOwner,
                2 if observation == 0 => RegisterAllocate,
                2 => continue,
                3 => RegisterPush,
                _ => Done,
            },
            _ => Done,
        };
        if action == Done {
            *stage = u32::MAX;
        }
        return action as u32;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn trace(kind: u32, facts: &[i64]) -> Vec<u32> {
        let mut stage = 0;
        let mut fact = 0;
        let mut facts = facts.iter();
        let mut out = Vec::new();
        loop {
            let action = unsafe { swr_v1_phpcoroutines_lifecycle(&mut stage, kind, fact) };
            if action == 0 {
                break;
            }
            out.push(action);
            if matches!(
                action,
                2 | 6 | 12 | 14 | 15 | 18 | 20 | 22 | 24 | 27 | 29 | 31 | 34 | 36 | 40 | 43
            ) {
                fact = *facts.next().unwrap();
            }
            // Native longjmp discards the local defer cursor, no later cleanup.
            if action == Action::DeferBailout as u32 {
                break;
            }
        }
        assert!(facts.next().is_none());
        out
    }
    #[test]
    fn constructor_hook_output_and_owner_short_circuits() {
        for fiber in [0, 1] {
            for callable in [0, 1] {
                assert_eq!(
                    trace(0, &[fiber, callable]),
                    vec![
                        1,
                        2,
                        if fiber != 0 { 3 } else { 4 },
                        5,
                        6,
                        if callable != 0 { 7 } else { 8 },
                        9,
                        10
                    ]
                );
            }
        }
        assert_eq!(trace(1, &[0, 0, 0]), vec![11, 12, 14, 17, 18]);
        assert_eq!(
            trace(1, &[1, 1, 1, 1]),
            vec![11, 12, 13, 14, 15, 16, 17, 18, 19]
        );
        assert_eq!(trace(1, &[0, 1, 0, 1]), vec![11, 12, 14, 15, 17, 18, 19]);
        assert_eq!(trace(3, &[0, 0, 0, 0]), vec![27, 29, 34, 36, 38]);
        assert_eq!(
            trace(3, &[1, 1, 0, 1, 1]),
            vec![27, 28, 29, 30, 31, 33, 34, 35, 36, 37, 38]
        );
        assert_eq!(
            trace(3, &[0, 1, 1, 0, 1]),
            vec![27, 29, 30, 31, 32, 33, 34, 36, 37, 38]
        );
        assert_eq!(trace(5, &[0]), vec![42, 43, 44, 45]);
        assert_eq!(trace(5, &[1]), vec![42, 43, 45]);
    }
    #[test]
    fn deferred_results_refresh_after_warning_and_post_cleanup_bailout() {
        for defined in [0, 1] {
            for failed in [0, 1] {
                for exception in [0, 1] {
                    let mut expected = vec![20];
                    if defined != 0 {
                        expected.push(21);
                    }
                    expected.push(22);
                    if failed != 0 {
                        expected.push(23);
                    }
                    expected.push(24);
                    expected.push(if exception != 0 { 25 } else { 26 });
                    assert_eq!(trace(2, &[defined, failed, exception]), expected);
                }
            }
        }
        assert_eq!(trace(4, &[0]), vec![39, 40]);
        assert_eq!(trace(4, &[1]), vec![39, 40, 41]);
    }
}
