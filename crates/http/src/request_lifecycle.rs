//! Native core Request multipart resource policy. Plans are immutable; every
//! allocator/parser/String/stdio effect completes outside a Rust frame.
const MAKE_PARSER: u32 = 1;
const SET_DATA: u32 = 2;
const NEW_BODY: u32 = 3;
const APPEND_BODY: u32 = 4;
const SAVE_BUFFER: u32 = 5;
const TRIM_BUFFER: u32 = 6;
const USE_BODY: u32 = 7;
const TMP_NAME: u32 = 8;
const NEW_UPLOAD: u32 = 9;
const UPLOAD_MAX: u32 = 10;
const TRUE: u32 = 11;
const WARN: u32 = 12;
const FALSE: u32 = 13;
const DELETE_BODY: u32 = 14;
const RESTORE_BUFFER: u32 = 15;
const CLEAR_SAVED: u32 = 16;
const OBSERVE_FILE: u32 = 17;
const CLOSE: u32 = 18;
const UNLINK: u32 = 19;
const FREE_PARSER: u32 = 20;
const NULL_PARSER: u32 = 21;
const DELETE_UPLOAD: u32 = 22;
const NULL_UPLOAD: u32 = 23;
const DELETE_FORM: u32 = 24;
const NULL_FORM: u32 = 25;
const DESTROY: u32 = 26;
const DONE: u32 = 0;

pub(crate) fn plan(kind: u32, observed: u32) -> Option<&'static [u32]> {
    if observed > 1 {
        return None;
    }
    Some(match (kind, observed != 0) {
        (0, true) => &[MAKE_PARSER],
        (0, false) => &[FALSE],
        (1, true) => &[
            SET_DATA,
            NEW_BODY,
            APPEND_BODY,
            SAVE_BUFFER,
            TRIM_BUFFER,
            USE_BODY,
            TMP_NAME,
            NEW_UPLOAD,
            UPLOAD_MAX,
            TRUE,
        ],
        (1, false) => &[WARN, FALSE],
        (2, _) => &[DELETE_BODY, RESTORE_BUFFER, CLEAR_SAVED, OBSERVE_FILE],
        (3, true) => &[
            CLOSE,
            UNLINK,
            FREE_PARSER,
            NULL_PARSER,
            DELETE_UPLOAD,
            NULL_UPLOAD,
            DELETE_FORM,
            NULL_FORM,
            DONE,
        ],
        (3, false) => &[
            FREE_PARSER,
            NULL_PARSER,
            DELETE_UPLOAD,
            NULL_UPLOAD,
            DELETE_FORM,
            NULL_FORM,
            DONE,
        ],
        (4, true) => &[DESTROY, DONE],
        (4, false) => &[DONE],
        _ => return None,
    })
}
/// Kind0=boundary result,1=parser allocation result,2=destroy prefix,
/// 3=FP presence freshly observed after prefix,4=destructor FormData presence.
/// Returns immutable module-lifetime actions; unknown metadata leaves count
/// unchanged and returns null. No dynamic owner or operand is captured.
///
/// # Safety
/// Count is aligned/writable/disjoint from returned static storage. Native must
/// execute each effect in order, read dynamic operands at that effect, and supply
/// late observations only after prior effects complete. Plans do not make partial
/// initialization, reentry, failure or unsupported request lifetimes safe.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_http_request_lifecycle(
    kind: u32,
    observed: u32,
    count: *mut usize,
) -> *const u32 {
    if count.is_null() {
        return std::ptr::null();
    }
    let Some(actions) = plan(kind, observed) else {
        return std::ptr::null();
    };
    // SAFETY: `count` is non-null (checked above), aligned and writable per the caller contract.
    unsafe { count.write(actions.len()) };
    actions.as_ptr()
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn complete_init_and_destroy_plans_preserve_effect_and_observation_order() {
        assert_eq!(plan(0, 1), Some([MAKE_PARSER].as_slice()));
        assert_eq!(
            plan(1, 1),
            Some(
                [
                    SET_DATA,
                    NEW_BODY,
                    APPEND_BODY,
                    SAVE_BUFFER,
                    TRIM_BUFFER,
                    USE_BODY,
                    TMP_NAME,
                    NEW_UPLOAD,
                    UPLOAD_MAX,
                    TRUE
                ]
                .as_slice()
            )
        );
        assert_eq!(
            plan(2, 0),
            Some([DELETE_BODY, RESTORE_BUFFER, CLEAR_SAVED, OBSERVE_FILE].as_slice())
        );
        assert_eq!(
            plan(3, 1),
            Some(
                [
                    CLOSE,
                    UNLINK,
                    FREE_PARSER,
                    NULL_PARSER,
                    DELETE_UPLOAD,
                    NULL_UPLOAD,
                    DELETE_FORM,
                    NULL_FORM,
                    DONE
                ]
                .as_slice()
            )
        );
        assert_eq!(
            plan(3, 0),
            Some(
                [
                    FREE_PARSER,
                    NULL_PARSER,
                    DELETE_UPLOAD,
                    NULL_UPLOAD,
                    DELETE_FORM,
                    NULL_FORM,
                    DONE
                ]
                .as_slice()
            )
        );
        assert_eq!(plan(4, 1), Some([DESTROY, DONE].as_slice()));
        assert_eq!(plan(4, 0), Some([DONE].as_slice()));
    }
    #[test]
    fn metadata_only_failure_plans_are_not_native_failure_or_lifetime_proof() {
        assert_eq!(plan(0, 0), Some([FALSE].as_slice()));
        assert_eq!(plan(1, 0), Some([WARN, FALSE].as_slice()));
        let mut count = 71;
        assert!(unsafe { swr_v1_http_request_lifecycle(5, 0, &raw mut count) }.is_null());
        assert_eq!(count, 71);
        assert!(unsafe { swr_v1_http_request_lifecycle(1, 2, &raw mut count) }.is_null());
        assert_eq!(count, 71);
        assert!(unsafe { swr_v1_http_request_lifecycle(0, 1, std::ptr::null_mut()) }.is_null());
    }
}
