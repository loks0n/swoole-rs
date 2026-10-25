// SPDX-License-Identifier: Apache-2.0
//! First-party TLS/DTLS decisions. No OpenSSL calls, callbacks, allocation or stored pointers.
use core::ffi::c_long;
const ALL: u32 = 0x7e;
const DTLS: u32 = 0x80;

/// Copy the native password callback's initialized bytes, retaining its strict
/// length < capacity - 1 rule and the original native String-to-int conversion.
///
/// # Safety
/// On an accepted copy, source holds `length` initialized bytes and destination
/// holds at least `length + 1` writable bytes, without overlap. Native String,
/// SSL and callback custody remain with the caller. Rejected copies touch neither
/// pointer. A nonempty String can have narrowed length0 on a native target; that
/// case still writes the original terminator. Negative narrowed copy lengths and
/// nonempty/INT_MIN capacity border original UB and are not parity/safety claims.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_tls_password(
    source: *const u8,
    nonempty: u8,
    length: i32,
    destination: *mut u8,
    capacity: i32,
) -> i32 {
    if nonempty == 0 || length < 0 || i64::from(length) >= i64::from(capacity) - 1 {
        return 0;
    }
    // No slice, allocation, callback, panic, destructor or retained native borrow.
    unsafe {
        if length != 0 {
            core::ptr::copy_nonoverlapping(source, destination, length as usize);
        }
        destination.add(length as usize).write(0);
    }
    length
}

#[repr(C)]
#[derive(Debug, Copy, Clone)]
pub struct ContextPlan {
    pub protocols: u32,
    pub disabled: u32,
    pub dtls: u8,
}

/// Method selection observes the original mask before zero normalization.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_tls_context(protocols: u32, supports_dtls: u8) -> ContextPlan {
    let normalized = if protocols == 0 { ALL } else { protocols };
    let disabled = !normalized & ALL;
    ContextPlan {
        protocols: normalized,
        disabled: if normalized & DTLS != 0 {
            disabled & !0x20
        } else {
            disabled
        },
        dtls: u8::from(supports_dtls != 0 && protocols & DTLS != 0),
    }
}

#[repr(C)]
#[derive(Debug, Copy, Clone, PartialEq, Eq)]
pub struct ReadPlan {
    pub length: i32,
    pub consume: u8,
    pub retry: u8,
}

/// Native callers only copy initialized datagrams with nonnegative requested length.
/// Negative lengths in the pinned BIO adapter lead to an invalid native memmove;
/// this scalar plan preserves the signed result without forming any Rust slice.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_tls_read(empty: u8, front: u16, requested: i32, peek: u8) -> ReadPlan {
    if empty != 0 {
        ReadPlan {
            length: -1,
            consume: 0,
            retry: 1,
        }
    } else {
        ReadPlan {
            length: i32::from(front).min(requested),
            consume: u8::from(peek == 0),
            retry: 0,
        }
    }
}

#[repr(C)]
#[derive(Debug, Copy, Clone, PartialEq, Eq)]
pub struct ControlPlan {
    pub result: c_long,
    pub effect: u32,
}

// Tags are decoded from the actual compiled OpenSSL macros by native code.
// Effects: 0 none, 1 set shutdown, 2 copy peer, 3 set peek, 4 warn unknown.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_tls_control(tag: u32, observed: c_long) -> ControlPlan {
    let (result, effect) = match tag {
        0..=2 => (observed, 0), // EOF, shutdown, total queued bytes
        3 => (0, 1),
        4 => (1, 0),
        5 => (1, 2),
        6 => (1500, 0),
        7 => (96, 0),
        8 => (1, 3),
        9 => (0, 0),
        _ => (0, 4),
    };
    ControlPlan { result, effect }
}

/// 0: failure/warn, 1: pending success, 2: success and publish listened.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_tls_listen(result: i32) -> u32 {
    match result.cmp(&0) {
        core::cmp::Ordering::Less => 0,
        core::cmp::Ordering::Equal => 1,
        core::cmp::Ordering::Greater => 2,
    }
}

#[repr(C)]
#[derive(Debug, Copy, Clone, PartialEq, Eq)]
pub struct SetupPlan {
    pub action: u32,
    pub next: u32,
}

#[repr(u32)]
#[derive(Copy, Clone)]
enum SetupAction {
    False,
    True,
    Password,
    Cert,
    Chain,
    Key,
    CheckKey,
    Cookie,
    Capath,
    NoVerify,
    Alpn,
    AlpnInstall,
    Grease,
    ClientCa,
    Ciphers,
    Observe,
    LoadCa,
    DefaultCa,
    VerifyDepth,
    CipherList,
    CipherPreference,
    DhParam,
    EcdhCurve,
    ClientVerifyInstall,
    ClientTrust,
    ClientNames,
    ClientNamesInstall,
    DhOpen,
    DhParse,
    DhInstall,
    DhOpenFailed,
    DhParseFailed,
    DhInstallFailed,
    DhRelease,
    CurveOptions,
    CurveList,
    CurveListFailed,
    CurveName,
    CurveUnknown,
    CurveKey,
    CurveKeyFailed,
    CurveInstall,
    InfoStartSocket,
    InfoRenegotiate,
    InfoLoopSocket,
    InfoBios,
    InfoBuffer,
    SessionCreate,
    SessionCreateFailed,
    SessionBindBio,
}
/// One native caller-stack cursor, copied facts and the preceding native result.
/// Returns the next native action. No native operation executes under this frame.
/// Facts: password,cert,key,cookie-capable-DTLS,verify,http,boring,clientCA.
/// Observe requests a fresh fact at next stage; never eagerly snapshot later fields.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_tls_setup(stage: u32, facts: u32, result: i32) -> SetupPlan {
    let (action, next) = match stage {
        // Disjoint entry cursors for the existing native CA/cipher methods.
        // A fact is bit0 at its own stage; later public fields stay unobserved.
        100 if facts & 1 != 0 => (SetupAction::LoadCa, 101),
        100 => (SetupAction::DefaultCa, 101),
        101 if result == 0 => (SetupAction::False, 17),
        101 => (SetupAction::Observe, 102),
        102 if facts & 1 != 0 => (SetupAction::VerifyDepth, 103),
        102 | 103 => (SetupAction::True, 17),
        700 if facts != 0 => (SetupAction::False, 17),
        700 => (SetupAction::SessionCreate, 701),
        701 if result < 0 => (SetupAction::SessionCreateFailed, 799),
        701 => (SetupAction::SessionBindBio, 702),
        702 => (SetupAction::True, 17),
        799 => (SetupAction::False, 17),
        600 if facts != 0 => (SetupAction::InfoStartSocket, 601),
        600 => (SetupAction::Observe, 602),
        601 if result != 0 => (SetupAction::InfoRenegotiate, 602),
        601 => (SetupAction::Observe, 602),
        602 if facts != 0 => (SetupAction::InfoLoopSocket, 603),
        602 => (SetupAction::True, 17),
        603 if result != 0 => (SetupAction::InfoBios, 604),
        603 => (SetupAction::True, 17),
        604 if result != 0 => (SetupAction::InfoBuffer, 605),
        604 | 605 => (SetupAction::True, 17),
        500 if facts == 0 => (SetupAction::True, 17), // Compiled without ECDH: no field observation/effect.
        500 if facts == 1 => (SetupAction::CurveOptions, 501),
        500 if facts == 2 => (SetupAction::CurveName, 503),
        501 if facts != 0 => (SetupAction::True, 17), // Literal auto after native options.
        501 => (SetupAction::CurveList, 502),
        502 if result == 0 => (SetupAction::CurveListFailed, 599),
        502 => (SetupAction::True, 17),
        503 if result == 0 => (SetupAction::CurveUnknown, 599),
        503 => (SetupAction::CurveKey, 504),
        504 if result == 0 => (SetupAction::CurveKeyFailed, 599),
        504 => (SetupAction::CurveInstall, 505),
        505 => (SetupAction::True, 17),
        599 => (SetupAction::False, 17),
        400 => (SetupAction::DhOpen, 401),
        401 if result == 0 => (SetupAction::DhOpenFailed, 450),
        401 => (SetupAction::DhParse, 402),
        402 if result == 0 => (SetupAction::DhParseFailed, 450),
        402 => (SetupAction::DhInstall, 403),
        403 if result == 0 => (SetupAction::DhInstallFailed, 450),
        403 => (SetupAction::DhRelease, 451),
        450 => (SetupAction::False, 17),
        451 => (SetupAction::True, 17),
        300 => (SetupAction::ClientVerifyInstall, 301),
        301 => (SetupAction::ClientTrust, 302),
        302 if result == 0 => (SetupAction::False, 17),
        302 => (SetupAction::ClientNames, 303),
        303 if result == 0 => (SetupAction::False, 17),
        303 => (SetupAction::ClientNamesInstall, 304),
        304 => (SetupAction::True, 17),
        200 if facts & 1 != 0 => (SetupAction::CipherList, 201),
        200 => (SetupAction::Observe, 204),
        201 if result == 0 => (SetupAction::False, 17),
        201 => (SetupAction::Observe, 202),
        202 if facts & 1 != 0 => (SetupAction::CipherPreference, 203),
        202 => (SetupAction::Observe, 204),
        203 if result == 0 => (SetupAction::False, 17),
        203 => (SetupAction::Observe, 204),
        204 if facts & 1 != 0 => (SetupAction::DhParam, 205),
        204 => (SetupAction::Observe, 206),
        205 if result == 0 => (SetupAction::False, 17),
        205 => (SetupAction::Observe, 206),
        206 if facts & 1 != 0 => (SetupAction::EcdhCurve, 207),
        206 => (SetupAction::True, 17),
        207 if result != 0 => (SetupAction::True, 17),
        0 if facts & 1 != 0 => (SetupAction::Password, 1),
        0 => (SetupAction::Observe, 1),
        1 if facts & 2 != 0 => (SetupAction::Cert, 2),
        1 => (SetupAction::Observe, 4),
        2 if result <= 0 => (SetupAction::False, 17),
        2 => (SetupAction::Chain, 3),
        3 if result <= 0 => (SetupAction::False, 17),
        3 => (SetupAction::Observe, 4),
        4 if facts & 4 != 0 => (SetupAction::Key, 5),
        4 => (SetupAction::Observe, 7),
        5 if result <= 0 => (SetupAction::False, 17),
        5 => (SetupAction::CheckKey, 6),
        6 if result == 0 => (SetupAction::False, 17),
        6 => (SetupAction::Observe, 7),
        7 if facts & 8 != 0 => (SetupAction::Cookie, 8),
        7 => (SetupAction::Observe, 8),
        8 => (SetupAction::Capath, 9),
        9 if facts & 16 != 0 && result == 0 => (SetupAction::False, 17),
        9 if facts & 16 == 0 => (SetupAction::NoVerify, 10),
        9 => (SetupAction::Observe, 10),
        10 if facts & 32 != 0 => (SetupAction::Alpn, 11),
        10 => (SetupAction::Observe, 12),
        11 if result < 0 => (SetupAction::False, 17), // Preserve <0, not !=0.
        11 => (SetupAction::AlpnInstall, 12),
        12 if facts & 64 != 0 => (SetupAction::Grease, 13),
        12 => (SetupAction::Observe, 13),
        13 if facts & 128 != 0 => (SetupAction::ClientCa, 14),
        13 => (SetupAction::Observe, 15),
        14 if result == 0 => (SetupAction::False, 17),
        14 => (SetupAction::Observe, 15),
        15 => (SetupAction::Ciphers, 16),
        16 if result != 0 => (SetupAction::True, 17),
        _ => (SetupAction::False, 17),
    };
    SetupPlan {
        action: action as u32,
        next,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn password_keeps_strict_spare_byte_canaries_and_embedded_nuls() {
        let source = *b"a\0b";
        for capacity in [0, 1, 3, 4] {
            let mut output = [0x55; 8];
            assert_eq!(
                unsafe {
                    swr_v1_tls_password(source.as_ptr(), 1, 3, output.as_mut_ptr(), capacity)
                },
                0
            );
            assert_eq!(output, [0x55; 8]);
        }
        for capacity in [5, 8] {
            let mut output = [0x55; 8];
            assert_eq!(
                unsafe {
                    swr_v1_tls_password(source.as_ptr(), 1, 3, output.as_mut_ptr(), capacity)
                },
                3
            );
            assert_eq!(output, [b'a', 0, b'b', 0, 0x55, 0x55, 0x55, 0x55]);
        }
        // Empty ignores all other copied facts/pointers. Nonempty+narrowed0 has
        // a different native rule: it writes the terminator if capacity permits.
        assert_eq!(
            unsafe { swr_v1_tls_password(core::ptr::null(), 0, 0, core::ptr::null_mut(), 8) },
            0
        );
        let mut output = [0x55; 2];
        assert_eq!(
            unsafe { swr_v1_tls_password(core::ptr::null(), 1, 0, output.as_mut_ptr(), 2) },
            0
        );
        assert_eq!(output, [0, 0x55]);
    }

    #[test]
    fn dtls_session_init_has_one_native_creation_and_exact_failure_cutoff() {
        assert_eq!(swr_v1_tls_setup(700, 1, 0).action, 0);
        assert_eq!(swr_v1_tls_setup(700, 0, 0).action, 47);
        for result in [i32::MIN, -1, 0, 1, i32::MAX] {
            let p = swr_v1_tls_setup(701, 0, result);
            if result < 0 {
                assert_eq!((p.action, p.next), (48, 799));
                assert_eq!(swr_v1_tls_setup(p.next, 0, 0).action, 0);
            } else {
                assert_eq!((p.action, p.next), (49, 702));
                assert_eq!(swr_v1_tls_setup(p.next, 0, 0).action, 1);
            }
        }
    }

    #[test]
    fn info_callback_observes_each_event_and_socket_only_when_reached() {
        for start in [false, true] {
            for accept in [false, true] {
                for ready in [false, true] {
                    for unset in [false, true] {
                        for split in [false, true] {
                            let (mut stage, mut result) = (600, 0);
                            let mut actual = Vec::new();
                            for _ in 0..10 {
                                let facts = match stage {
                                    600 => u32::from(start),
                                    602 => u32::from(accept),
                                    _ => 0,
                                };
                                let p = swr_v1_tls_setup(stage, facts, result);
                                stage = p.next;
                                if p.action == 1 {
                                    break;
                                }
                                if p.action != 15 {
                                    actual.push(p.action);
                                }
                                result = match p.action {
                                    42 => i32::from(ready),
                                    44 => i32::from(unset),
                                    45 => i32::from(split),
                                    _ => 0,
                                };
                            }
                            let mut expected = Vec::new();
                            if start {
                                expected.push(42);
                                if ready {
                                    expected.push(43);
                                }
                            }
                            if accept {
                                expected.push(44);
                                if unset {
                                    expected.push(45);
                                    if split {
                                        expected.push(46);
                                    }
                                }
                            }
                            assert_eq!(actual, expected);
                            assert_eq!(stage, 17);
                        }
                    }
                }
            }
        }
    }

    #[test]
    fn curve_capabilities_and_failure_cutoffs_preserve_native_order() {
        fn trace(mode: u32, auto: bool, failed: u32, failure: i32) -> Vec<u32> {
            let (mut stage, mut result) = (500, 1);
            let mut effects = Vec::new();
            for _ in 0..12 {
                let facts = match stage {
                    500 => mode,
                    501 => u32::from(auto),
                    _ => 0,
                };
                let plan = swr_v1_tls_setup(stage, facts, result);
                effects.push(plan.action);
                if plan.action <= 1 {
                    return effects;
                }
                result = if plan.action == failed { failure } else { 1 };
                stage = plan.next;
            }
            panic!("curve cursor did not terminate");
        }
        assert_eq!(trace(0, false, 0, 0), vec![1]);
        assert_eq!(trace(1, true, 0, 0), vec![34, 1]);
        assert_eq!(trace(1, false, 0, 0), vec![34, 35, 1]);
        assert_eq!(trace(1, false, 35, 0), vec![34, 35, 36, 0]);
        assert_eq!(trace(1, false, 35, -1), vec![34, 35, 1]); // Original checks ==0.
        assert_eq!(trace(2, false, 0, 0), vec![37, 39, 41, 1]);
        assert_eq!(trace(2, true, 0, 0), vec![37, 39, 41, 1]); // No legacy auto special case.
        assert_eq!(trace(2, false, 37, 0), vec![37, 38, 0]);
        assert_eq!(trace(2, false, 39, 0), vec![37, 39, 40, 0]);
        assert_eq!(trace(2, false, 41, 0), vec![37, 39, 41, 1]); // Original ignores installation result.
    }
    #[test]
    fn subordinate_methods_preserve_lazy_order_and_failure_cutoffs() {
        fn trace(start: u32, enabled: bool, failed_action: u32) -> (Vec<u32>, Vec<u32>) {
            let mut stage = start;
            let mut result = 1;
            let (mut effects, mut observations) = (Vec::new(), Vec::new());
            for _ in 0..32 {
                let facts = match stage {
                    100 | 102 | 200 | 202 | 204 | 206 => {
                        observations.push(stage);
                        u32::from(enabled)
                    }
                    _ => 0,
                };
                let plan = swr_v1_tls_setup(stage, facts, result);
                stage = plan.next;
                match plan.action {
                    0 | 1 => {
                        effects.push(plan.action);
                        return (effects, observations);
                    }
                    15 => (),
                    action => {
                        effects.push(action);
                        result = i32::from(action != failed_action);
                    }
                }
            }
            panic!("subordinate cursor did not terminate");
        }
        assert_eq!(trace(400, false, 0).0, vec![27, 28, 29, 33, 1]);
        assert_eq!(trace(400, false, 27).0, vec![27, 30, 0]);
        assert_eq!(trace(400, false, 28).0, vec![27, 28, 31, 0]);
        assert_eq!(trace(400, false, 29).0, vec![27, 28, 29, 32, 0]);
        assert_eq!(trace(300, false, 0), (vec![23, 24, 25, 26, 1], vec![]));
        assert_eq!(trace(300, false, 24), (vec![23, 24, 0], vec![]));
        assert_eq!(trace(300, false, 25), (vec![23, 24, 25, 0], vec![]));
        assert_eq!(trace(100, true, 0), (vec![16, 18, 1], vec![100, 102]));
        assert_eq!(trace(100, false, 0), (vec![17, 1], vec![100, 102]));
        assert_eq!(trace(100, true, 16), (vec![16, 0], vec![100]));
        assert_eq!(trace(100, false, 17), (vec![17, 0], vec![100]));
        assert_eq!(trace(200, false, 0), (vec![1], vec![200, 204, 206]));
        assert_eq!(trace(200, true, 0).0, vec![19, 20, 21, 22, 1]);
        for failed in 19..=22 {
            let expected: Vec<u32> = (19..=failed).chain([0]).collect();
            assert_eq!(trace(200, true, failed).0, expected);
        }
    }
    #[test]
    fn every_protocol_mask_preserves_dtls_exception() {
        for protocols in 0..512 {
            for support in [0, 1] {
                let p = swr_v1_tls_context(protocols, support);
                let expected = if protocols == 0 { ALL } else { protocols };
                assert_eq!(p.protocols, expected);
                assert_eq!(p.dtls != 0, support != 0 && protocols & DTLS != 0);
                for bit in [2, 4, 8, 16, 32, 64] {
                    assert_eq!(
                        p.disabled & bit != 0,
                        expected & bit == 0 && !(bit == 32 && expected & DTLS != 0)
                    );
                }
            }
        }
    }
    #[test]
    fn zero_short_and_peek_datagrams() {
        for front in [0, 1, 255, 65535] {
            for requested in [0, 1, 256, 65536, i32::MAX] {
                for peek in [0, 1] {
                    let p = swr_v1_tls_read(0, front, requested, peek);
                    assert_eq!(p.length, i32::from(front).min(requested));
                    assert_eq!(p.consume, u8::from(peek == 0));
                    assert_eq!(p.retry, 0);
                }
            }
        }
        assert_eq!(
            swr_v1_tls_read(1, 0, 0, 0),
            ReadPlan {
                length: -1,
                consume: 0,
                retry: 1
            }
        );
    }
    #[test]
    fn control_observations_and_effects() {
        for value in [c_long::MIN, -1, 0, 1, c_long::MAX] {
            for tag in 0..=2 {
                assert_eq!(swr_v1_tls_control(tag, value).result, value);
            }
        }
        assert_eq!(
            swr_v1_tls_control(3, 99),
            ControlPlan {
                result: 0,
                effect: 1
            }
        );
        assert_eq!(
            swr_v1_tls_control(5, 0),
            ControlPlan {
                result: 1,
                effect: 2
            }
        );
        assert_eq!(
            swr_v1_tls_control(8, 0),
            ControlPlan {
                result: 1,
                effect: 3
            }
        );
        assert_eq!(
            swr_v1_tls_control(u32::MAX, 0),
            ControlPlan {
                result: 0,
                effect: 4
            }
        );
    }
    #[test]
    fn listen_pending_is_success_without_publication() {
        for x in [i32::MIN, -1] {
            assert_eq!(swr_v1_tls_listen(x), 0);
        }
        assert_eq!(swr_v1_tls_listen(0), 1);
        for x in [1, i32::MAX] {
            assert_eq!(swr_v1_tls_listen(x), 2);
        }
    }
    #[test]
    fn setup_effect_order_and_early_outcomes() {
        fn trace(facts: u32, fail_action: u32, failure: i32) -> Vec<u32> {
            let (mut stage, mut result) = (0, 1);
            let mut actions = Vec::new();
            for _ in 0..32 {
                let field = match stage {
                    0 => 1,
                    1 => 2,
                    4 => 4,
                    7 => 8,
                    9 => 16,
                    10 => 32,
                    12 => 64,
                    13 => 128,
                    _ => 0,
                };
                let plan = swr_v1_tls_setup(stage, facts & field, result);
                if plan.action != SetupAction::Observe as u32 {
                    actions.push(plan.action);
                }
                if plan.action <= 1 {
                    return actions;
                }
                stage = plan.next;
                if plan.action != SetupAction::Observe as u32 {
                    result = if plan.action == fail_action {
                        failure
                    } else {
                        1
                    };
                }
            }
            panic!("nonterminating setup");
        }
        assert_eq!(
            trace(255, 99, 0),
            vec![2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13, 14, 1]
        );
        assert_eq!(trace(0, 99, 0), vec![8, 9, 14, 1]);
        assert_eq!(trace(255, 3, 0), vec![2, 3, 0]);
        assert_eq!(trace(255, 4, 0), vec![2, 3, 4, 0]);
        assert_eq!(trace(255, 5, 0), vec![2, 3, 4, 5, 0]);
        assert_eq!(trace(255, 6, 0), vec![2, 3, 4, 5, 6, 0]);
        assert_eq!(trace(255, 8, 0), vec![2, 3, 4, 5, 6, 7, 8, 0]);
        assert_eq!(trace(0, 8, 0), vec![8, 9, 14, 1]);
        assert_eq!(trace(255, 10, -1), vec![2, 3, 4, 5, 6, 7, 8, 10, 0]);
        assert_eq!(trace(255, 10, 0), trace(255, 99, 0));
        assert_eq!(trace(255, 10, 1), trace(255, 99, 0));
        assert_eq!(
            trace(255, 13, 0),
            vec![2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13, 0]
        );
        assert_eq!(
            trace(255, 14, 0),
            vec![2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13, 14, 0]
        );
        for facts in 0..256 {
            assert_eq!(*trace(facts, 99, 0).last().unwrap(), 1);
        }
    }
}
