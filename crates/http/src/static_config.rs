//! Sole static-serving configuration storage. Native performs canonicalization,
//! warnings, allocation of scoped IO copies and filesystem effects after return.
use crate::proxy::HttpProxyText;
use crate::{INVALID, bytes};
use std::alloc::{Layout, alloc};

const ALLOCATION: i32 = -3;
const ROOT: u32 = 0;
const LOCATION: u32 = 1;
const INDEX: u32 = 2;
const INITIALIZE: u32 = 3;

#[derive(Default)]
pub struct HttpStaticConfig {
    root: Vec<u8>,
    // Preserve absent versus initialized empty configuration without Native
    // containers. Location iteration only accumulates a case-prefix match;
    // the selected typed interface exposes no unordered iteration ABI.
    locations: Option<Vec<Vec<u8>>>,
    indexes: Option<Vec<Vec<u8>>>,
}
impl HttpStaticConfig {
    fn insert(family: &mut Option<Vec<Vec<u8>>>, input: &[u8]) -> Result<(), i32> {
        let values = family.get_or_insert_with(Vec::new);
        if values.iter().any(|value| value == input) {
            return Ok(());
        }
        let mut value = Vec::new();
        if value.try_reserve_exact(input.len()).is_err() || values.try_reserve(1).is_err() {
            return Err(ALLOCATION);
        }
        value.extend_from_slice(input);
        values.push(value);
        Ok(())
    }
    fn apply(&mut self, operation: u32, input: &[u8]) -> Result<(), i32> {
        match operation {
            ROOT => {
                let mut replacement = Vec::new();
                replacement
                    .try_reserve_exact(input.len())
                    .map_err(|_| ALLOCATION)?;
                replacement.extend_from_slice(input);
                self.root = replacement;
                Ok(())
            }
            LOCATION => Self::insert(&mut self.locations, input),
            INDEX => Self::insert(&mut self.indexes, input),
            INITIALIZE => {
                self.locations.get_or_insert_with(Vec::new);
                Ok(())
            }
            _ => Err(INVALID),
        }
    }
}

/// Apply one complete canonical-root publication, unique location admission,
/// insertion-ordered unique index admission, or startup initialization. Lazy
/// owner creation and all bytes belong to Rust; no Native pointee is retained.
/// # Safety
/// Field is an aligned initialized optional owner, exclusively writable and
/// disjoint from initialized input. A live owner came from this function only.
/// ROOT input is the Native realpath result's initialized C prefix. No callback
/// or other Native effect can occur until this call returns.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_config_apply(
    field: *mut *mut HttpStaticConfig,
    operation: u32,
    input: *const HttpProxyText,
) -> i32 {
    let Some(field) = (unsafe { field.as_mut() }) else {
        return INVALID;
    };
    if operation > INITIALIZE {
        return INVALID;
    }
    let data = if operation == INITIALIZE {
        &[][..]
    } else {
        let Some(input) = (unsafe { input.as_ref() }) else {
            return INVALID;
        };
        match unsafe { bytes(input.data, input.length) } {
            Ok(data) => data,
            Err(error) => return error,
        }
    };
    if field.is_null() {
        let owner = unsafe { alloc(Layout::new::<HttpStaticConfig>()).cast::<HttpStaticConfig>() };
        if owner.is_null() {
            return ALLOCATION;
        }
        unsafe { owner.write(HttpStaticConfig::default()) };
        *field = owner;
    }
    match unsafe { &mut **field }.apply(operation, data) {
        Ok(()) => 0,
        Err(error) => error,
    }
}
/// # Safety
/// Null or unique live owner published by config_apply, destroyed exactly once.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_config_drop(owner: *mut HttpStaticConfig) {
    if !owner.is_null() {
        unsafe { drop(Box::from_raw(owner)) };
    }
}

/// Root-setting actions: begin0 checks the exact Native input length before
/// realpath; completion1 publishes the returned C prefix or requests the same
/// missing-directory warning. Native warnings/realpath execute after return.
/// # Safety
/// Field is valid as for config_apply. Optional canonical span is initialized
/// and disjoint; it is supplied only after Native realpath has completed.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_config_root_step(
    field: *mut *mut HttpStaticConfig,
    requested: usize,
    limit: usize,
    event: u32,
    canonical: *const HttpProxyText,
) -> i32 {
    if field.is_null() {
        return INVALID;
    }
    match event {
        0 => {
            if requested > limit {
                2
            } else {
                1
            }
        }
        1 if canonical.is_null() => 3,
        1 => unsafe { swr_v2_http_config_apply(field, ROOT, canonical) },
        _ => INVALID,
    }
}

/// Complete configured root/path/location operation, stopping only when the
/// existing path FSM requests a Native effect. Location traversal and index
/// enablement query the authoritative Rust owner; no Native per-name loop.
/// # Safety
/// Optional unchanged owner and initialized input; exclusive state/output follow
/// static_path's contract and are disjoint from all owner/input storage. Native
/// effects start after return; callers re-observe configuration at each call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_config_path(
    owner: *const HttpStaticConfig,
    url: *const HttpProxyText,
    output: *mut u8,
    capacity: usize,
    state: *mut crate::HttpStaticPath,
    facts: *mut u32,
) -> i32 {
    let Some(facts) = (unsafe { facts.as_mut() }) else {
        return INVALID;
    };
    if state.is_null() || output.is_null() {
        return INVALID;
    }
    if capacity > isize::MAX as usize {
        return crate::OVERFLOW;
    }
    let Some(url) = (unsafe { url.as_ref() }) else {
        return INVALID;
    };
    let url = match unsafe { bytes(url.data, url.length) } {
        Ok(url) => url,
        Err(error) => return error,
    };
    let state = unsafe { &mut *state };
    let empty = HttpStaticConfig::default();
    let owner = unsafe { owner.as_ref() }.unwrap_or(&empty);
    let locations = owner.locations.as_deref().unwrap_or(&[]);
    // The original Legacy method captures these two enablement bits once;
    // subsequent Native observations only replace filesystem fact bits.
    if state.phase == 0 {
        *facts &= !(crate::static_path::LOCATIONS | crate::static_path::INDEX);
        if !locations.is_empty() {
            *facts |= crate::static_path::LOCATIONS;
        }
        if owner
            .indexes
            .as_ref()
            .is_some_and(|names| !names.is_empty())
        {
            *facts |= crate::static_path::INDEX;
        }
    }
    loop {
        let action = unsafe {
            crate::static_path::path_step(url, &owner.root, output, capacity, state, *facts)
        };
        if action != 2 {
            return action;
        }
        for location in locations {
            if let Err(error) = crate::static_path::location_match(url, location, state) {
                return error;
            }
        }
    }
}

/// Complete original strict root-containment predicate; no root byte view or
/// persistent Native std::string is needed by the selected caller.
/// # Safety
/// Optional unchanged owner and initialized filename span, disjoint/live for the
/// complete call. No Native effect, allocation, callback or borrow survives it.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_config_contains(
    owner: *const HttpStaticConfig,
    filename: *const HttpProxyText,
) -> i32 {
    let Some(filename) = (unsafe { filename.as_ref() }) else {
        return INVALID;
    };
    let filename = match unsafe { bytes(filename.data, filename.length) } {
        Ok(value) => value,
        Err(error) => return error,
    };
    let root = unsafe { owner.as_ref() }.map_or(&[][..], |owner| owner.root.as_slice());
    i32::from(
        filename.len() > root.len()
            && filename[root.len()] == b'/'
            && crate::static_path::prefix(filename, root, false),
    )
}

/// First configured index present in a borrowed sorted Native directory-name
/// snapshot. Query/fill copy the chosen name only; no configuration pointer or
/// borrowed name escapes. The Legacy public directory/index stores remain
/// Native; this snapshot is scoped metadata, never another authoritative owner.
/// # Safety
/// Optional unchanged owner; directory is an initialized aligned sorted array
/// of initialized independent spans. Written/output are writable/disjoint from
/// each other and all inputs/owner; output may be uninitialized. Native effects
/// and output publication occur after return; no array/span is retained.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_config_select_index(
    owner: *const HttpStaticConfig,
    directory: *const HttpProxyText,
    count: usize,
    output: *mut u8,
    capacity: usize,
    written: *mut usize,
) -> i32 {
    if written.is_null() || (count != 0 && directory.is_null()) {
        return INVALID;
    }
    if count > isize::MAX as usize / std::mem::size_of::<HttpProxyText>()
        || capacity > isize::MAX as usize
    {
        return crate::OVERFLOW;
    }
    let names = if count == 0 {
        &[][..]
    } else {
        unsafe { std::slice::from_raw_parts(directory, count) }
    };
    for name in names {
        if let Err(error) = unsafe { bytes(name.data, name.length) } {
            return error;
        }
    }
    let indexes = unsafe { owner.as_ref() }
        .and_then(|owner| owner.indexes.as_deref())
        .unwrap_or(&[]);
    let selected = indexes
        .iter()
        .find(|index| {
            names
                .binary_search_by(|name| {
                    // Every span was validated above and remains unchanged for this call.
                    unsafe { bytes(name.data, name.length) }
                        .unwrap()
                        .cmp(index.as_slice())
                })
                .is_ok()
        })
        .map_or(&[][..], Vec::as_slice);
    unsafe { copy_selected_index(selected, output, capacity, written) }
}

// Both real Legacy paths copy only the selected configured name. The Native
// directory-span path and the sole Rust directory path keep separate inputs.
unsafe fn copy_selected_index(
    selected: &[u8],
    output: *mut u8,
    capacity: usize,
    written: *mut usize,
) -> i32 {
    if capacity != 0 {
        if capacity < selected.len() {
            return crate::OVERFLOW;
        }
        if output.is_null() {
            return INVALID;
        }
        if !selected.is_empty() {
            unsafe { std::ptr::copy_nonoverlapping(selected.as_ptr(), output, selected.len()) };
        }
    }
    unsafe { written.write(selected.len()) };
    0
}

/// First configured index in the sole finished Rust directory, without a Native
/// name-pointer snapshot. Only the selected name is copied into Native scratch.
/// # Safety
/// Optional unchanged config/directory owners; initialized writable written and
/// independent output backing for capacity bytes. No borrow survives return.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_config_directory_index(
    owner: *const HttpStaticConfig,
    directory: *const crate::HttpDirectory,
    output: *mut u8,
    capacity: usize,
    written: *mut usize,
) -> i32 {
    if written.is_null() {
        return INVALID;
    }
    if capacity > isize::MAX as usize {
        return crate::OVERFLOW;
    }
    let directory = unsafe { directory.as_ref() };
    let indexes = unsafe { owner.as_ref() }
        .and_then(|owner| owner.indexes.as_deref())
        .unwrap_or(&[]);
    let mut selected = &[][..];
    if let Some(directory) = directory {
        for index in indexes {
            match directory.contains(index) {
                Ok(true) => {
                    selected = index;
                    break;
                }
                Ok(false) => (),
                Err(error) => return error,
            }
        }
    }
    unsafe { copy_selected_index(selected, output, capacity, written) }
}

/// Coupled Legacy index admission preserves the original conditional directory
/// field read. Action5 requests that Native observation only when indexes exist;
/// the existing FSM then schedules scan/intersection/filename effects unchanged.
/// # Safety
/// Optional unchanged owner, initialized exclusive phase, disjoint Native fact
/// snapshot; no Native field or effect is accessed through Rust.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_config_legacy_index(
    config: *const HttpStaticConfig,
    phase: *mut u32,
    facts: u32,
) -> i32 {
    let Some(phase) = (unsafe { phase.as_mut() }) else {
        return INVALID;
    };
    if *phase == 0 {
        let has_index = unsafe { config.as_ref() }.is_some_and(|config| {
            config
                .indexes
                .as_ref()
                .is_some_and(|names| !names.is_empty())
        });
        if !has_index {
            return 1;
        }
        *phase = 4;
        return 5;
    }
    let facts = if *phase == 4 {
        *phase = 0;
        facts | 1
    } else {
        facts
    };
    unsafe { crate::swr_v1_http_index_file(phase, facts) }
}

/// Whole selected path/configuration operation: consume all location matches in
/// Rust and stop only for a real Native filesystem/MIME effect. No configured
/// root/name pointer is exposed or retained by Native.
/// # Safety
/// Optional unchanged configuration, unique live context, and initialized
/// observation follow context_serve's disjointness contract. Effects occur only
/// after return; configuration/context memory must not alias.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_config_serve(
    config: *const HttpStaticConfig,
    context: *mut crate::HttpStaticContext,
    observation: *const crate::HttpContextServeObservation,
) -> i32 {
    let Some(observation) = (unsafe { observation.as_ref() }) else {
        return INVALID;
    };
    let empty = HttpStaticConfig::default();
    let config = unsafe { config.as_ref() }.unwrap_or(&empty);
    let locations = config.locations.as_deref().unwrap_or(&[]);
    let root = HttpProxyText {
        data: config.root.as_ptr(),
        length: config.root.len(),
    };
    let mut observation = *observation;
    if observation.event == 0 {
        observation.has_locations = u32::from(!locations.is_empty());
        observation.has_index = u32::from(
            config
                .indexes
                .as_ref()
                .is_some_and(|names| !names.is_empty()),
        );
    }
    loop {
        let action = unsafe { crate::swr_v2_http_context_serve(context, &root, &observation) };
        if action != 2 {
            return action;
        }
        for location in locations {
            let result = unsafe {
                crate::swr_v2_http_context_path(context, 1, location.as_ptr(), location.len(), 0)
            };
            if result < 0 {
                return result;
            }
        }
        observation.event = 1;
    }
}

/// Whole selected index operation uses the actual Rust configuration/directory
/// owners directly. Candidate traversal never crosses Native. Directory scans,
/// filename/stat publication and autoindex observation remain requested actions.
/// # Safety
/// Optional unchanged config, unique context and writable cursor follow the
/// existing index contract, mutually disjoint. Native effects finish before
/// entry; no owner/name span or borrow survives return.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v2_http_config_index(
    config: *const HttpStaticConfig,
    context: *mut crate::HttpStaticContext,
    event: u32,
    value: usize,
    cursor: *mut usize,
) -> i32 {
    let indexes = unsafe { config.as_ref() }
        .and_then(|owner| owner.indexes.as_deref())
        .unwrap_or(&[]);
    let value = if event == 0 || event == 1 {
        indexes.len()
    } else {
        value
    };
    let mut action = unsafe {
        crate::swr_v2_http_context_index(context, event, value, std::ptr::null(), 0, cursor)
    };
    while action == 3 {
        let ordinal = unsafe { cursor.read() };
        let Some(name) = indexes.get(ordinal) else {
            return INVALID;
        };
        action = unsafe {
            crate::swr_v2_http_context_index(context, 2, 0, name.as_ptr(), name.len(), cursor)
        };
    }
    action
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn legacy_directory_selection_uses_two_real_owners() {
        unsafe {
            for indexes in [
                vec![b"missing".as_slice()],
                vec![b"z.txt".as_slice(), b"a.txt"],
                vec![b"a.txt".as_slice(), b"z.txt"],
                vec![b"".as_slice(), b"a.txt"],
            ] {
                let mut config = std::ptr::null_mut();
                for name in &indexes {
                    assert_eq!(
                        swr_v2_http_config_apply(&mut config, INDEX, &input(name)),
                        0
                    );
                }
                let directory = crate::swr_v2_http_directory_new();
                assert!(!directory.is_null());
                let names = [b"".as_slice(), b"a.txt".as_slice(), b"z.txt".as_slice()];
                for name in names.iter().rev() {
                    assert_eq!(
                        crate::swr_v2_http_directory_insert(directory, name.as_ptr(), name.len()),
                        1
                    );
                }
                let spans: Vec<_> = names.iter().map(|name| input(name)).collect();
                let expected = indexes
                    .iter()
                    .find(|name| names.contains(name))
                    .copied()
                    .unwrap_or_default();
                let mut previous = [0xa5; 32];
                let mut current = [0xa5; 32];
                let mut previous_count = 0;
                let mut current_count = 0;
                assert_eq!(
                    swr_v2_http_config_select_index(
                        config,
                        spans.as_ptr(),
                        spans.len(),
                        previous.as_mut_ptr(),
                        previous.len(),
                        &mut previous_count
                    ),
                    0
                );
                assert_eq!(
                    swr_v2_http_config_directory_index(
                        config,
                        directory,
                        current.as_mut_ptr(),
                        current.len(),
                        &mut current_count
                    ),
                    0
                );
                assert_eq!(previous_count, expected.len());
                assert_eq!(current_count, expected.len());
                assert_eq!(previous, current);
                assert_eq!(&current[..current_count], expected);
                assert!(current[current_count..].iter().all(|&byte| byte == 0xa5));
                crate::swr_v2_http_directory_drop(directory);
                swr_v2_http_config_drop(config);
            }
        }
    }
    use std::ptr;
    #[test]
    fn ordinary_config_owns_root_unique_binary_names_and_index_order() {
        let mut owner = HttpStaticConfig::default();
        assert!(owner.locations.is_none() && owner.indexes.is_none());
        owner.apply(INITIALIZE, &[]).unwrap();
        assert_eq!(owner.locations.as_deref(), Some(&[][..]));
        assert!(owner.indexes.is_none());
        let mut root = b"/canonical/root".to_vec();
        owner.apply(ROOT, &root).unwrap();
        root.fill(b'x');
        assert_eq!(owner.root, b"/canonical/root");
        for name in [b"/DOCS".as_slice(), b"/docs", b"", b"/a\0b", b"/docs"] {
            owner.apply(LOCATION, name).unwrap();
        }
        assert_eq!(owner.locations.as_ref().unwrap().len(), 4);
        for name in [
            b"index.html".as_slice(),
            b"a\0b",
            b"",
            b"index.php",
            b"index.html",
        ] {
            owner.apply(INDEX, name).unwrap();
        }
        assert_eq!(
            owner.indexes.as_ref().unwrap(),
            &[
                b"index.html".to_vec(),
                b"a\0b".to_vec(),
                Vec::new(),
                b"index.php".to_vec()
            ]
        );
        owner.apply(ROOT, b"/new").unwrap();
        assert_eq!(owner.root, b"/new");
        assert_eq!(owner.indexes.as_ref().unwrap().len(), 4);
    }
    #[test]
    fn ordinary_c_entry_is_lazy_and_owns_independent_input() {
        let mut owner = ptr::null_mut();
        let mut name = b"index.html".to_vec();
        let input = HttpProxyText {
            data: name.as_ptr(),
            length: name.len(),
        };
        assert_eq!(
            unsafe { swr_v2_http_config_apply(&mut owner, INDEX, &input) },
            0
        );
        name.fill(b'x');
        assert_eq!(
            unsafe { &*owner }.indexes.as_ref().unwrap()[0],
            b"index.html"
        );
        assert_eq!(
            unsafe { swr_v2_http_config_apply(&mut owner, INITIALIZE, ptr::null()) },
            0
        );
        assert_eq!(unsafe { &*owner }.locations.as_deref(), Some(&[][..]));
        unsafe { swr_v2_http_config_drop(owner) };
    }
    fn input(bytes: &[u8]) -> HttpProxyText {
        HttpProxyText {
            data: bytes.as_ptr(),
            length: bytes.len(),
        }
    }
    #[test]
    fn ordinary_coupled_path_and_index_operations_consume_owned_config() {
        let mut config = HttpStaticConfig::default();
        config.apply(ROOT, b"/root").unwrap();
        config.apply(LOCATION, b"/DOCS").unwrap();
        config.apply(INDEX, b"index.php").unwrap();
        config.apply(INDEX, b"index.html").unwrap();
        let url = input(b"/docs/a?version=1");
        let mut filename = [0xa5; 128];
        let mut state = crate::HttpStaticPath::default();
        let mut facts = 0;
        assert_eq!(
            unsafe {
                swr_v2_http_config_path(
                    &config,
                    &url,
                    filename.as_mut_ptr(),
                    filename.len(),
                    &mut state,
                    &mut facts,
                )
            },
            3
        );
        assert_eq!(&filename[..13], b"/root/docs/a\0");
        assert_eq!(state.last, 1);
        // Ordinary successful Native observations resume the same owned path:
        // publish/URL decode, successful regular-file metadata, then MIME.
        for (observed, expected) in [(0, 4), (34, 6), (290, 1)] {
            facts =
                (facts & (crate::static_path::LOCATIONS | crate::static_path::INDEX)) | observed;
            assert_eq!(
                unsafe {
                    swr_v2_http_config_path(
                        &config,
                        &url,
                        filename.as_mut_ptr(),
                        filename.len(),
                        &mut state,
                        &mut facts,
                    )
                },
                expected
            );
        }
        assert_eq!(&filename[..13], b"/root/docs/a\0");
        assert_eq!(
            unsafe { swr_v2_http_config_contains(&config, &input(b"/root/docs/a")) },
            1
        );
        assert_eq!(
            unsafe { swr_v2_http_config_contains(&config, &input(b"/roots/a")) },
            0
        );
        let directory = [
            input(b"."),
            input(b".."),
            input(b"index.html"),
            input(b"index.php"),
        ];
        let mut written = 0;
        assert_eq!(
            unsafe {
                swr_v2_http_config_select_index(
                    &config,
                    directory.as_ptr(),
                    directory.len(),
                    filename.as_mut_ptr(),
                    filename.len(),
                    &mut written,
                )
            },
            0
        );
        assert_eq!(&filename[..written], b"index.php");

        let context = unsafe { crate::swr_v2_http_context_new(url.data, url.length, 128) };
        assert!(!context.is_null());
        let observed = crate::HttpContextServeObservation {
            event: 0,
            observed: 0,
            has_locations: 0,
            has_index: 0,
            autoindex: 0,
            value: input(&[]),
        };
        assert_eq!(
            unsafe { swr_v2_http_config_serve(&config, context, &observed) },
            4
        );
        let metadata = crate::HttpStaticObservation {
            kind: 16,
            ..Default::default()
        };
        assert_eq!(
            unsafe { crate::swr_v2_http_context_observed(context, 0, &metadata) },
            0
        );
        let mut cursor = 0;
        assert_eq!(
            unsafe { swr_v2_http_config_index(&config, context, 0, 0, &mut cursor) },
            2
        );
        assert_eq!(
            unsafe { crate::swr_v2_http_context_scan(context, 0, ptr::null(), 0) },
            2
        );
        assert_eq!(
            unsafe { crate::swr_v2_http_context_scan(context, 1, ptr::null(), 0) },
            3
        );
        for name in [b"index.html".as_slice(), b"index.php"] {
            assert_eq!(
                unsafe { crate::swr_v2_http_context_scan(context, 3, name.as_ptr(), name.len()) },
                3
            );
        }
        assert_eq!(
            unsafe { crate::swr_v2_http_context_scan(context, 4, ptr::null(), 0) },
            4
        );
        assert_eq!(
            unsafe { crate::swr_v2_http_context_scan(context, 5, ptr::null(), 0) },
            1
        );
        assert_eq!(
            unsafe { swr_v2_http_config_index(&config, context, 1, 0, &mut cursor) },
            4
        );
        assert_eq!(
            unsafe {
                crate::swr_v2_http_context_text(
                    context,
                    3,
                    filename.as_mut_ptr(),
                    filename.len(),
                    &mut written,
                )
            },
            0
        );
        assert_eq!(&filename[..written], b"index.php");
        unsafe { crate::swr_v2_http_context_drop(context) };
    }
}
