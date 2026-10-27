//! Ordered coroutine HTTP startup settings; native code owns all Zend effects.
use crate::{Action, Text};

#[repr(C)]
#[derive(Default)]
pub struct SettingsCursor {
    pub entry: u32,
    pub alias: u32,
    pub stage: u32,
}
struct Setting {
    keys: &'static [&'static [u8]],
    effect: u32,
    compression: bool,
}
const SETTINGS: [Setting; 9] = [
    Setting {
        keys: &[b"http_parse_cookie"],
        effect: 2,
        compression: false,
    },
    Setting {
        keys: &[b"http_parse_post"],
        effect: 3,
        compression: false,
    },
    Setting {
        keys: &[b"http_parse_files"],
        effect: 4,
        compression: false,
    },
    Setting {
        keys: &[b"http_compression"],
        effect: 5,
        compression: true,
    },
    Setting {
        keys: &[
            b"http_compression_level",
            b"compression_level",
            b"http_gzip_level",
        ],
        effect: 6,
        compression: true,
    },
    Setting {
        keys: &[b"http_compression_min_length", b"compression_min_length"],
        effect: 7,
        compression: true,
    },
    Setting {
        keys: &[b"http_compression_types", b"compression_types"],
        effect: 8,
        compression: true,
    },
    Setting {
        keys: &[],
        effect: 9,
        compression: false,
    },
    Setting {
        keys: &[b"upload_tmp_dir"],
        effect: 10,
        compression: false,
    },
];
fn advance(cursor: &mut SettingsCursor) {
    cursor.entry += 1;
    cursor.alias = 0;
    cursor.stage = 0;
}

/// Emit one native lookup/effect. Native lookup treats null values as absent,
/// preserving original short-circuit aliases and fresh conversion/reentry order.
/// # Safety
/// Cursor/action are initialized, disjoint writable objects for this call only.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_httpbindings_settings(
    cursor: *mut SettingsCursor,
    compression: u32,
    found: u32,
    out: *mut Action,
) -> i32 {
    // SAFETY: `cursor` is null or aligned, writable and exclusively lent for this call.
    let cursor = unsafe { cursor.as_mut() };
    // SAFETY: `out` is null or aligned, writable and exclusively lent for this call.
    let out = unsafe { out.as_mut() };
    let (Some(cursor), Some(out)) = (cursor, out) else {
        return -1;
    };
    *out = Action::default();
    if cursor.stage > 1
        || cursor.entry > u32::try_from(SETTINGS.len()).unwrap_or(u32::MAX)
        || (cursor.stage == 0 && cursor.alias != 0)
    {
        return -1;
    }
    if let Some(setting) = SETTINGS.get(cursor.entry as usize) {
        if cursor.stage == 1 && cursor.alias as usize >= setting.keys.len() {
            return -1;
        }
    } else if cursor.stage != 0 {
        return -1;
    }
    loop {
        let Some(setting) = SETTINGS.get(cursor.entry as usize) else {
            out.kind = 11;
            return 0;
        };
        if setting.compression && compression == 0 {
            advance(cursor);
            continue;
        }
        if setting.keys.is_empty() {
            out.kind = setting.effect;
            advance(cursor);
            return 0;
        }
        if cursor.stage == 1 {
            if cursor.alias as usize >= setting.keys.len() {
                return -1;
            }
            if found != 0 {
                out.kind = setting.effect;
                advance(cursor);
                return 0;
            }
            cursor.alias += 1;
            cursor.stage = 0;
        }
        let Some(key) = setting.keys.get(cursor.alias as usize) else {
            advance(cursor);
            continue;
        };
        out.kind = 1;
        out.text = Text {
            data: key.as_ptr(),
            length: key.len(),
        };
        cursor.stage = 1;
        return 0;
    }
}

/// Zend conversion remains native; preserve the original unsigned-byte clamp.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_httpbindings_server_level(level: i64) -> u32 {
    u8::try_from(level.clamp(0, 255)).map_or(0, u32::from)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn malformed_cursors_do_not_request_a_native_effect() {
        for mut cursor in [
            SettingsCursor {
                entry: u32::MAX,
                alias: 0,
                stage: 0,
            },
            SettingsCursor {
                entry: 0,
                alias: u32::MAX,
                stage: 1,
            },
            SettingsCursor {
                entry: 0,
                alias: 1,
                stage: 0,
            },
            SettingsCursor {
                entry: 7,
                alias: 0,
                stage: 1,
            },
            SettingsCursor {
                entry: 9,
                alias: 0,
                stage: 1,
            },
        ] {
            let mut action = Action::default();
            assert_eq!(
                unsafe { swr_v1_httpbindings_settings(&raw mut cursor, 1, 0, &raw mut action) },
                -1
            );
            assert_eq!(action.kind, 0);
        }
    }
}
