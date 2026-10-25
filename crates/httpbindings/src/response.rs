//! Response header policy. Native code performs all allocation/date/codec effects.
use crate::request::{bytes, case_equal};
use crate::{Action, Text};

/// Original native known-header flags; unknown headers retain their custom path.
/// # Safety
/// Name is an initialized readable span for this call only.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_httpbindings_response_header(name: Text) -> i32 {
    const HEADERS: [(&[u8], i32); 7] = [
        (b"Server", 2),
        (b"Connection", 4),
        (b"Date", 16),
        (b"Content-Length", 8),
        (b"Content-Type", 32),
        (b"Transfer-Encoding", 64),
        (b"Content-Encoding", 256),
    ];
    let Some(name) = (unsafe { bytes(name) }) else {
        return -1;
    };
    HEADERS
        .iter()
        .find(|&&(key, _)| case_equal(name, key))
        .map_or(0, |&(_, flag)| flag)
}

#[derive(Clone, Copy)]
#[repr(u32)]
enum Phase {
    Server,
    Date,
    Upgrade,
    Connection,
    ContentType,
    Body,
    Transfer,
    Compress,
    AfterCompress,
    Length,
    Finish,
    Publish,
    Done,
}
const PHASES: [Phase; 13] = [
    Phase::Server,
    Phase::Date,
    Phase::Upgrade,
    Phase::Connection,
    Phase::ContentType,
    Phase::Body,
    Phase::Transfer,
    Phase::Compress,
    Phase::AfterCompress,
    Phase::Length,
    Phase::Finish,
    Phase::Publish,
    Phase::Done,
];
#[repr(u32)]
enum Effect {
    Append = 1,
    Server,
    Date,
    ContentType,
    AssertChunked,
    Compress,
    Encoding,
    Length,
    Publish,
    Done,
}
fn effect(out: &mut Action, kind: Effect) -> i32 {
    out.kind = kind as u32;
    0
}
fn append(out: &mut Action, bytes: &'static [u8]) -> i32 {
    out.text = Text {
        data: bytes.as_ptr(),
        length: bytes.len(),
    };
    effect(out, Effect::Append)
}

/// Advance native header construction after custom header/cookie iteration.
/// Facts: upgrade==1, keepalive, chunked, HEAD, compiled compression, last codec result.
/// Cursor owns no native pointer or allocation; reobserve fields between effects.
/// # Safety
/// Cursor and action are initialized, disjoint writable objects valid for this call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_httpbindings_response_tail(
    cursor: *mut u32,
    headers: u32,
    facts: u32,
    length: usize,
    out: *mut Action,
) -> i32 {
    let (Some(cursor), Some(out)) = (unsafe { cursor.as_mut() }, unsafe { out.as_mut() }) else {
        return -1;
    };
    *out = Action::default();
    loop {
        let Some(&phase) = PHASES.get(*cursor as usize) else {
            return -1;
        };
        use Phase as P;
        match phase {
            P::Server => {
                *cursor = P::Date as u32;
                if headers & 2 == 0 {
                    return effect(out, Effect::Server);
                }
            }
            P::Date => {
                *cursor = P::Upgrade as u32;
                if headers & 16 == 0 {
                    return effect(out, Effect::Date);
                }
            }
            P::Upgrade => {
                *cursor = P::Connection as u32;
                if facts & 1 != 0 {
                    *cursor = P::Publish as u32;
                    return append(out, b"\r\n");
                }
            }
            P::Connection => {
                *cursor = P::ContentType as u32;
                if headers & 4 == 0 {
                    return append(
                        out,
                        if facts & 2 != 0 {
                            b"Connection: keep-alive\r\n"
                        } else {
                            b"Connection: close\r\n"
                        },
                    );
                }
            }
            P::ContentType => {
                *cursor = P::Body as u32;
                if headers & 32 == 0 {
                    return effect(out, Effect::ContentType);
                }
            }
            P::Body => {
                if facts & 4 != 0 {
                    *cursor = P::Transfer as u32;
                    return effect(out, Effect::AssertChunked);
                }
                *cursor = if length != 0 || facts & 8 == 0 {
                    P::Compress
                } else {
                    P::Finish
                } as u32;
            }
            P::Transfer => {
                *cursor = P::Finish as u32;
                if headers & 64 == 0 {
                    return append(out, b"Transfer-Encoding: chunked\r\n");
                }
            }
            P::Compress => {
                *cursor = P::AfterCompress as u32;
                if facts & 16 != 0 {
                    return effect(out, Effect::Compress);
                }
                *cursor = P::Length as u32;
            }
            P::AfterCompress => {
                *cursor = P::Length as u32;
                if facts & 32 != 0 {
                    return effect(out, Effect::Encoding);
                }
            }
            P::Length => {
                *cursor = P::Finish as u32;
                if headers & 8 == 0 {
                    return effect(out, Effect::Length);
                }
            }
            P::Finish => {
                *cursor = P::Publish as u32;
                return append(out, b"\r\n");
            }
            P::Publish => {
                *cursor = P::Done as u32;
                return effect(out, Effect::Publish);
            }
            P::Done => return effect(out, Effect::Done),
        }
    }
}

/// Native codec selection before any allocation/backend call. Capabilities are
/// zlib/Brotli/Zstd bits; unsupported methods retain the native warning path.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_httpbindings_codec(
    method: i32,
    capabilities: u32,
    accepted: u32,
    length: usize,
    minimum: u32,
) -> i32 {
    if accepted == 0 || length < minimum as usize {
        return 0;
    }
    let required = match method {
        1 | 2 => 1,
        3 => 2,
        4 => 4,
        _ => return -1,
    };
    if capabilities & required != 0 {
        method
    } else {
        -1
    }
}

/// Preserve codec-specific native level policy. Zstd normalizes a captured local
/// level; Brotli/zlib native callers publish the result to their original field.
/// Brotli retains min-first and Zstd max-first order, with no clamp panic across C ABI.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_httpbindings_codec_level(
    method: i32,
    level: i32,
    minimum: i32,
    maximum: i32,
) -> i32 {
    match method {
        1 | 2 => match level {
            i32::MIN..=-1 => -1,
            0 => 1,
            value => value.min(9),
        },
        3 => {
            if level < minimum {
                minimum
            } else if level > maximum {
                maximum
            } else {
                level
            }
        }
        4 => {
            if level > maximum {
                maximum
            } else if level < minimum {
                minimum
            } else {
                level
            }
        }
        _ => level,
    }
}
