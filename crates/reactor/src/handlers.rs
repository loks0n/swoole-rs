//! Complete routing over Native nonnull facts. Actual function-pointer storage,
//! typed snapshots and invocation remain Native; no pointer enters Rust.
fn kind(event: i32, exact: bool) -> i32 {
    if !exact && event < 256 {
        return 1;
    }
    [(1 << 9, 1), (1 << 10, 2), (1 << 11, 3)]
        .into_iter()
        .find(|&(mask, _)| {
            if exact {
                event == mask
            } else {
                event & mask != 0
            }
        })
        .map_or(0, |(_, slot)| slot)
}
/// Operations0set,1isset,2get,3get_error. Native slots/readiness bits1read,
///2write,3error,4default-write,5default-error. Return0absent/-1invalid or slot;
///6 requests Native nonnull facts (present high bit means not observed yet).
/// Original routing reads ordinary Native pointer fields with no intervening
/// effect. Native supplies their nonnull facts and retains the typed values for
/// the chosen result; no snapshot or borrow is stored in Rust. Calls occur only
/// after return. Public arrays remain the only authoritative pointer storage.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_reactor_handler_select(operation: u32, event: i32, present: u32) -> i32 {
    if operation > 3 {
        return -1;
    }
    let unknown = present & (1 << 31) != 0;
    let has = |slot: i32| present & (1 << (slot - 1)) != 0;
    if operation == 3 {
        return if unknown {
            6
        } else {
            [3, 5, 1, 2, 4]
                .into_iter()
                .find(|&slot| has(slot))
                .unwrap_or(0)
        };
    }
    let slot = kind(event, operation == 2);
    match operation {
        0 => {
            if slot == 0 {
                -1
            } else {
                slot
            }
        }
        1 if slot == 0 => 0,
        2 if slot == 0 => -1,
        2 if slot == 1 => 1,
        _ if unknown => 6,
        1 => {
            if has(slot) {
                slot
            } else {
                0
            }
        }
        2 if has(slot) => slot,
        2 if slot == 2 && has(4) => 4,
        2 if slot == 3 && has(5) => 5,
        _ => 0,
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn handlers_positive_priority_exact_and_fallback_order() {
        for legacy in [0, 7, 255] {
            assert_eq!(swr_v1_reactor_handler_select(0, legacy, 0), 1);
        }
        for present in 0u32..32 {
            for mask in 0..8 {
                let event = mask << 9;
                let slot = if event < 256 || mask & 1 != 0 {
                    1
                } else if mask & 2 != 0 {
                    2
                } else if mask & 4 != 0 {
                    3
                } else {
                    0
                };
                if slot != 0 {
                    assert_eq!(swr_v1_reactor_handler_select(0, event, present), slot);
                }
                assert_eq!(
                    swr_v1_reactor_handler_select(1, event, present),
                    if slot != 0 && present & (1 << (slot - 1)) != 0 {
                        slot
                    } else {
                        0
                    }
                );
            }
            let order = [3, 5, 1, 2, 4];
            assert_eq!(
                swr_v1_reactor_handler_select(3, 0, present),
                order
                    .into_iter()
                    .find(|slot| present & (1 << (slot - 1)) != 0)
                    .unwrap_or(0)
            );
            for slot in 1..4 {
                let expected = if slot == 1 || present & (1 << (slot - 1)) != 0 {
                    slot
                } else if slot == 2 && present & 8 != 0 {
                    4
                } else if slot == 3 && present & 16 != 0 {
                    5
                } else {
                    0
                };
                assert_eq!(
                    swr_v1_reactor_handler_select(2, 1 << (slot + 8), present),
                    expected
                );
            }
        }
    }
}
