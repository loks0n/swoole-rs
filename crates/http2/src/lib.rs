//! HTTP/2 policy and one externally native-owned send queue; native code executes effects.
#![cfg_attr(
    not(test),
    deny(
        clippy::undocumented_unsafe_blocks,
        clippy::multiple_unsafe_ops_per_block
    )
)]
#[cfg(test)]
mod queue_faults;
mod receive;
pub use receive::*;
mod files;
pub use files::*;
mod decompression;
pub use decompression::*;
mod connection;
pub use connection::*;
mod send_queue;
pub use send_queue::*;
use std::ffi::c_char;
use std::ptr;

#[repr(C)]
#[derive(Clone, Copy, Default, Debug, PartialEq, Eq)]
pub struct Http2Settings {
    pub header_table_size: u32,
    pub enable_push: u32,
    pub max_concurrent_streams: u32,
    pub init_window_size: u32,
    pub max_frame_size: u32,
    pub max_header_list_size: u32,
}

#[repr(C)]
#[derive(Clone, Copy, Default, Debug, PartialEq, Eq)]
pub struct Http2FrameFacts {
    pub length: u32,
    pub kind: u32,
    pub flags: u32,
    pub stream_id: u32,
    pub publish_last_id: u32,
    pub action: u32,
}

#[repr(C)]
#[derive(Clone, Copy, Default, Debug, PartialEq, Eq)]
pub struct Http2SettingPlan {
    pub field: i32,
    pub set_value: u32,
    pub set_window: u32,
    pub change_deflater: u32,
}

#[repr(C)]
#[derive(Clone, Copy, Default, Debug, PartialEq, Eq)]
pub struct Http2ChunkPlan {
    pub length: usize,
    pub flags: u32,
}

#[repr(C)]
#[derive(Clone, Copy, Default, Debug, PartialEq, Eq)]
pub struct Http2ResponsePlan {
    pub end: u32,
    pub ready: u32,
}

#[no_mangle]
pub extern "C" fn sw_rs_http2_setting_index(id: u32) -> i32 {
    if (1..=6).contains(&id) {
        (id - 1).cast_signed()
    } else {
        -1
    }
}

fn header(kind: u8, length: u32, flags: u8, stream_id: u32) -> [u8; 9] {
    let id = stream_id.to_be_bytes();
    let [_, high, middle, low] = length.to_be_bytes();
    [high, middle, low, kind, flags, id[0], id[1], id[2], id[3]]
}

#[repr(C)]
#[derive(Clone, Copy, Default, Debug, PartialEq, Eq)]
pub struct Http2WindowPlan {
    pub value: u32,
    pub increment: u32,
}

/// # Safety
/// `out` is writable POD. The caller refreshes facts after every native send/resume.
#[no_mangle]
pub unsafe extern "C" fn sw_rs_http2_window_plan(
    current: u32,
    amount: usize,
    initial: u32,
    credit: u32,
    out: *mut Http2WindowPlan,
) {
    if out.is_null() {
        return;
    }
    #[expect(
        clippy::cast_possible_truncation,
        reason = "native uint32_t window arithmetic"
    )]
    let value = if credit != 0 {
        current.wrapping_add(amount as u32)
    } else {
        current.wrapping_sub(amount as u32)
    };
    let increment = if value < initial / 4 {
        initial - value
    } else {
        0
    };
    ptr::write(out, Http2WindowPlan { value, increment });
}

#[no_mangle]
pub extern "C" fn sw_rs_http2_data_rejected(
    current: usize,
    additional: usize,
    maximum: u32,
    ended: u32,
) -> u32 {
    u32::from(current.wrapping_add(additional) > maximum as usize || ended != 0)
}

#[repr(u32)]
enum FrameAction {
    Settings,
    Headers,
    Data,
    PingReply,
    WindowUpdate,
    Reset,
    Goaway,
    Other,
    SettingsAck,
    PingAck,
    IgnorePush,
}

fn frame_action(client: u32, kind: u32, flags: u32) -> u32 {
    let ack = flags & 1 != 0;
    let action = match kind {
        4 if ack => FrameAction::SettingsAck,
        4 => FrameAction::Settings,
        1 => FrameAction::Headers,
        0 => FrameAction::Data,
        6 if ack => FrameAction::PingAck,
        6 => FrameAction::PingReply,
        8 => FrameAction::WindowUpdate,
        3 => FrameAction::Reset,
        7 => FrameAction::Goaway,
        5 if client != 0 => FrameAction::IgnorePush,
        _ => FrameAction::Other,
    };
    action as u32
}

/// Queue storage and native allocation/release remain owned by the client.
#[no_mangle]
pub extern "C" fn sw_rs_http2_queue_action(bound: u32, queued: usize, limit: u32) -> u32 {
    if bound == 0 {
        0 // direct send
    } else if queued > limit as usize {
        2 // preserve the original strict greater-than limit
    } else {
        1 // append one native-owned frame
    }
}

#[no_mangle]
pub extern "C" fn sw_rs_http2_send_complete(sent: isize, wanted: usize) -> u32 {
    // Native compares `send_all(...) != (ssize_t) len`: the cast wraps.
    u32::from(sent == wanted.cast_signed())
}

/// Match locale-folded native header bytes; Rust selects role-specific effects.
/// # Safety
/// `folded` addresses `copied` initialized bytes, or is null when copied is zero.
unsafe fn header_kind(role: u32, folded: *const u8, copied: usize, logical: usize) -> u32 {
    if copied == 0 || copied != logical || folded.is_null() {
        return 0;
    }
    let name = std::slice::from_raw_parts(folded, copied);
    match (role, name) {
        (0, b":method") => 1,
        (0, b":path") => 2,
        (0, b":authority") => 3,
        (0 | 2, b"content-type") => 4,
        (0, b"cookie") => 5,
        (0 | 2, b"content-length") => 6,
        (0, b"accept-encoding") => 7,
        (1, b":status") => 8,
        (1, b"content-encoding") => 9,
        (1, b"set-cookie") => 10,
        (2, b"server") => 11,
        (2, b"date") => 12,
        (3, b"host") => 13,
        _ => 0,
    }
}

#[repr(C)]
#[derive(Clone, Copy, Default, Debug, PartialEq, Eq)]
pub struct Http2HeaderPlan {
    pub kind: u32,
    pub publish_flags: u32,
    pub suppress: u32,
    pub capture_content_type: u32,
}

/// # Safety
/// `folded` addresses `copied` initialized bytes; `out` is writable POD.
#[no_mangle]
pub unsafe extern "C" fn sw_rs_http2_header_plan(
    role: u32,
    folded: *const u8,
    copied: usize,
    logical: usize,
    can_capture: u32,
    out: *mut Http2HeaderPlan,
) {
    if out.is_null() {
        return;
    }
    let kind = header_kind(role, folded, copied, logical);
    let server = role == 2;
    let publish_flags = if server {
        match kind {
            11 => 2,
            12 => 16,
            4 => 32,
            _ => 0,
        }
    } else {
        0
    };
    ptr::write(
        out,
        Http2HeaderPlan {
            kind,
            publish_flags,
            suppress: u32::from(server && kind == 6),
            capture_content_type: u32::from(server && kind == 4 && can_capture != 0),
        },
    );
}

#[repr(C)]
pub struct Http2RespondFacts {
    pub header_sent: u32,
    pub trailer_present: u32,
    pub chunked: u32,
    pub shutting_down: u32,
    pub streams_empty: u32,
    pub body_length: usize,
}

// Module-local effect tags mirror the private native executor.
mod respond_action {
    pub const START: u32 = 0;
    pub const HEADER: u32 = 1;
    pub const COMMIT_END: u32 = 2;
    pub const EMPTY: u32 = 3;
    pub const BODY: u32 = 4;
    pub const TRAILER: u32 = 5;
    pub const ERROR_CLOSE: u32 = 6;
    pub const REMOVE: u32 = 7;
    pub const ERROR_SHUTDOWN: u32 = 8;
    pub const SUCCESS_SHUTDOWN: u32 = 9;
    pub const FALSE: u32 = 10;
    pub const TRUE: u32 = 11;
}

/// Choose one native effect. No borrowed state or Rust frame survives its execution.
///
/// # Safety
/// `facts` addresses initialized POD; the caller refreshes only the facts needed
/// after each native effect, preserving cached trailer presence and end flags.
#[no_mangle]
pub unsafe extern "C" fn sw_rs_http2_respond_next(
    previous: u32,
    succeeded: u32,
    facts: *const Http2RespondFacts,
) -> u32 {
    use respond_action::*;
    if facts.is_null() {
        return FALSE;
    }
    let facts = &*facts;
    match previous {
        START if facts.header_sent == 0 => HEADER,
        START => COMMIT_END,
        HEADER if succeeded != 0 => COMMIT_END,
        HEADER => FALSE,
        COMMIT_END if facts.chunked != 0 && facts.body_length == 0 => EMPTY,
        COMMIT_END => BODY,
        EMPTY | BODY | TRAILER if succeeded == 0 => ERROR_CLOSE,
        EMPTY => BODY,
        BODY if facts.trailer_present != 0 => TRAILER,
        BODY | TRAILER => REMOVE,
        ERROR_CLOSE if facts.shutting_down != 0 && facts.streams_empty != 0 => ERROR_SHUTDOWN,
        ERROR_CLOSE => FALSE,
        REMOVE if facts.shutting_down != 0 && facts.streams_empty != 0 => SUCCESS_SHUTDOWN,
        REMOVE => TRUE,
        _ => FALSE,
    }
}

#[no_mangle]
pub extern "C" fn sw_rs_http2_response_status(status: i32) -> i32 {
    if status == 0 {
        200
    } else {
        status
    }
}

#[no_mangle]
pub extern "C" fn sw_rs_http2_header_defaults(published: u32) -> u32 {
    (2 | 16 | 32) & !published
}

#[no_mangle]
pub extern "C" fn sw_rs_http2_content_length_rejected(
    complete: u32,
    parsed: i64,
    maximum: u32,
) -> u32 {
    u32::from(complete == 0 || parsed > i64::from(maximum))
}

/// # Safety
/// `folded` addresses `copied` initialized locale-folded bytes (maximum 33 needed).
#[no_mangle]
pub unsafe extern "C" fn sw_rs_http2_media_kind(folded: *const u8, copied: usize) -> u32 {
    if copied == 0 || folded.is_null() {
        return 0;
    }
    let value = std::slice::from_raw_parts(folded, copied);
    if value.starts_with(b"application/x-www-form-urlencoded") {
        1
    } else if value.starts_with(b"multipart/form-data") {
        2
    } else if value.starts_with(b"gzip") {
        3
    } else {
        0
    }
}

/// # Safety
/// `out` addresses nine writable bytes. Integer truncation matches the native header API.
#[no_mangle]
pub unsafe extern "C" fn sw_rs_http2_pack_frame_header(
    out: *mut u8,
    kind: u32,
    length: u32,
    flags: u32,
    stream_id: u32,
) {
    if !out.is_null() {
        #[expect(
            clippy::cast_possible_truncation,
            reason = "the native uint8_t frame type and flags"
        )]
        let bytes = header(kind as u8, length, flags as u8, stream_id);
        ptr::copy_nonoverlapping(bytes.as_ptr(), out, bytes.len());
    }
}

/// # Safety
/// `bytes` addresses four initialized bytes.
#[no_mangle]
pub unsafe extern "C" fn sw_rs_http2_read_u32(bytes: *const u8) -> u32 {
    let mut value = [0; 4];
    ptr::copy_nonoverlapping(bytes, value.as_mut_ptr(), value.len());
    u32::from_be_bytes(value)
}

/// # Safety
/// `out` addresses four writable bytes.
#[no_mangle]
pub unsafe extern "C" fn sw_rs_http2_write_u32(out: *mut u8, value: u32) {
    ptr::copy_nonoverlapping(value.to_be_bytes().as_ptr(), out, 4);
}

/// # Safety
/// `out` addresses `capacity` writable bytes; `settings` addresses an initialized POD.
#[no_mangle]
pub unsafe extern "C" fn sw_rs_http2_pack_settings(
    out: *mut u8,
    capacity: usize,
    settings: *const Http2Settings,
    server: u32,
) -> usize {
    let count = if server != 0 { 5 } else { 6 };
    let size = 9 + count * 6;
    if capacity < size || out.is_null() || settings.is_null() {
        return 0;
    }
    let s = ptr::read(settings);
    let values = [
        s.header_table_size,
        s.enable_push,
        s.max_concurrent_streams,
        s.init_window_size,
        s.max_frame_size,
        s.max_header_list_size,
    ];
    let mut bytes = [0u8; 45];
    bytes[..9].copy_from_slice(&header(4, u32::try_from(count * 6).unwrap_or(0), 0, 0));
    let mut offset = 9;
    for (index, value) in values.iter().enumerate() {
        if server != 0 && index == 1 {
            continue;
        }
        bytes[offset..offset + 2]
            .copy_from_slice(&u16::try_from(index + 1).unwrap_or(0).to_be_bytes());
        bytes[offset + 2..offset + 6].copy_from_slice(&value.to_be_bytes());
        offset += 6;
    }
    ptr::copy_nonoverlapping(bytes.as_ptr(), out, size);
    size
}

/// Decode one item only. Native code invokes the callback before decoding another.
/// # Safety
/// `bytes` addresses six initialized bytes, including original backing-storage
/// preconditions when the caller's positive logical length is smaller than six.
/// Outputs each address initialized writable scalar storage.
#[no_mangle]
pub unsafe extern "C" fn sw_rs_http2_unpack_setting(
    bytes: *const u8,
    id: *mut u16,
    value: *mut u32,
) {
    if bytes.is_null() || id.is_null() || value.is_null() {
        return;
    }
    let mut b = [0u8; 6];
    ptr::copy_nonoverlapping(bytes, b.as_mut_ptr(), 6);
    ptr::write(id, u16::from_be_bytes([b[0], b[1]]));
    ptr::write(value, u32::from_be_bytes([b[2], b[3], b[4], b[5]]));
}

/// # Safety
/// For `available >= 9`, bytes addresses nine initialized bytes. `out` is writable POD.
#[no_mangle]
pub unsafe extern "C" fn sw_rs_http2_decode_frame(
    bytes: *const u8,
    available: usize,
    previous_last_id: u32,
    client: u32,
    out: *mut Http2FrameFacts,
) -> i32 {
    if available < 9 || bytes.is_null() || out.is_null() {
        return 0;
    }
    let mut b = [0u8; 9];
    ptr::copy_nonoverlapping(bytes, b.as_mut_ptr(), 9);
    let id = u32::from_be_bytes([b[5], b[6], b[7], b[8]]) & 0x7fff_ffff;
    ptr::write(
        out,
        Http2FrameFacts {
            length: (u32::from(b[0]) << 16) | (u32::from(b[1]) << 8) | u32::from(b[2]),
            kind: u32::from(b[3]),
            flags: u32::from(b[4]),
            stream_id: id,
            publish_last_id: u32::from(id > previous_last_id),
            action: frame_action(client, u32::from(b[3]), u32::from(b[4])),
        },
    );
    1
}

/// # Safety
/// For `available >= 9`, bytes addresses nine initialized bytes.
#[no_mangle]
pub unsafe extern "C" fn sw_rs_http2_frame_length(bytes: *const u8, available: usize) -> isize {
    if available < 9 || bytes.is_null() {
        return 0;
    }
    let mut b = [0u8; 3];
    ptr::copy_nonoverlapping(bytes, b.as_mut_ptr(), 3);
    let length = (u32::from(b[0]) << 16) | (u32::from(b[1]) << 8) | u32::from(b[2]);
    isize::try_from(length).map_or(-1, |length| length + 9)
}

/// # Safety
/// `out` is writable POD; no native effects happen here.
#[no_mangle]
pub unsafe extern "C" fn sw_rs_http2_setting_plan(
    id: u32,
    value: u32,
    old_value: u32,
    deflater_present: u32,
    server: u32,
    out: *mut Http2SettingPlan,
) {
    if out.is_null() {
        return;
    }
    let field = match id {
        1 | 3 | 4 | 5 | 6 => (id - 1).cast_signed(),
        _ => -1,
    };
    ptr::write(
        out,
        Http2SettingPlan {
            field,
            set_value: u32::from(
                field >= 0 && (id != 1 && (server != 0 || id != 6) || value != old_value),
            ),
            set_window: u32::from(id == 4),
            change_deflater: u32::from(
                id == 1 && value != old_value && (server == 0 || deflater_present != 0),
            ),
        },
    );
}

/// # Safety
/// `out` is writable POD.
#[no_mangle]
pub unsafe extern "C" fn sw_rs_http2_chunk(
    remaining: usize,
    max_frame: u32,
    flags: u32,
    out: *mut Http2ChunkPlan,
) {
    if out.is_null() {
        return;
    }
    let more = remaining > max_frame as usize;
    ptr::write(
        out,
        Http2ChunkPlan {
            length: if more { max_frame as usize } else { remaining },
            flags: if more {
                0
            } else {
                u32::from(flags.to_le_bytes()[0])
            },
        },
    );
}

/// 0: send as planned, 1: native warning, 2: native yield, 3: truncate to window.
#[no_mangle]
pub extern "C" fn sw_rs_http2_window_action(length: usize, window: u32, may_suspend: u32) -> u32 {
    if length <= window as usize {
        0
    } else if may_suspend == 0 {
        1
    } else if window == 0 {
        2
    } else {
        3
    }
}

#[no_mangle]
pub extern "C" fn sw_rs_http2_stream_flags(pipeline: u32, pipeline_read: u32) -> u32 {
    (if pipeline != 0 { 2 } else { 0 }) | (if pipeline_read != 0 { 8 } else { 0 })
}

#[repr(C)]
pub struct Http2InflateStep {
    pub end_headers: u32,
    pub finish: u32,
}

/// # Safety
/// `out` is writable POD; copied facts are reobserved after native header effects.
#[no_mangle]
pub unsafe extern "C" fn sw_rs_http2_inflate_step(
    flags: u32,
    remaining: usize,
    client_role: u32,
    out: *mut Http2InflateStep,
) {
    if out.is_null() {
        return;
    }
    let end_headers = flags & 1 != 0;
    ptr::write(
        out,
        Http2InflateStep {
            end_headers: u32::from(end_headers),
            finish: u32::from(
                end_headers || remaining == 0 && (client_role != 0 || flags & 2 == 0),
            ),
        },
    );
}

#[no_mangle]
pub extern "C" fn sw_rs_http2_request_value_default(is_string: u32, length: usize) -> u32 {
    u32::from(is_string == 0 || length == 0)
}

#[no_mangle]
pub extern "C" fn sw_rs_http2_authority_with_port(secure: u32, port: i32) -> u32 {
    u32::from(port != if secure != 0 { 443 } else { 80 })
}

#[no_mangle]
pub extern "C" fn sw_rs_http2_headers_flags(empty: u32, end_stream: u32, stream_flags: u32) -> u32 {
    4 | u32::from(empty != 0 && end_stream != 0 && stream_flags & 2 == 0)
}

/// Apply a copied stream flag transition. Callers publish into the sole native stream.
#[no_mangle]
pub extern "C" fn sw_rs_http2_stream_update(flags: u32, end: u32, receiving: u32) -> u32 {
    flags
        | if receiving != 0 && end == 0 {
            4
        } else {
            u32::from(receiving == 0 && end != 0)
        }
}

#[no_mangle]
pub extern "C" fn sw_rs_http2_write_allowed(exists: u32, stream_flags: u32) -> u32 {
    u32::from(exists != 0 && stream_flags & 2 != 0 && stream_flags & 1 == 0)
}

/// # Safety
/// `out` is writable POD.
#[no_mangle]
pub unsafe extern "C" fn sw_rs_http2_response(
    kind: u32,
    flags: u32,
    stream_flags: u32,
    pipeline_read: u32,
    out: *mut Http2ResponsePlan,
) {
    if out.is_null() {
        return;
    }
    let end = flags & 1 != 0 || kind == 3 || kind == 7;
    let pipeline = (pipeline_read != 0 || stream_flags & 8 != 0) && stream_flags & 4 != 0;
    ptr::write(
        out,
        Http2ResponsePlan {
            end: u32::from(end),
            ready: u32::from(end || pipeline),
        },
    );
}

#[no_mangle]
pub extern "C" fn sw_rs_http2_type_name(kind: i32) -> *const c_char {
    let text: &'static [u8] = match kind {
        0 => b"DATA\0",
        1 => b"HEADERS\0",
        2 => b"PRIORITY\0",
        3 => b"RST_STREAM\0",
        4 => b"SETTINGS\0",
        5 => b"PUSH_PROMISE\0",
        6 => b"PING\0",
        7 => b"GOAWAY\0",
        8 => b"WINDOW_UPDATE\0",
        9 => b"CONTINUATION\0",
        _ => b"UNKNOWN\0",
    };
    text.as_ptr().cast()
}

#[no_mangle]
pub extern "C" fn sw_rs_http2_color_group(kind: i32) -> u32 {
    match kind {
        0 | 8 => 0,
        1 | 4 | 5 | 9 => 1,
        2 | 6 => 2,
        _ => 3,
    }
}

#[cfg(test)]
#[expect(
    clippy::cast_possible_truncation,
    clippy::cast_possible_wrap,
    reason = "tests drive the native integer interfaces with literal and loop values"
)]
mod tests {
    use super::*;
    #[test]
    fn send_complete_matches_the_wrapping_native_cast() {
        for wanted in [
            0,
            1,
            isize::MAX as usize,
            isize::MAX as usize + 1,
            usize::MAX,
        ] {
            for sent in [-1, 0, 1, isize::MIN, isize::MAX] {
                assert_eq!(
                    sw_rs_http2_send_complete(sent, wanted),
                    u32::from(sent == wanted as isize)
                );
            }
        }
        assert_eq!(sw_rs_http2_send_complete(-1, usize::MAX), 1);
    }
    #[test]
    fn codec_and_unknown_settings() {
        for id in 0..=8 {
            assert_eq!(
                sw_rs_http2_setting_index(id),
                if (1..=6).contains(&id) {
                    id as i32 - 1
                } else {
                    -1
                }
            );
        }
        let s = Http2Settings {
            header_table_size: 0x0102_0304,
            enable_push: 1,
            max_concurrent_streams: u32::MAX,
            init_window_size: 65535,
            max_frame_size: 16384,
            max_header_list_size: 0,
        };
        for server in 0..=1 {
            let mut out = [0xcc; 47];
            let n = unsafe {
                sw_rs_http2_pack_settings(out.as_mut_ptr().add(1), 45, &raw const s, server)
            };
            assert_eq!(n, if server == 0 { 45 } else { 39 });
            assert_eq!(out[0], 0xcc);
            assert_eq!(out[n + 1], 0xcc);
            let mut frame = Http2FrameFacts::default();
            assert_eq!(
                unsafe { sw_rs_http2_decode_frame(out.as_ptr().add(1), n, 0, 0, &raw mut frame) },
                1
            );
            assert_eq!((frame.kind, frame.length), (4, (n - 9) as u32));
            for item in out[10..n + 1].as_chunks::<6>().0 {
                let mut id = 0;
                let mut value = 0;
                unsafe { sw_rs_http2_unpack_setting(item.as_ptr(), &raw mut id, &raw mut value) };
                assert!((1..=6).contains(&id));
                if id == 1 {
                    assert_eq!(value, s.header_table_size);
                }
                if server != 0 {
                    assert_ne!(id, 2);
                }
            }
        }
    }
    #[test]
    fn framing_and_short_prefix() {
        assert_eq!(unsafe { sw_rs_http2_frame_length(ptr::null(), 8) }, 0);
        let bytes = header(255, 0x00ff_ffff, 0x80, 0xffff_ffff);
        let mut f = Http2FrameFacts::default();
        assert_eq!(
            unsafe { sw_rs_http2_decode_frame(bytes.as_ptr(), 9, 0, 0, &raw mut f) },
            1
        );
        assert_eq!(f.stream_id, 0x7fff_ffff);
        assert_eq!(f.publish_last_id, 1);
        assert_eq!(
            unsafe { sw_rs_http2_frame_length(bytes.as_ptr(), 9) },
            0x00ff_ffff + 9
        );
    }
    #[test]
    fn role_specific_setting_effects() {
        for id in 0..=7 {
            for server in 0..=1 {
                for has_deflater in 0..=1 {
                    let mut p = Http2SettingPlan::default();
                    unsafe { sw_rs_http2_setting_plan(id, 2, 1, has_deflater, server, &raw mut p) };
                    assert_eq!(
                        p.field,
                        if [1, 3, 4, 5, 6].contains(&id) {
                            id as i32 - 1
                        } else {
                            -1
                        }
                    );
                    assert_eq!(
                        p.change_deflater,
                        u32::from(id == 1 && (server == 0 || has_deflater != 0))
                    );
                    assert_eq!(p.set_window, u32::from(id == 4));
                }
            }
        }
    }
    #[test]
    fn chunk_window_and_pipeline_bits() {
        let mut chunk = Http2ChunkPlan::default();
        unsafe { sw_rs_http2_chunk(20, 16, 1, &raw mut chunk) };
        assert_eq!(
            chunk,
            Http2ChunkPlan {
                length: 16,
                flags: 0
            }
        );
        unsafe { sw_rs_http2_chunk(16, 16, 257, &raw mut chunk) };
        assert_eq!(chunk.flags, 1);
        assert_eq!(sw_rs_http2_window_action(16, 16, 0), 0);
        assert_eq!(sw_rs_http2_window_action(16, 0, 0), 1);
        assert_eq!(sw_rs_http2_window_action(16, 0, 1), 2);
        assert_eq!(sw_rs_http2_window_action(16, 8, 1), 3);
        for flags in 0..16 {
            for read in 0..=1 {
                for kind in 0..=9 {
                    for frame_flags in 0..8 {
                        let mut p = Http2ResponsePlan::default();
                        unsafe { sw_rs_http2_response(kind, frame_flags, flags, read, &raw mut p) };
                        let end = frame_flags & 1 != 0 || kind == 3 || kind == 7;
                        assert_eq!(p.end, u32::from(end));
                        assert_eq!(
                            p.ready,
                            u32::from(end || ((read != 0 || flags & 8 != 0) && flags & 4 != 0))
                        );
                    }
                }
            }
        }
        assert_eq!(sw_rs_http2_stream_flags(1, 1), 10);
        assert_eq!(sw_rs_http2_headers_flags(1, 1, 0), 5);
        assert_eq!(sw_rs_http2_headers_flags(1, 1, 2), 4);
        assert_eq!(sw_rs_http2_write_allowed(0, 2), 0);
        assert_eq!(sw_rs_http2_write_allowed(1, 3), 0);
        assert_eq!(sw_rs_http2_write_allowed(1, 2), 1);
    }
}
