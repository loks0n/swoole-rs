// SPDX-License-Identifier: Apache-2.0
//! Random-output sequencing. Native code retains entropy, RNG and object custody.

#[repr(C)]
#[derive(Default)]
pub struct RandomState {
    pub phase: u32,
    pub value: i32,
    pub index: usize,
}

const SYSTEM: u32 = 0;
const BUFFER: u32 = 1;
const APPEND: u32 = 2;
const OPEN: u32 = 1;
const READ: u32 = 2;
const FALLBACK: u32 = 3;
const WARN: u32 = 4;
const RETURN: u32 = 5;
const DRAW: u32 = 6;
const STORE_DRAW: u32 = 7;
const STORE_NUL: u32 = 10;
const STORE_DONE: u32 = 11;
const FIRST_DRAW_READY: u32 = 4;
const NUL: u32 = 8;
const DONE: u32 = 9;
const INVALID: u32 = u32::MAX;
const ALPHABET: &[u8; 62] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";

/// Advance one native effect at a time, retaining no borrow after return.
/// # Safety
/// `state` is an exclusive zeroed cursor, mode/length/range remain fixed, and
/// each returned effect completes before reentry. Stop at RETURN/FALLBACK/NUL/
/// DONE/STORE_NUL/STORE_DONE/INVALID. STORE_DRAW completes store before draw.
/// SYSTEM flags copy cached-fd-ready (1) and full-native-read (2); string
/// modes may set FIRST_DRAW_READY (4) when the native caller already drew.
/// SYSTEM requires the original defined range domain (max>min, no signed
/// overflow in max-min+1); string draws are native integers in 0..=61.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_corebase_random_next(
    state: *mut RandomState,
    mode: u32,
    flags: u32,
    length: usize,
    random: u32,
    min: i32,
    max: i32,
) -> u32 {
    let Some(state) = (unsafe { state.as_mut() }) else {
        return INVALID;
    };
    if mode == SYSTEM {
        let action = match state.phase {
            0 | 1 if flags & 1 != 0 => {
                state.phase = 2;
                READ
            }
            0 => {
                state.phase = 1;
                OPEN
            }
            1 => {
                state.phase = 4;
                FALLBACK
            }
            2 if flags & 2 != 0 => {
                // Preserve native unsigned addition and range-width rules.
                let width = max.wrapping_sub(min).wrapping_add(1) as u32;
                if width == 0 {
                    return INVALID;
                }
                state.value = (min as u32).wrapping_add(random % width) as i32;
                state.phase = 4;
                RETURN
            }
            2 => {
                state.phase = 3;
                WARN
            }
            3 => {
                state.value = -1;
                state.phase = 4;
                RETURN
            }
            _ => INVALID,
        };
        return action;
    }
    if !matches!(mode, BUFFER | APPEND) || state.index > length {
        return INVALID;
    }
    if state.phase == 0 {
        if length == 0 {
            state.phase = 3;
            return if mode == BUFFER { NUL } else { DONE };
        }
        state.phase = 1;
        if flags & FIRST_DRAW_READY == 0 {
            return DRAW;
        }
    }
    match state.phase {
        1 => {}
        2 if state.index < length.saturating_sub(1) => state.index += 1,
        _ => return INVALID,
    }
    let Some(&byte) = ALPHABET.get(random as usize) else {
        return INVALID;
    };
    state.value = i32::from(byte);
    if state.index == length - 1 {
        state.phase = 3;
        if mode == BUFFER {
            STORE_NUL
        } else {
            STORE_DONE
        }
    } else {
        state.phase = 2;
        STORE_DRAW
    }
}

#[cfg(test)]
mod tests {
    use super::{RandomState, swr_v1_corebase_random_next};

    fn step(
        s: &mut RandomState,
        mode: u32,
        flags: u32,
        len: usize,
        draw: u32,
        min: i32,
        max: i32,
    ) -> u32 {
        unsafe { swr_v1_corebase_random_next(s, mode, flags, len, draw, min, max) }
    }

    #[test]
    fn system_open_fallback_retry_and_read_warning_prefixes() {
        let mut s = RandomState::default();
        assert_eq!(step(&mut s, 0, 0, 0, 0, 4, 9), 1); // open
        assert_eq!(step(&mut s, 0, 0, 0, 0, 4, 9), 3); // fallback, stop
        // A later invocation gets a fresh cursor and retries the native cached -1.
        let mut s = RandomState::default();
        assert_eq!(step(&mut s, 0, 0, 0, 0, 4, 9), 1);
        assert_eq!(step(&mut s, 0, 1, 0, 0, 4, 9), 2); // read
        assert_eq!(step(&mut s, 0, 1, 0, 0, 4, 9), 4); // warning, no fallback/reopen
        assert_eq!(step(&mut s, 0, 1, 0, 0, 4, 9), 5);
        assert_eq!(s.value, -1);
    }

    #[test]
    fn complete_native_unsigned_read_maps_defined_ranges() {
        for (min, max) in [
            (0, 61),
            (-100, 100),
            (i32::MIN, i32::MIN + 10),
            (i32::MAX - 20, i32::MAX),
        ] {
            for draw in [0, 1, 61, 62, i32::MAX as u32, u32::MAX] {
                let mut s = RandomState::default();
                assert_eq!(step(&mut s, 0, 1, 0, 0, min, max), 2); // cached descriptor
                assert_eq!(step(&mut s, 0, 3, 0, draw, min, max), 5);
                let expected =
                    i64::from(min) + i64::from(draw) % (i64::from(max) - i64::from(min) + 1);
                assert_eq!(i64::from(s.value), expected);
            }
        }
    }

    #[test]
    fn buffer_draw_write_order_full_alphabet_nul_and_canaries() {
        let alphabet = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
        for len in [0, 1, 62, 1023] {
            let mut s = RandomState::default();
            let mut out = vec![0xa5; len + 3];
            let initial = step(&mut s, 1, 0, len, 0, 0, 0);
            let mut transitions = 1;
            if len == 0 {
                assert_eq!(initial, 8);
                out[1] = 0;
            } else {
                assert_eq!(initial, 6);
                for index in 0..len {
                    let action = step(&mut s, 1, 0, len, (index % 62) as u32, 0, 0);
                    transitions += 1;
                    assert_eq!(s.index, index);
                    out[1 + s.index] = s.value as u8;
                    if index + 1 == len {
                        assert_eq!(action, 10); // final store then NUL, no extra draw
                        out[2 + s.index] = 0;
                    } else {
                        assert_eq!(action, 7); // store before the next native draw
                    }
                }
            }
            assert_eq!(transitions, len + 1);
            assert_eq!(out[0], 0xa5);
            assert_eq!(out[len + 2], 0xa5);
            assert_eq!(out[len + 1], 0);
            for index in 0..len {
                assert_eq!(out[index + 1], alphabet[index % 62]);
            }
        }
    }

    #[test]
    fn pre_drawn_first_byte_skips_only_the_initial_dispatch() {
        let mut buffer = RandomState::default();
        assert_eq!(step(&mut buffer, 1, 4, 3, 0, 0, 0), 7);
        assert_eq!((buffer.index, buffer.value), (0, b'A' as i32));
        assert_eq!(step(&mut buffer, 1, 0, 3, 27, 0, 0), 7);
        assert_eq!((buffer.index, buffer.value), (1, b'b' as i32));
        assert_eq!(step(&mut buffer, 1, 0, 3, 61, 0, 0), 10);
        assert_eq!((buffer.index, buffer.value), (2, b'9' as i32));

        let mut append = RandomState::default();
        assert_eq!(step(&mut append, 2, 4, 3, 25, 0, 0), 7);
        assert_eq!((append.index, append.value), (0, b'Z' as i32));
        // A native append failure here must stop before another policy call
        // or native draw, as in the original interleaved loop.
        assert_eq!(append.phase, 2);
        assert_eq!(append.index, 0);
    }

    #[test]
    fn append_prefix_and_failure_stops_before_another_draw() {
        let mut empty = RandomState::default();
        assert_eq!(step(&mut empty, 2, 0, 0, 0, 0, 0), 9); // no draw/append
        let mut s = RandomState::default();
        let mut out = String::from("prefix:");
        let draws = [0, 27, 25, 61];
        assert_eq!(step(&mut s, 2, 0, 20, 0, 0, 0), 6);
        for (index, draw) in draws.into_iter().enumerate() {
            assert_eq!(step(&mut s, 2, 0, 20, draw, 0, 0), 7);
            assert_eq!(s.index, index);
            if index == 3 {
                break;
            } // simulated native append exception: no reentry
            out.push(char::from(s.value as u8));
        }
        assert_eq!(out, "prefix:AbZ");
        assert_eq!(s.phase, 2);
        assert_eq!(s.index, 3);
    }

    #[test]
    fn append_success_preserves_prefix_with_n_plus_one_transitions() {
        let alphabet = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
        for len in [0, 1, 62, 1023] {
            let mut s = RandomState::default();
            let mut text = String::from("prefix:");
            let initial = step(&mut s, 2, 0, len, 0, 0, 0);
            let mut transitions = 1;
            if len == 0 {
                assert_eq!(initial, 9);
            } else {
                assert_eq!(initial, 6);
                for index in 0..len {
                    let action = step(&mut s, 2, 0, len, (index % 62) as u32, 0, 0);
                    transitions += 1;
                    assert_eq!(s.index, index);
                    text.push(char::from(s.value as u8));
                    assert_eq!(action, if index + 1 == len { 11 } else { 7 });
                }
            }
            assert_eq!(transitions, len + 1);
            assert_eq!(&text.as_bytes()[..7], b"prefix:");
            assert_eq!(text.len(), len + 7);
            for index in 0..len {
                assert_eq!(text.as_bytes()[7 + index], alphabet[index % 62]);
            }
        }
    }
}
