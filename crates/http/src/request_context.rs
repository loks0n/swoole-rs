//! Private selected core Request custody. Native owns actual parser/String/FILE
//! effects; Rust owns metadata, form/name/template bytes and invocation cursors.
use crate::{
    HttpChunkStep, HttpFrame, HttpHeaderInfo, HttpMultipartData, HttpSpan, INVALID, OVERFLOW, bytes,
};
use std::alloc::{Layout, alloc};
const ALLOCATION: i32 = -3;
const EXCEPTED: u32 = 1;
const TOO_LARGE: u32 = 2;
const UNAVAILABLE: u32 = 4;
const HEADER_PARSED: u32 = 8;
const DISPATCHED: u32 = 16;
const MULTIPART_HEADER: u32 = 32;
const KNOWN: u32 = 64;
const KEEPALIVE: u32 = 128;
const CHUNKED: u32 = 256;
const NOBODY: u32 = 512;
#[repr(C)]
#[derive(Default, Clone, Copy, Debug, PartialEq, Eq)]
pub struct HttpRequestObservation {
    pub content_length: u64,
    pub upload_size: usize,
    pub upload_maximum: usize,
    pub method: u32,
    pub version: u32,
    pub flags: u32,
    pub url_offset: u32,
    pub url_length: u32,
    pub maximum: u32,
    pub line_length: u32,
    pub header_length: u32,
    pub has_form: u32,
    pub boundary_length: u32,
}
#[derive(Default)]
struct Facts {
    content_length: u64,
    method: u32,
    version: u32,
    flags: u32,
    url_offset: u32,
    url_length: u32,
    maximum: u32,
    line_length: u32,
    header_length: u32,
}
#[derive(Default)]
struct Form {
    boundary_length: u32,
    name: Vec<u8>,
    template: Vec<u8>,
    uploaded: usize,
    maximum: usize,
    active: bool,
}
#[derive(Default)]
struct Data {
    phase: u32,
    length: usize,
}
#[derive(Default)]
pub struct HttpRequestContext {
    facts: Facts,
    form: Option<Box<Form>>,
    header_cursor: usize,
    chunk_cursor: usize,
    chunk_initial: u32,
    data: Data,
}
impl HttpRequestContext {
    fn observe(&self) -> HttpRequestObservation {
        let facts = &self.facts;
        HttpRequestObservation {
            content_length: facts.content_length,
            method: facts.method,
            version: facts.version,
            flags: facts.flags,
            url_offset: facts.url_offset,
            url_length: facts.url_length,
            maximum: facts.maximum,
            line_length: facts.line_length,
            header_length: facts.header_length,
            has_form: u32::from(self.form.is_some()),
            upload_size: self.form.as_ref().map_or(0, |form| form.uploaded),
            upload_maximum: self.form.as_ref().map_or(0, |form| form.maximum),
            boundary_length: self.form.as_ref().map_or(0, |form| form.boundary_length),
        }
    }
    fn flag(&mut self, flag: u32, value: bool) {
        self.facts.flags = (self.facts.flags & !flag) | if value { flag } else { 0 };
    }
    #[expect(
        clippy::cast_possible_truncation,
        reason = "operands are native fields the ABI widens to u64; each narrows back to its own type"
    )]
    fn control(&mut self, operation: u32, value: u64, auxiliary: u64) -> i32 {
        match operation {
            0 => {
                // Legacy clean resets only the prefix; form/resources survive.
                self.facts = Facts::default();
                self.header_cursor = 0;
                self.chunk_cursor = 0;
                self.chunk_initial = 0;
                self.data = Data::default();
            }
            1 => self.facts.maximum = value as u32,
            2 => self.facts.header_length = self.facts.header_length.wrapping_add(value as u32),
            3 => self.flag(DISPATCHED, true),
            4 => self.form = None,
            5 => self.flag(EXCEPTED, false),
            6 => self.flag(EXCEPTED, true),
            7 => {
                if value & 1 != 0 {
                    self.flag(MULTIPART_HEADER, true);
                }
                if value & 2 != 0 {
                    self.flag(MULTIPART_HEADER, false);
                }
                if value & 4 != 0 {
                    self.facts.content_length =
                        (auxiliary as usize).wrapping_sub(self.facts.header_length as usize) as u64;
                    self.flag(DISPATCHED, true);
                }
            }
            8 => {
                let Some(form) = self.form.as_mut() else {
                    return INVALID;
                };
                form.uploaded = 0;
            }
            9 => {
                let Some(form) = self.form.as_mut() else {
                    return INVALID;
                };
                form.maximum = value as usize;
            }
            10 => {
                let Some(form) = try_boxed(Form {
                    boundary_length: value as u32,
                    ..Form::default()
                }) else {
                    return ALLOCATION;
                };
                self.form = Some(form);
            }
            11 => {
                let Some(form) = self.form.as_mut() else {
                    return INVALID;
                };
                form.active = true;
            }
            12 => {
                let Some(form) = self.form.as_mut() else {
                    return INVALID;
                };
                form.name = Vec::new();
                form.template = Vec::new();
            }
            _ => return INVALID,
        }
        0
    }
    fn set_text(&mut self, kind: u32, input: &[u8]) -> i32 {
        let Some(form) = self.form.as_mut() else {
            return INVALID;
        };
        let (text, suffix) = match kind {
            0 => (&mut form.template, b"/swoole.upfile.XXXXXX".as_slice()),
            1 => (&mut form.name, b"".as_slice()),
            _ => return INVALID,
        };
        let Some(length) = input
            .len()
            .checked_add(suffix.len())
            .filter(|&n| n <= isize::MAX as usize)
        else {
            return OVERFLOW;
        };
        // Reserve before changing initialized bytes: an allocation error leaves
        // the previous value intact. Independent snapshots never borrow this Vec.
        if text
            .try_reserve_exact(length.saturating_sub(text.len()))
            .is_err()
        {
            return ALLOCATION;
        }
        text.clear();
        text.extend_from_slice(input);
        text.extend_from_slice(suffix);
        0
    }
    fn text(&self, kind: u32) -> Result<&[u8], i32> {
        let Some(form) = self.form.as_ref() else {
            return Err(INVALID);
        };
        match kind {
            0 => Ok(&form.template),
            1 => Ok(&form.name),
            _ => Err(INVALID),
        }
    }
    fn header_flags(&self) -> u32 {
        [
            (KNOWN, 1),
            (KEEPALIVE, 2),
            (CHUNKED, 4),
            (NOBODY, 8),
            (HEADER_PARSED, 16),
        ]
        .into_iter()
        .fold(0, |flags, (native, parser)| {
            flags
                | if self.facts.flags & native != 0 {
                    parser
                } else {
                    0
                }
        })
    }
    fn publish_header_flags(&mut self, flags: u32) {
        for (native, parser) in [
            (KNOWN, 1),
            (KEEPALIVE, 2),
            (CHUNKED, 4),
            (NOBODY, 8),
            (HEADER_PARSED, 16),
        ] {
            self.flag(native, flags & parser != 0);
        }
    }
    fn publish_data(&mut self, state: &HttpMultipartData) {
        self.data.phase = state.phase;
        self.data.length = state.length;
        if state.has_file != 0
            && let Some(form) = self.form.as_mut()
        {
            form.uploaded = state.upload_size;
        }
        if state.flags & 1 != 0 {
            self.flag(EXCEPTED, true);
        }
        if state.flags & 2 != 0 {
            self.flag(UNAVAILABLE, true);
        }
        if state.flags & 4 != 0 {
            self.flag(TOO_LARGE, true);
        }
    }
}
// Form metadata is admitted out of line only at the real multipart boundary;
// ordinary requests do not carry unused name/template/vector capacity fields.
pub(crate) fn try_boxed<T>(value: T) -> Option<Box<T>> {
    if size_of::<T>() == 0 {
        return Some(Box::new(value));
    }
    // SAFETY: a non-zero-sized layout; null is handled below.
    let storage = unsafe { alloc(Layout::new::<T>()).cast::<T>() };
    if storage.is_null() {
        return None;
    }
    // SAFETY: a fresh, non-null allocation with `T`'s layout.
    unsafe { storage.write(value) };
    // SAFETY: a global allocation with `Box`'s layout, initialized above.
    Some(unsafe { Box::from_raw(storage) })
}
/// Allocate only Rust metadata. Native maps null to its exception after return;
/// no external parser/String/FILE or callback is created through Rust.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v2_http_request_new() -> *mut HttpRequestContext {
    try_boxed(HttpRequestContext::default()).map_or(std::ptr::null_mut(), Box::into_raw)
}
/// # Safety
/// Null or unique live owner, after all Native resource effects finished.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_request_drop(owner: *mut HttpRequestContext) {
    if !owner.is_null() {
        // SAFETY: a unique, live owner from `request_new`, dropped once.
        drop(unsafe { Box::from_raw(owner) });
    }
}
/// # Safety
/// Live owner and independent aligned writable output. Snapshot is copied and
/// must be refreshed after Native effects; it is never a second persistent store.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_request_observe(
    owner: *const HttpRequestContext,
    output: *mut HttpRequestObservation,
) -> i32 {
    // SAFETY: `owner` is null or live and aligned for this call.
    let owner = unsafe { owner.as_ref() };
    // SAFETY: `output` is null or live, aligned and exclusively lent for this call.
    let output = unsafe { output.as_mut() };
    let (Some(owner), Some(output)) = (owner, output) else {
        return INVALID;
    };
    *output = owner.observe();
    0
}
/// Controls0=clean prefix,1=maximum,2=advance header,3=dispatched,4=discard form,
/// 5=clear excepted,6=excepted,7=emit effects(value)/current body length(aux),
/// 8=reset upload size,9=upload maximum,10=admit form with boundary length,
/// 11=publish fully initialized multipart resources,12=destroy form text before
/// the separate absent-form publication at control4.
/// # Safety
/// Unique live owner. Native applies controls only at their original publication
/// points and completes all effects before calling Rust, never through a borrow.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_request_control(
    owner: *mut HttpRequestContext,
    operation: u32,
    value: u64,
    auxiliary: u64,
) -> i32 {
    // SAFETY: `owner` is null or live, aligned and exclusively lent for this call.
    let Some(owner) = (unsafe { owner.as_mut() }) else {
        return INVALID;
    };
    owner.control(operation, value, auxiliary)
}
/// # Safety
/// Unique owner; initialized independent Native input, writable disjoint next
/// offset. Native observes and publishes its actual buffer offset outside Rust.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_request_frame(
    owner: *mut HttpRequestContext,
    operation: u32,
    input: *const u8,
    length: usize,
    offset: usize,
    next: *mut usize,
) -> i32 {
    // SAFETY: `owner` is null or live, aligned and exclusively lent for this call.
    let owner = unsafe { owner.as_mut() };
    // SAFETY: `next` is null or live, aligned and exclusively lent for this call.
    let next = unsafe { next.as_mut() };
    let (Some(owner), Some(next)) = (owner, next) else {
        return INVALID;
    };
    let f = &owner.facts;
    let mut frame = HttpFrame {
        offset,
        content_length: f.content_length,
        method: f.method,
        version: f.version,
        excepted: u32::from(f.flags & EXCEPTED != 0),
        url_offset: f.url_offset,
        url_length: f.url_length,
        line_length: f.line_length,
        header_length: f.header_length,
        known_length: u32::from(f.flags & KNOWN != 0),
    };
    // SAFETY: the caller lends `length` initialized bytes at `input` (null only when empty).
    let result = match unsafe { bytes(input, length) } {
        Ok(input) => frame.parse(input, operation),
        Err(error) => error,
    };
    *next = frame.offset;
    owner.facts.content_length = frame.content_length;
    owner.facts.method = frame.method;
    owner.facts.version = frame.version;
    owner.facts.url_offset = frame.url_offset;
    owner.facts.url_length = frame.url_length;
    owner.facts.line_length = frame.line_length;
    owner.facts.header_length = frame.header_length;
    owner.flag(EXCEPTED, frame.excepted != 0);
    owner.flag(KNOWN, frame.known_length != 0);
    result
}
#[repr(C)]
#[derive(Default)]
pub struct HttpRequestHeaderResult {
    pub boundary: HttpSpan,
    pub number_errors: u32,
}
/// Operation0 begins a fresh header invocation,1 resumes. A multipart result1
/// requires Native errno handling, then form admission/captured Native boundary
/// backing before resuming. No borrowed buffer pointer is stored in Rust.
/// # Safety
/// Unique owner; initialized independent Native input and disjoint output. Native
/// completes errno/allocation/resource effects after return, before the next call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_request_headers(
    owner: *mut HttpRequestContext,
    operation: u32,
    input: *const u8,
    length: usize,
    output: *mut HttpRequestHeaderResult,
) -> i32 {
    // SAFETY: `owner` is null or live, aligned and exclusively lent for this call.
    let owner = unsafe { owner.as_mut() };
    // SAFETY: `output` is null or live, aligned and exclusively lent for this call.
    let output = unsafe { output.as_mut() };
    let (Some(owner), Some(output)) = (owner, output) else {
        return INVALID;
    };
    if operation == 0 {
        owner.header_cursor = owner.facts.line_length.wrapping_add(2) as usize;
    } else if operation != 1 {
        return INVALID;
    }
    let mut header = HttpHeaderInfo {
        cursor: owner.header_cursor,
        content_length: owner.facts.content_length,
        flags: owner.header_flags(),
        number_errors: 0,
    };
    output.boundary = HttpSpan::default();
    // SAFETY: the caller lends `length` initialized bytes at `input` (null only when empty).
    let result = match unsafe { bytes(input, length) } {
        Ok(input) => crate::headers::header_info(
            input,
            owner.facts.header_length.wrapping_sub(4) as usize,
            &mut header,
            &mut output.boundary,
        ),
        Err(error) => error,
    };
    owner.header_cursor = header.cursor;
    owner.facts.content_length = header.content_length;
    owner.publish_header_flags(header.flags);
    output.number_errors = header.number_errors;
    result
}
/// Rust-owned active/candidate admission over the existing Native effect plans.
/// A candidate has no fully committed parser resource set; partial allocation/
/// failure prefixes remain unqualified, never probed or credited as cleanup proof.
/// # Safety
/// Live owner; count is aligned/writable/disjoint. Native completes the returned
/// module-lifetime plan after Rust returns; no owner borrow crosses any effect.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_request_lifecycle(
    owner: *const HttpRequestContext,
    kind: u32,
    observed: u32,
    count: *mut usize,
) -> *const u32 {
    // SAFETY: `owner` is null or live and aligned for this call.
    let owner = unsafe { owner.as_ref() };
    // SAFETY: `count` is null or live, aligned and exclusively lent for this call.
    let count = unsafe { count.as_mut() };
    let (Some(owner), Some(count)) = (owner, count) else {
        return std::ptr::null();
    };
    if observed > 1 {
        return std::ptr::null();
    }
    let actions = if kind == 4 {
        match owner.form.as_ref() {
            None => crate::request_lifecycle::plan(4, 0),
            Some(form) if form.active => crate::request_lifecycle::plan(4, 1),
            Some(_) => Some([24, 25, 0].as_slice()),
        }
    } else if kind == 2 && owner.form.as_ref().is_some_and(|form| !form.active) {
        Some([24, 25, 0].as_slice())
    } else {
        crate::request_lifecycle::plan(kind, observed)
    };
    let Some(actions) = actions else {
        return std::ptr::null();
    };
    *count = actions.len();
    actions.as_ptr()
}
/// # Safety
/// Live owner; initialized independent input/name and aligned disjoint span output.
/// No pointer/borrow is retained; Native materializes its result after return.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_request_header(
    owner: *const HttpRequestContext,
    input: *const u8,
    length: usize,
    name: *const u8,
    name_length: usize,
    output: *mut HttpSpan,
) -> i32 {
    // SAFETY: `owner` is null or live and aligned for this call.
    let Some(owner) = (unsafe { owner.as_ref() }) else {
        return INVALID;
    };
    let start = owner
        .facts
        .url_offset
        .wrapping_add(owner.facts.url_length)
        .wrapping_add(10) as usize;
    if output.is_null() {
        return INVALID;
    }
    // SAFETY: `output` is non-null (checked above), aligned and writable.
    unsafe {
        output.write(HttpSpan::default());
    }
    // SAFETY: the caller lends `length` initialized bytes at `input` (null only when empty).
    let input = match unsafe { bytes(input, length) } {
        Ok(input) => input,
        Err(error) => return error,
    };
    // SAFETY: the caller lends `name_length` initialized bytes at `name` (null only when empty).
    let name = match unsafe { bytes(name, name_length) } {
        Ok(name) => name,
        Err(error) => return error,
    };
    crate::framing::header_value(
        input,
        start,
        owner.facts.header_length as usize,
        name,
        // SAFETY: `output` is non-null (checked above), aligned and exclusive per the caller contract.
        unsafe { &mut *output },
    )
}
/// Kind0 assembles upload template from a fresh Native directory;1 copies the
/// current header name. Fallible bytes have one Rust owner, no exposed pointer.
/// # Safety
/// Unique owner; initialized independent input. Native effects happen afterward.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_request_text_set(
    owner: *mut HttpRequestContext,
    kind: u32,
    input: *const u8,
    length: usize,
) -> i32 {
    // SAFETY: `owner` is null or live, aligned and exclusively lent for this call.
    let Some(owner) = (unsafe { owner.as_mut() }) else {
        return INVALID;
    };
    // SAFETY: the caller lends `length` initialized bytes at `input` (null only when empty).
    let input = match unsafe { bytes(input, length) } {
        Ok(input) => input,
        Err(error) => return error,
    };
    owner.set_text(kind, input)
}
/// Capacity0 queries size; otherwise copy complete independent bytes, no NUL.
/// # Safety
/// Live owner, independent writable output/capacity and aligned written. Native
/// allocation/resizing occurs only between completed query and copy calls.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_request_text_copy(
    owner: *const HttpRequestContext,
    kind: u32,
    output: *mut u8,
    capacity: usize,
    written: *mut usize,
) -> i32 {
    // SAFETY: `owner` is null or live and aligned for this call.
    let owner = unsafe { owner.as_ref() };
    // SAFETY: `written` is null or live, aligned and exclusively lent for this call.
    let written = unsafe { written.as_mut() };
    let (Some(owner), Some(written)) = (owner, written) else {
        return INVALID;
    };
    let text = match owner.text(kind) {
        Ok(text) => text,
        Err(error) => return error,
    };
    if capacity != 0 {
        if output.is_null() || capacity < text.len() || capacity > isize::MAX as usize {
            return INVALID;
        }
        // SAFETY: non-null, `text.len() <= capacity <= isize::MAX` writable bytes, disjoint
        // from the owner's text.
        unsafe { std::ptr::copy_nonoverlapping(text.as_ptr(), output, text.len()) };
    }
    *written = text.len();
    0
}
/// Independent immutable bytes for one Native String effect, never a form mirror.
pub struct HttpRequestTextSnapshot {
    bytes: Vec<u8>,
}
/// Copy text into independent Native scratch, or an owned Rust fallback lease.
/// Both paths include initialized NUL backing, including for an empty name.
/// # Safety
/// Live owner; scratch is independently writable for capacity bytes (may be null
/// only at zero capacity). Output and lease are writable, aligned and disjoint
/// from owner, scratch and each other. Native effects start after return. The
/// copied span lasts until scratch expires or the returned lease is dropped;
/// neither backing may be moved/mutated while consumed. No live form borrow escapes.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_request_text_snapshot_new(
    owner: *const HttpRequestContext,
    kind: u32,
    scratch: *mut u8,
    capacity: usize,
    output: *mut crate::HttpProxyText,
    lease: *mut *mut HttpRequestTextSnapshot,
) -> i32 {
    let (Some(owner), Some(output), Some(lease)) = (
        // SAFETY: `owner` is null or live and aligned for this call.
        unsafe { owner.as_ref() },
        // SAFETY: `output` is null or live, aligned and exclusively lent for this call.
        unsafe { output.as_mut() },
        // SAFETY: `lease` is null or live, aligned and exclusively lent for this call.
        unsafe { lease.as_mut() },
    ) else {
        return INVALID;
    };
    if capacity > isize::MAX as usize || (capacity != 0 && scratch.is_null()) {
        return INVALID;
    }
    let text = match owner.text(kind) {
        Ok(text) => text,
        Err(error) => return error,
    };
    let Some(length) = text.len().checked_add(1) else {
        return OVERFLOW;
    };
    if capacity >= length {
        // `text.len() + 1 <= capacity` writable scratch bytes, disjoint from the owner's text.
        // SAFETY: as above.
        unsafe { std::ptr::copy_nonoverlapping(text.as_ptr(), scratch, text.len()) };
        // SAFETY: as above.
        unsafe { scratch.wrapping_add(text.len()).write(0) };
        *output = crate::HttpProxyText {
            data: scratch,
            length: text.len(),
        };
        *lease = std::ptr::null_mut();
    } else {
        let mut bytes = Vec::new();
        if bytes.try_reserve_exact(length).is_err() {
            return ALLOCATION;
        }
        bytes.extend_from_slice(text);
        bytes.push(0);
        let Some(snapshot) = try_boxed(HttpRequestTextSnapshot { bytes }) else {
            return ALLOCATION;
        };
        *output = crate::HttpProxyText {
            data: snapshot.bytes.as_ptr(),
            length: text.len(),
        };
        *lease = Box::into_raw(snapshot);
    }
    0
}
/// Release the optional fallback after its Native effect has completed.
/// # Safety
/// Null or one live uniquely owned snapshot from text_snapshot, with all raw
/// span uses ended. Rust performs no Native callback or allocation here.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_request_text_snapshot_drop(
    lease: *mut HttpRequestTextSnapshot,
) {
    if !lease.is_null() {
        // SAFETY: one live, uniquely owned snapshot from `text_snapshot`, dropped once.
        drop(unsafe { Box::from_raw(lease) });
    }
}
/// Classify the form's authoritative header directly and resume upload effects.
/// Returned plan storage is immutable and independent of the owner.
/// # Safety
/// Owner is live/initialized and count is writable and disjoint. Native parser,
/// file, allocation and warning effects execute only after return.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_request_upload_plan(
    owner: *const HttpRequestContext,
    stage: u32,
    observed: u32,
    count: *mut usize,
) -> *const u32 {
    // SAFETY: `owner` is null or live and aligned for this call.
    let Some(owner) = (unsafe { owner.as_ref() }) else {
        return std::ptr::null();
    };
    let Ok(name) = owner.text(1) else {
        return std::ptr::null();
    };
    // SAFETY: `name` is the owner's live text; `count` is the caller's writable output.
    unsafe {
        crate::swr_v2_http_multipart_upload(stage, observed, name.as_ptr(), name.len(), count)
    }
}
/// Prepare the live Native tempfile buffer from sole Rust-owned form metadata.
/// Copy/NUL publication precedes the logical upload-size reset, as before.
/// # Safety
/// Unique initialized owner; output is independently writable for capacity bytes.
/// No borrow, allocation or Native effect occurs or survives within Rust.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_request_upload_template(
    owner: *mut HttpRequestContext,
    output: *mut u8,
    capacity: usize,
) -> i32 {
    // SAFETY: `owner` is null or live, aligned and exclusively lent for this call.
    let Some(form) = (unsafe { owner.as_mut() }).and_then(|owner| owner.form.as_mut()) else {
        return INVALID;
    };
    if output.is_null() || capacity <= form.template.len() || capacity > isize::MAX as usize {
        return INVALID;
    }
    // `template.len() < capacity` writable output bytes, disjoint from the owner.
    // SAFETY: as above.
    unsafe { std::ptr::copy_nonoverlapping(form.template.as_ptr(), output, form.template.len()) };
    // SAFETY: as above.
    unsafe { output.wrapping_add(form.template.len()).write(0) };
    form.uploaded = 0;
    0
}
/// Operation0 begins one data callback using fresh file/body observations;
/// 1 resumes after fwrite/close. Only invocation phase/length survive effects;
/// request/form metadata has no second persistent scalar store.
/// # Safety
/// Unique owner; Native stdio/buffer/warning effects finish outside Rust.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_request_data(
    owner: *mut HttpRequestContext,
    operation: u32,
    has_file: u32,
    length: usize,
    body_length: usize,
    written: i64,
) -> i32 {
    // SAFETY: `owner` is null or live, aligned and exclusively lent for this call.
    let Some(owner) = (unsafe { owner.as_mut() }) else {
        return INVALID;
    };
    let mut data = if operation == 0 {
        let Some(form) = owner.form.as_ref() else {
            return INVALID;
        };
        HttpMultipartData {
            has_file,
            length,
            buffer_length: body_length,
            maximum: owner.facts.maximum as usize,
            upload_size: form.uploaded,
            upload_maximum: form.maximum,
            ..HttpMultipartData::default()
        }
    } else if operation == 1 {
        HttpMultipartData {
            phase: owner.data.phase,
            length: owner.data.length,
            written,
            ..HttpMultipartData::default()
        }
    } else {
        return INVALID;
    };
    let action = data.step();
    owner.publish_data(&data);
    action
}
/// Operation0 begins from fresh Native buffer offset;1 resumes after tracing.
/// # Safety
/// Unique owner, initialized independent input and disjoint writable output.
/// Native logging/effects complete after return, never through a Rust borrow.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_request_chunk(
    owner: *mut HttpRequestContext,
    operation: u32,
    input: *const u8,
    length: usize,
    offset: usize,
    output: *mut HttpChunkStep,
) -> i32 {
    // SAFETY: `owner` is null or live, aligned and exclusively lent for this call.
    let Some(owner) = (unsafe { owner.as_mut() }) else {
        return INVALID;
    };
    if operation == 0 {
        owner.chunk_cursor = offset;
        owner.chunk_initial = 1;
    } else if operation != 1 {
        return INVALID;
    }
    if output.is_null() {
        return INVALID;
    }
    // SAFETY: the caller lends `length` initialized bytes at `input` (null only when empty).
    let (result, step) = match unsafe { bytes(input, length) } {
        Ok(input) => crate::framing::chunk_step(
            input,
            owner.chunk_cursor,
            owner.facts.header_length as usize,
            owner.chunk_initial != 0,
        ),
        Err(error) => (error, HttpChunkStep::default()),
    };
    // SAFETY: `output` is non-null (checked above), aligned and writable.
    unsafe {
        output.write(step);
    }
    if result == -2 {
        owner.flag(EXCEPTED, true);
    }
    if result > 0 {
        // SAFETY: `output` is non-null (checked above), aligned and initialized per the caller contract.
        let output = unsafe { &*output };
        if result == 2 {
            owner.flag(KNOWN, true);
            owner.facts.content_length = output.body_length;
        } else if result == 1 {
            owner.chunk_cursor = output.next;
            owner.chunk_initial = 0;
        }
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::ptr;
    fn framed(input: &[u8]) -> Box<HttpRequestContext> {
        let owner = unsafe { Box::from_raw(swr_v2_http_request_new()) };
        assert_eq!(owner.observe(), HttpRequestObservation::default());
        let mut owner = owner;
        let mut offset = 0;
        assert_eq!(
            unsafe {
                swr_v2_http_request_frame(
                    &mut *owner,
                    0,
                    input.as_ptr(),
                    input.len(),
                    offset,
                    &mut offset,
                )
            },
            0
        );
        assert_eq!(
            unsafe {
                swr_v2_http_request_frame(
                    &mut *owner,
                    1,
                    input.as_ptr(),
                    input.len(),
                    offset,
                    &mut offset,
                )
            },
            0
        );
        owner
    }
    fn headers(owner: &mut HttpRequestContext, input: &[u8]) {
        let mut result = HttpRequestHeaderResult::default();
        let mut operation = 0;
        loop {
            let action = unsafe {
                swr_v2_http_request_headers(
                    owner,
                    operation,
                    input.as_ptr(),
                    input.len(),
                    &mut result,
                )
            };
            assert_eq!(result.number_errors, 0);
            if action == 0 {
                break;
            }
            assert_eq!(action, 1);
            assert_eq!(owner.control(10, result.boundary.length as u64, 0), 0);
            operation = 1;
        }
    }
    #[test]
    fn ordinary_request_metadata_and_header_query_have_one_rust_owner() {
        let input = b"GET /index.html HTTP/1.1\r\nHost: local\r\nConnection: keep-alive\r\n\r\n";
        let mut owner = framed(input);
        headers(&mut owner, input);
        let facts = owner.observe();
        assert_eq!(
            (
                facts.method,
                facts.version,
                facts.url_offset,
                facts.url_length
            ),
            (2, 2, 4, 11)
        );
        assert_eq!(facts.header_length as usize, input.len());
        assert_ne!(facts.flags & KEEPALIVE, 0);
        assert_ne!(facts.flags & HEADER_PARSED, 0);
        let mut value = HttpSpan::default();
        assert_eq!(
            unsafe {
                swr_v2_http_request_header(
                    &*owner,
                    input.as_ptr(),
                    input.len(),
                    b"Host".as_ptr(),
                    4,
                    &mut value,
                )
            },
            1
        );
        assert_eq!(&input[value.offset..value.offset + value.length], b"local");
    }
    #[test]
    fn repeated_name_and_template_updates_reuse_owned_capacity() {
        let mut owner = HttpRequestContext::default();
        assert_eq!(owner.control(10, 0, 0), 0);
        let first = vec![b'n'; 80];
        assert_eq!(owner.set_text(1, &first), 0);
        let name_pointer = owner.form.as_ref().unwrap().name.as_ptr();
        let name_capacity = owner.form.as_ref().unwrap().name.capacity();
        for name in [b"Content-Disposition".as_slice(), b"Content-Type", b"x"] {
            assert_eq!(owner.set_text(1, name), 0);
            let form = owner.form.as_ref().unwrap();
            assert_eq!(form.name.as_ptr(), name_pointer);
            assert_eq!(form.name.capacity(), name_capacity);
            assert_eq!(form.name, name);
        }
        assert_eq!(owner.set_text(0, b"/ordinary/initial/directory"), 0);
        let pointer = owner.form.as_ref().unwrap().template.as_ptr();
        let capacity = owner.form.as_ref().unwrap().template.capacity();
        assert_eq!(owner.set_text(0, b"/tmp"), 0);
        let form = owner.form.as_ref().unwrap();
        assert_eq!(form.template.as_ptr(), pointer);
        assert_eq!(form.template.capacity(), capacity);
        assert_eq!(form.template, b"/tmp/swoole.upfile.XXXXXX");
        assert_eq!(form.name, b"x");
        assert_eq!(owner.control(12, 0, 0), 0);
        assert_eq!(owner.form.as_ref().unwrap().name.capacity(), 0);
        assert_eq!(owner.form.as_ref().unwrap().template.capacity(), 0);
    }
    #[test]
    fn text_effect_snapshots_use_initialized_independent_backing() {
        let mut owner = HttpRequestContext::default();
        assert_eq!(owner.control(10, 0, 0), 0);
        for length in [0, 19, 80] {
            let name = vec![b'n'; length];
            assert_eq!(owner.set_text(1, &name), 0);
            let mut scratch = [0xcc; 64];
            let mut span = crate::HttpProxyText {
                data: std::ptr::null(),
                length: 0,
            };
            let mut lease = std::ptr::null_mut();
            assert_eq!(
                unsafe {
                    swr_v2_http_request_text_snapshot_new(
                        &owner,
                        1,
                        scratch.as_mut_ptr(),
                        scratch.len(),
                        &mut span,
                        &mut lease,
                    )
                },
                0
            );
            assert_eq!(span.length, name.len());
            assert_eq!(
                unsafe { std::slice::from_raw_parts(span.data, span.length) },
                name
            );
            assert_eq!(unsafe { *span.data.add(span.length) }, 0);
            if length < scratch.len() {
                assert!(lease.is_null());
                assert_eq!(span.data, scratch.as_ptr());
                assert!(scratch[length + 1..].iter().all(|&b| b == 0xcc));
            } else {
                assert!(!lease.is_null());
                assert!(scratch.iter().all(|&b| b == 0xcc));
            }
            unsafe { swr_v2_http_request_text_snapshot_drop(lease) };
        }
    }
    #[test]
    fn upload_uses_authoritative_name_and_template_without_native_string_copies() {
        let mut owner = HttpRequestContext::default();
        assert_eq!(owner.control(10, 0, 0), 0);
        assert_eq!(owner.set_text(1, b"Content-Disposition"), 0);
        assert_eq!(owner.set_text(0, b"/ordinary"), 0);
        let mut count = 0;
        let plan = unsafe { swr_v2_http_request_upload_plan(&owner, 0, 0, &mut count) };
        assert!(!plan.is_null());
        assert_eq!(unsafe { std::slice::from_raw_parts(plan, count) }, &[1]);
        // Normal accepted-file effects resume outside Rust; the plan is static.
        for (stage, expected) in [(1, &[2, 3][..]), (2, &[4][..]), (3, &[7, 0][..])] {
            let plan = unsafe { swr_v2_http_request_upload_plan(&owner, stage, 1, &mut count) };
            assert!(!plan.is_null());
            assert_eq!(unsafe { std::slice::from_raw_parts(plan, count) }, expected);
        }
        owner.form.as_mut().unwrap().uploaded = 17;
        let mut native = [0xcc; 128];
        assert_eq!(
            unsafe {
                swr_v2_http_request_upload_template(&mut owner, native.as_mut_ptr(), native.len())
            },
            0
        );
        let expected = b"/ordinary/swoole.upfile.XXXXXX";
        assert_eq!(&native[..expected.len()], expected);
        assert_eq!(native[expected.len()], 0);
        assert!(native[expected.len() + 1..].iter().all(|&b| b == 0xcc));
        assert_eq!(owner.form.as_ref().unwrap().uploaded, 0);
        assert_eq!(owner.text(1).unwrap(), b"Content-Disposition");
    }
    #[test]
    fn owned_multipart_name_template_and_clean_preserve_the_separate_form() {
        let input = b"POST /upload HTTP/1.1\r\nContent-Length: 17\r\nContent-Type: multipart/form-data; boundary=ordinary\r\n\r\n";
        let mut owner = framed(input);
        headers(&mut owner, input);
        assert_eq!(owner.observe().has_form, 1);
        assert_eq!(owner.observe().content_length, 17);
        assert_eq!(owner.set_text(0, b"/private/tmp/proof"), 0);
        let mut name = b"Content-Disposition".to_vec();
        assert_eq!(
            unsafe { swr_v2_http_request_text_set(&mut *owner, 1, name.as_ptr(), name.len()) },
            0
        );
        name.fill(b'x');
        let mut count = 0;
        assert_eq!(
            unsafe { swr_v2_http_request_text_copy(&*owner, 1, ptr::null_mut(), 0, &mut count) },
            0
        );
        let mut native = vec![b'?'; count + 8];
        assert_eq!(
            unsafe {
                swr_v2_http_request_text_copy(&*owner, 1, native.as_mut_ptr(), count, &mut count)
            },
            0
        );
        assert_eq!(&native[..count], b"Content-Disposition");
        assert!(native[count..].iter().all(|&b| b == b'?'));
        assert_eq!(
            owner.text(0).unwrap(),
            b"/private/tmp/proof/swoole.upfile.XXXXXX"
        );
        assert_eq!(owner.control(0, 0, 0), 0);
        assert_eq!(owner.observe().has_form, 1);
        assert_eq!(owner.observe().flags, 0);
        assert_eq!(owner.observe().method, 0);
        assert_eq!(owner.text(1).unwrap(), b"Content-Disposition");
        assert_eq!(owner.control(4, 0, 0), 0);
        assert_eq!(owner.observe().has_form, 0);
    }
    #[test]
    fn ordinary_file_and_form_data_callbacks_publish_owned_accounting() {
        let mut owner = HttpRequestContext::default();
        assert_eq!(owner.control(10, 8, 0), 0);
        assert_eq!(owner.control(1, 128, 0), 0);
        assert_eq!(owner.control(9, 100, 0), 0);
        assert_eq!(
            unsafe { swr_v2_http_request_data(&mut owner, 0, 1, 4, 9, 0) },
            2
        );
        assert_eq!(owner.observe().upload_size, 4);
        assert_eq!(
            unsafe { swr_v2_http_request_data(&mut owner, 1, 0, 0, 0, 4) },
            0
        );
        assert_eq!(owner.observe().upload_size, 4);
        assert_eq!(
            unsafe { swr_v2_http_request_data(&mut owner, 0, 0, 3, 9, 0) },
            1
        );
        assert_eq!(owner.observe().upload_size, 4);
        assert_eq!(owner.observe().flags, 0);
    }
    #[test]
    fn ordinary_chunk_cursor_finishes_before_native_metadata_observation() {
        let input = b"POST / HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n3\r\nabc\r\n0\r\n\r\n";
        let mut owner = framed(input);
        headers(&mut owner, input);
        let offset = owner.observe().header_length as usize;
        let mut step = HttpChunkStep::default();
        assert_eq!(
            unsafe {
                swr_v2_http_request_chunk(
                    &mut *owner,
                    0,
                    input.as_ptr(),
                    input.len(),
                    offset,
                    &mut step,
                )
            },
            1
        );
        assert_eq!(step.chunk_length, 3);
        assert_eq!(
            unsafe {
                swr_v2_http_request_chunk(&mut *owner, 1, input.as_ptr(), input.len(), 0, &mut step)
            },
            2
        );
        assert_eq!(owner.observe().content_length, 13);
        assert_ne!(owner.observe().flags & KNOWN, 0);
    }
    #[test]
    fn multipart_emit_effects_publish_only_when_native_step_requests_them() {
        let mut owner = HttpRequestContext::default();
        owner.facts.header_length = 23;
        assert_eq!(owner.control(7, 1, 0), 0);
        assert_ne!(owner.observe().flags & MULTIPART_HEADER, 0);
        assert_eq!(owner.control(7, 2, 0), 0);
        assert_eq!(owner.observe().flags & MULTIPART_HEADER, 0);
        assert_eq!(owner.control(7, 4, 40), 0);
        assert_eq!(owner.observe().content_length, 17);
        assert_ne!(owner.observe().flags & DISPATCHED, 0);
    }
}
