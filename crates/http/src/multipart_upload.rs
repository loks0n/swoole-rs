//! Header upload admission/acquisition plans; parser/stdio effects stay Native.
const DONE: u32 = 0;
const FILENAME: u32 = 1;
const PREPARE: u32 = 2;
const TEMPFILE: u32 = 3;
const OPEN: u32 = 4;
const EXCEPTED: u32 = 5;
const WARN: u32 = 6;
const PUBLISH: u32 = 7;
fn plan(stage: u32, observed: bool) -> Option<&'static [u32]> {
    Some(match (stage, observed) {
        (0, true) => &[FILENAME],
        (0 | 1, false) => &[DONE],
        (1, true) => &[PREPARE, TEMPFILE],
        (2, true) => &[OPEN],
        (2, false) => &[EXCEPTED, DONE],
        (3, true) => &[PUBLISH, DONE],
        (3, false) => &[WARN, DONE],
        _ => return None,
    })
}
/// Stages0=classify fresh header name,1=filename result,2=tempfile result,
/// 3=fdopen result. Actions0=done,1=allocate scratch/parse filename,2=copy current
/// template/NUL/reset upload size,3=tempfile,4=fdopen,5=excepted,6=warn,7=store FILE.
/// Each Native effect completes before its result is supplied. No pointer or
/// native resource is captured; returned actions are module-lifetime immutable.
/// Existing v1 disposition/filename contracts are unchanged.
/// # Safety
/// Count is writable and independent. At stage0 header is an initialized span;
/// later stages ignore it. Native observes live operands only at each effect and
/// does not retain a Rust frame/borrow across allocation, parser, stdio or warning.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_multipart_upload(
    stage: u32,
    observed: u32,
    header: *const u8,
    length: usize,
    count: *mut usize,
) -> *const u32 {
    if count.is_null() || observed > 1 {
        return std::ptr::null();
    }
    let observed = if stage == 0 {
        match unsafe { crate::swr_v1_http_multipart_disposition(header, length) } {
            0 => false,
            1 => true,
            _ => return std::ptr::null(),
        }
    } else {
        observed != 0
    };
    let Some(actions) = plan(stage, observed) else {
        return std::ptr::null();
    };
    unsafe { count.write(actions.len()) };
    actions.as_ptr()
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn ordinary_upload_sequence_admits_effects_before_file_publication() {
        assert_eq!(plan(0, true), Some([FILENAME].as_slice()));
        assert_eq!(plan(1, true), Some([PREPARE, TEMPFILE].as_slice()));
        assert_eq!(plan(2, true), Some([OPEN].as_slice()));
        assert_eq!(plan(3, true), Some([PUBLISH, DONE].as_slice()));
        assert_eq!(plan(0, false), Some([DONE].as_slice()));
        assert_eq!(plan(1, false), Some([DONE].as_slice()));
    }
}
