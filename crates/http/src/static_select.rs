//! Whole static-response selection. Native constructs strings/handlers and
//! executes IO only after each call returns; no native object is borrowed here.
use crate::INVALID;

#[repr(C)]
#[derive(Default, Clone, Copy, Debug, PartialEq, Eq)]
pub struct HttpStaticSelection {
    pub phase: u32,
    pub head: u32,
    pub range_kind: u32,
}
#[repr(i32)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Action {
    Skip = 0,
    Status = 1,
    NotFound = 2,
    Dates = 3,
    CheckModified = 4,
    NotModified = 5,
    Index = 6,
    InspectIndex = 7,
    Autoindex = 8,
    File = 9,
    FileHeader = 10,
    Ready = 11,
}
impl HttpStaticSelection {
    fn next(&mut self, value: usize, status: i32) -> Result<Action, i32> {
        use Action::{
            Autoindex, CheckModified, Dates, File, FileHeader, Index, InspectIndex, NotFound,
            NotModified, Ready, Skip, Status,
        };
        let (phase, action) = match self.phase {
            0 if value == 0 => (8, Skip),
            0 => (1, Status),
            1 if status == 404 => (8, NotFound),
            1 => (2, Dates),
            2 if value != 0 => (3, CheckModified),
            2 => (4, Index),
            3 if value != 0 => (8, NotModified),
            3 => (4, Index),
            4 if value == 0 => (8, Skip),
            4 => (5, InspectIndex),
            5 if value > 7 => return Err(INVALID),
            5 if value == 6 => (8, Autoindex),
            5 => (6, File),
            6 => {
                self.head = u32::from(value == 3); // Pinned SW_HTTP_HEAD.
                (7, FileHeader)
            }
            7 => {
                self.range_kind = if value == 1 {
                    if status == 206 { 1 } else { 2 }
                } else {
                    0
                };
                (8, Ready)
            }
            8 => (8, Ready),
            _ => return Err(INVALID),
        };
        self.phase = phase;
        Ok(action)
    }
}
/// Phase values:0 try-serve result,1 current status,2 conditional header length,
/// 3 conditional result,4 index-serve result,5 initialized index/autoindex/dir
/// facts(bits1/2/4),6 raw method,7 copied task count/current post-MIME status.
/// Head and range decisions are observed at separate native effect boundaries.
///
/// # Safety
/// State is initialized, aligned, exclusive scratch. Native effects run only
/// after return; each input is supplied at its documented phase. No owner or
/// reference survives a call. Original C++ handler/response storage stays native.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_http_static_select(
    state: *mut HttpStaticSelection,
    value: usize,
    status: i32,
) -> i32 {
    // SAFETY: `state` is null or live, aligned and exclusively lent for this call.
    let Some(state) = (unsafe { state.as_mut() }) else {
        return INVALID;
    };
    match state.next(value, status) {
        Ok(action) => action as i32,
        Err(error) => error,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn terminal_branches_stop_before_later_native_effects() {
        let mut skipped = HttpStaticSelection::default();
        assert_eq!(skipped.next(0, 0), Ok(Action::Skip));
        let mut missing = HttpStaticSelection::default();
        assert_eq!(missing.next(1, 0), Ok(Action::Status));
        assert_eq!(missing.next(0, 404), Ok(Action::NotFound));
        let mut cached = HttpStaticSelection::default();
        assert_eq!(cached.next(1, 0), Ok(Action::Status));
        assert_eq!(cached.next(0, 200), Ok(Action::Dates));
        assert_eq!(cached.next(1, 0), Ok(Action::CheckModified));
        assert_eq!(cached.next(1, 0), Ok(Action::NotModified));
        assert_eq!((missing.head, cached.head), (0, 0));
    }
    #[test]
    fn index_flags_and_file_header_decisions_are_separate_fresh_observations() {
        for conditional in [false, true] {
            for facts in 0..8 {
                for method in 1..=26 {
                    for tasks in 0..=3 {
                        for status in [200, 206, 416] {
                            let mut state = HttpStaticSelection::default();
                            assert_eq!(state.next(1, 0), Ok(Action::Status));
                            assert_eq!(state.next(0, 200), Ok(Action::Dates));
                            if conditional {
                                assert_eq!(state.next(3, 0), Ok(Action::CheckModified));
                                assert_eq!(state.next(0, 0), Ok(Action::Index));
                            } else {
                                assert_eq!(state.next(0, 0), Ok(Action::Index));
                            }
                            assert_eq!(state.next(1, 0), Ok(Action::InspectIndex));
                            if facts == 6 {
                                assert_eq!(state.next(facts, 0), Ok(Action::Autoindex));
                                continue;
                            }
                            assert_eq!(state.next(facts, 0), Ok(Action::File));
                            assert_eq!(state.next(method, 0), Ok(Action::FileHeader));
                            assert_eq!(state.head, u32::from(method == 3));
                            // A native MIME effect may occur here. Status is a
                            // fresh copied fact on the next call, never cached.
                            assert_eq!(state.next(tasks, status), Ok(Action::Ready));
                            assert_eq!(
                                state.range_kind,
                                if tasks != 1 {
                                    0
                                } else if status == 206 {
                                    1
                                } else {
                                    2
                                }
                            );
                        }
                    }
                }
            }
        }
    }
    #[test]
    fn invalid_scratch_rejects_without_publication() {
        for phase in [5, 9, u32::MAX] {
            let mut state = HttpStaticSelection {
                phase,
                head: 71,
                range_kind: 81,
            };
            let old = state;
            assert_eq!(state.next(8, 0), Err(INVALID));
            assert_eq!(state, old);
        }
        assert_eq!(
            unsafe { swr_v1_http_static_select(std::ptr::null_mut(), 0, 0) },
            INVALID
        );
    }
}
