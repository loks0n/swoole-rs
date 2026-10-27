//! PHP async Client callback classification/metadata and native-effect sequencing.
//! All mutable callback slots/objects stay native; static names are not a registry.
#[repr(C)]
pub struct ClientsAsyncMeta {
    pub slot: u32,
    pub name: *const u8,
    pub length: usize,
}
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_clients_async_meta(slot: u32) -> ClientsAsyncMeta {
    let name: &[u8] = match slot {
        1 => b"onConnect\0",
        2 => b"onReceive\0",
        3 => b"onClose\0",
        4 => b"onError\0",
        5 => b"onBufferFull\0",
        6 => b"onBufferEmpty\0",
        7 => b"onSSLReady\0",
        _ => {
            return ClientsAsyncMeta {
                slot: 0,
                name: std::ptr::null(),
                length: 0,
            };
        }
    };
    ClientsAsyncMeta {
        slot,
        name: name.as_ptr(),
        length: name.len() - 1,
    }
}
/// # Safety
/// Folded is an initialized native C-locale lowercase prefix of min(length,12)
/// bytes; original_length is the original PHP string size. No borrow survives.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_clients_async_event(
    folded: *const u8,
    length: usize,
    original_length: usize,
) -> u32 {
    if length != original_length.min(12) || (length != 0 && folded.is_null()) {
        return 0;
    }
    let bytes = if length == 0 {
        &[][..]
    } else {
        // SAFETY: `folded` is non-null and `length <= 12` (checked above); the caller lends those bytes.
        unsafe { std::slice::from_raw_parts(folded, length) }
    };
    // Native strncasecmp's n is the supplied name length: abbreviations and the
    // empty name select the first matching event; matching NUL ignores the tail.
    for (index, name) in [
        b"connect\0".as_slice(),
        b"receive\0",
        b"close\0",
        b"error\0",
        b"bufferfull\0",
        b"bufferempty\0",
    ]
    .iter()
    .enumerate()
    {
        let count = original_length.min(name.len());
        if bytes.get(..count) == Some(&name[..count]) {
            return u32::try_from(index).map_or(0, |index| index + 1);
        }
    }
    0
}
#[repr(C)]
pub struct ClientsAsyncPlan {
    pub action: u32,
    pub stage: u32,
}
/// Operation0 native callback freeing order;1 connect/SSL callback choice;
///2 PHP async connect/publication/error cleanup. Copied stage-local facts only.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_clients_async_next(
    operation: u32,
    stage: u32,
    facts: u32,
) -> ClientsAsyncPlan {
    let (action, stage) = match (operation, stage) {
        (0, 1..=7) => (u32::from(facts != 0), stage + 1),
        (0, _) => (2, 0), // delete native callback container after all frees
        (1, _) => (if facts != 0 { 4 } else { 3 }, 0),
        (2, 0) if facts == 0 => (32, 0),
        (2, 0) => (0, 1),
        (2, 1) if facts != 0 => (33, 0),
        (2, 1) => (0, 2),
        (2, 2) if facts != 0 => (34, 3),
        (2, 2) => (35, 0),
        (2, 3) if facts != 0 => (36, 4),
        (2, 3) => (6, 0),
        (2, 4) if facts != 0 => (37, 5),
        (2, 4) => (0, 5),
        (2, 5) if facts != 0 => (38, 6),
        (2, 5) => (39, 0),
        (2, 6) => (0, if facts != 0 { 7 } else { 20 }),
        (2, 7) if facts != 0 => (0, 8),
        (2, 7) => (40, 0),
        (2, 8) if facts != 0 => (0, 9),
        (2, 8) => (41, 0),
        (2, 9) if facts != 0 => (42, 10),
        (2, 9) => (43, 0),
        (2, 10) => (if facts != 0 { 44 } else { 0 }, 11),
        (2, 11) => (if facts != 0 { 45 } else { 0 }, 30),
        (2, 20) => (if facts != 0 { 46 } else { 0 }, 21),
        (2, 21) => (if facts != 0 { 47 } else { 0 }, 22),
        (2, 22) => (if facts != 0 { 48 } else { 0 }, 23),
        (2, 23) => (49, 30),
        (2, 30) => (50, 31),
        (2, 31) => (51, 32),
        (2, 32) if facts != 0 => (0, 33),
        (2, 32) => (5, 0),
        (2, 33) if facts != 0 => (52, 34),
        (2, 33) => (53, 35),
        (2, 34) => (if facts != 0 { 54 } else { 0 }, 36),
        (2, 36) => (55, 35),
        (2, 35) => (56, 37),
        (2, 37) if facts != 0 => (57, 38),
        (2, 37 | 38) => (6, 0),
        _ => (6, 0),
    };
    ClientsAsyncPlan { action, stage }
}
