//! The llhttp parser Swoole links (`thirdparty/llhttp`), bound by hand: its
//! parser struct, settings table and the API the HTTP client uses, plus
//! `swoole_llhttp_parser_init`/`_execute` from `include/swoole_llhttp.h`.
use libc::{c_char, c_int, c_void, size_t};

/// `HPE_OK`, `HPE_PAUSED` and `HPE_PAUSED_UPGRADE`.
pub(crate) const OK: c_int = 0;
pub(crate) const PAUSED: c_int = 21;
const PAUSED_UPGRADE: c_int = 22;
/// `HTTP_RESPONSE`.
const RESPONSE: c_int = 2;

/// `llhttp_t` (`llhttp__internal_t`).
#[repr(C)]
pub(crate) struct Parser {
    index: i32,
    span_pos0: *mut c_void,
    span_cb0: *mut c_void,
    pub(crate) error: i32,
    reason: *const c_char,
    error_pos: *const c_char,
    pub(crate) data: *mut c_void,
    current: *mut c_void,
    content_length: u64,
    kind: u8,
    method: u8,
    http_major: u8,
    http_minor: u8,
    header_state: u8,
    lenient_flags: u16,
    pub(crate) upgrade: u8,
    finish: u8,
    flags: u16,
    pub(crate) status_code: u16,
    initial_message_completed: u8,
    settings: *const c_void,
}

pub(crate) type DataCallback = unsafe extern "C" fn(*mut Parser, *const c_char, size_t) -> c_int;
pub(crate) type Callback = unsafe extern "C" fn(*mut Parser) -> c_int;

/// `llhttp_settings_t`.
#[repr(C)]
#[derive(Default)]
pub(crate) struct Settings {
    pub(crate) on_message_begin: Option<Callback>,
    pub(crate) on_protocol: Option<DataCallback>,
    pub(crate) on_url: Option<DataCallback>,
    pub(crate) on_status: Option<DataCallback>,
    pub(crate) on_method: Option<DataCallback>,
    pub(crate) on_version: Option<DataCallback>,
    pub(crate) on_header_field: Option<DataCallback>,
    pub(crate) on_header_value: Option<DataCallback>,
    pub(crate) on_chunk_extension_name: Option<DataCallback>,
    pub(crate) on_chunk_extension_value: Option<DataCallback>,
    pub(crate) on_headers_complete: Option<Callback>,
    pub(crate) on_body: Option<DataCallback>,
    pub(crate) on_message_complete: Option<Callback>,
    pub(crate) on_protocol_complete: Option<Callback>,
    pub(crate) on_url_complete: Option<Callback>,
    pub(crate) on_status_complete: Option<Callback>,
    pub(crate) on_method_complete: Option<Callback>,
    pub(crate) on_version_complete: Option<Callback>,
    pub(crate) on_header_field_complete: Option<Callback>,
    pub(crate) on_header_value_complete: Option<Callback>,
    pub(crate) on_chunk_extension_name_complete: Option<Callback>,
    pub(crate) on_chunk_extension_value_complete: Option<Callback>,
    pub(crate) on_chunk_header: Option<Callback>,
    pub(crate) on_chunk_complete: Option<Callback>,
    pub(crate) on_reset: Option<Callback>,
}

unsafe extern "C" {
    fn llhttp_init(parser: *mut Parser, kind: c_int, settings: *const Settings);
    fn llhttp_execute(parser: *mut Parser, data: *const c_char, length: size_t) -> c_int;
    fn llhttp_finish(parser: *mut Parser) -> c_int;
    fn llhttp_message_needs_eof(parser: *const Parser) -> c_int;
    fn llhttp_should_keep_alive(parser: *const Parser) -> c_int;
    fn llhttp_resume(parser: *mut Parser);
    fn llhttp_resume_after_upgrade(parser: *mut Parser);
    fn llhttp_get_error_pos(parser: *const Parser) -> *const c_char;
}

impl Parser {
    /// A zeroed parser, as upstream's `llhttp_t parser = {}`.
    pub(crate) fn new() -> Self {
        // SAFETY: llhttp_t is plain data; all-zero is upstream's initial value.
        unsafe { std::mem::zeroed() }
    }

    /// `swoole_llhttp_parser_init(parser, HTTP_RESPONSE, data)`.
    pub(crate) fn init_response(&mut self, data: *mut c_void) {
        // SAFETY: a parser we own; llhttp keeps no settings pointer from init.
        unsafe { llhttp_init(self, RESPONSE, std::ptr::null()) };
        self.data = data;
    }

    /// `swoole_llhttp_parser_execute`: how many bytes parsed; a pause resumes.
    pub(crate) fn execute(&mut self, settings: &'static Settings, input: &[u8]) -> usize {
        self.settings = std::ptr::from_ref(settings).cast();
        // SAFETY: a parser we own over the caller's bytes; callbacks receive it.
        let result = unsafe { llhttp_execute(self, input.as_ptr().cast(), input.len()) };
        if result == OK {
            return input.len();
        }
        // SAFETY: as above; the error position points into `input`.
        let position = unsafe { llhttp_get_error_pos(self) };
        let parsed = (position as usize).wrapping_sub(input.as_ptr() as usize);
        if result == PAUSED {
            // SAFETY: a paused parser.
            unsafe { llhttp_resume(self) };
        } else if result == PAUSED_UPGRADE {
            // SAFETY: a parser paused for an upgrade.
            unsafe { llhttp_resume_after_upgrade(self) };
        }
        parsed
    }

    pub(crate) fn finish(&mut self) {
        // SAFETY: a parser we own.
        unsafe { llhttp_finish(self) };
    }

    pub(crate) fn needs_eof(&self) -> bool {
        // SAFETY: as above.
        unsafe { llhttp_message_needs_eof(self) == 1 }
    }

    pub(crate) fn keep_alive(&self) -> bool {
        // SAFETY: as above.
        unsafe { llhttp_should_keep_alive(self) != 0 }
    }
}
