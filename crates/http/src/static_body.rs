//! Static response body scheduling; allocation, storage and sends remain native.
use crate::INVALID;

#[repr(C)]
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct HttpStaticBody {
    pub count: usize,
    pub cursor: usize,
    pub phase: u32,
    pub head: u32,
}

#[repr(i32)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Action {
    Done = 0,
    Allocate = 1,
    PartHeader = 2,
    File = 3,
    EndPart = 4,
    Free = 5,
    KeepAlive = 6,
    Close = 7,
}

impl HttpStaticBody {
    fn valid(&self) -> bool {
        self.phase <= 7
            && self.cursor <= self.count
            && (!(1..=3).contains(&self.phase) || self.count != 0)
            && (!(2..=3).contains(&self.phase) || self.cursor < self.count)
    }

    fn next(&mut self, length: usize, keep_alive: bool) -> Action {
        use Action::*;
        match self.phase {
            0 if self.head != 0 || self.count == 0 => {
                self.phase = 6;
                KeepAlive
            }
            0 => {
                self.phase = 1;
                Allocate
            }
            1 if self.count > 1 => {
                self.phase = 2;
                PartHeader
            }
            1 if length == 0 => {
                self.phase = 5;
                Free
            }
            1 | 2 => {
                self.phase = 3;
                File
            }
            3 if self.count > 1 => {
                self.cursor += 1;
                if self.cursor < self.count {
                    self.phase = 2;
                    PartHeader
                } else {
                    self.phase = 4;
                    EndPart
                }
            }
            3 | 4 => {
                self.phase = 5;
                Free
            }
            5 => {
                self.phase = 6;
                KeepAlive
            }
            6 => {
                self.phase = 7;
                if keep_alive { Done } else { Close }
            }
            _ => Done,
        }
    }
}

/// Return the next native operation after the preceding action has completed.
/// `length` is inspected only for the single-task decision after allocation;
/// `keep_alive` is inspected only after returning action6 (late native snapshot).
/// No owner, borrowed native object, callback or allocation survives this call.
///
/// # Safety
/// State is an initialized, aligned, exclusively writable POD. Native executes
/// actions only after return and resumes the same state with its original count.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_http_static_body(
    state: *mut HttpStaticBody,
    length: usize,
    keep_alive: u32,
) -> i32 {
    // SAFETY: `state` is null or live, aligned and exclusively lent for this call.
    let Some(state) = (unsafe { state.as_mut() }) else {
        return INVALID;
    };
    if !state.valid() {
        return INVALID;
    }
    state.next(length, keep_alive != 0) as i32
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn complete_native_action_order() {
        for count in [0, 1, 2, 3, 16, 2048] {
            for head in [false, true] {
                for keep in [false, true] {
                    for length in [0, 1, usize::MAX] {
                        let mut state = HttpStaticBody {
                            count,
                            head: u32::from(head),
                            ..Default::default()
                        };
                        let mut actual = Vec::new();
                        loop {
                            let action = unsafe {
                                swr_v1_http_static_body(&raw mut state, length, u32::from(keep))
                            };
                            assert!(action >= 0);
                            if action == Action::Done as i32 {
                                break;
                            }
                            actual.push((action, state.cursor));
                        }
                        let mut expected = Vec::new();
                        if !head && count != 0 {
                            expected.push((Action::Allocate as i32, 0));
                            if count > 1 {
                                for index in 0..count {
                                    expected.push((Action::PartHeader as i32, index));
                                    expected.push((Action::File as i32, index));
                                }
                                expected.push((Action::EndPart as i32, count));
                            } else if length != 0 {
                                expected.push((Action::File as i32, 0));
                            }
                            expected.push((Action::Free as i32, if count > 1 { count } else { 0 }));
                        }
                        let final_cursor = if !head && count > 1 { count } else { 0 };
                        expected.push((Action::KeepAlive as i32, final_cursor));
                        if !keep {
                            expected.push((Action::Close as i32, final_cursor));
                        }
                        assert_eq!(actual, expected);
                    }
                }
            }
        }
    }

    #[test]
    fn bad_state_does_not_advance() {
        for state in [
            HttpStaticBody {
                phase: 8,
                ..Default::default()
            },
            HttpStaticBody {
                count: 1,
                cursor: 2,
                ..Default::default()
            },
            HttpStaticBody {
                phase: 1,
                ..Default::default()
            },
            HttpStaticBody {
                phase: 2,
                count: 1,
                cursor: 1,
                ..Default::default()
            },
        ] {
            let mut actual = state;
            assert_eq!(
                unsafe { swr_v1_http_static_body(&raw mut actual, 1, 1) },
                INVALID
            );
            assert_eq!(actual, state);
        }
    }
}
