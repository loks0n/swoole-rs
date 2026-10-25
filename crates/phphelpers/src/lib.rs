//! Common PHP helper policy. Zend storage, calls, allocation and VM effects stay native.
use std::ffi::c_char;
mod asynchronous;
mod facade;
mod known_strings;
mod registration;

/// Empty string/array predicate over a count observed by the native Zend shim.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_phphelpers_empty(count: usize) -> u8 {
    u8::from(count == 0)
}

fn alias(family: u32, name: &[u8]) -> Option<&'static [u8]> {
    match (family, name) {
        (0, b"all") => Some(b"array_all\0"),
        (0, b"any") => Some(b"array_any\0"),
        (0, b"changeKeyCase") => Some(b"array_change_key_case\0"),
        (0, b"chunk") => Some(b"array_chunk\0"),
        (0, b"column") => Some(b"array_column\0"),
        (0, b"countValues") => Some(b"array_count_values\0"),
        (0, b"diff") => Some(b"array_diff\0"),
        (0, b"diffAssoc") => Some(b"array_diff_assoc\0"),
        (0, b"diffKey") => Some(b"array_diff_key\0"),
        (0, b"filter") => Some(b"array_filter\0"),
        (0, b"find") => Some(b"array_find\0"),
        (0, b"flip") => Some(b"array_flip\0"),
        (0, b"intersect") => Some(b"array_intersect\0"),
        (0, b"intersectAssoc") => Some(b"array_intersect_assoc\0"),
        (0, b"isList") => Some(b"array_is_list\0"),
        (0, b"keyExists") => Some(b"swoole_array_key_exists\0"),
        (0, b"keyFirst") => Some(b"array_key_first\0"),
        (0, b"keyLast") => Some(b"array_key_last\0"),
        (0, b"keys") => Some(b"array_keys\0"),
        (0, b"map") => Some(b"swoole_array_map\0"),
        (0, b"pad") => Some(b"array_pad\0"),
        (0, b"product") => Some(b"array_product\0"),
        (0, b"rand") => Some(b"array_rand\0"),
        (0, b"reduce") => Some(b"array_reduce\0"),
        (0, b"replace") => Some(b"array_replace\0"),
        (0, b"reverse") => Some(b"array_reverse\0"),
        (0, b"search") => Some(b"swoole_array_search\0"),
        (0, b"slice") => Some(b"array_slice\0"),
        (0, b"sum") => Some(b"array_sum\0"),
        (0, b"unique") => Some(b"array_unique\0"),
        (0, b"values") => Some(b"array_values\0"),
        (0, b"count") => Some(b"count\0"),
        (0, b"merge") => Some(b"array_merge\0"),
        (0, b"contains") => Some(b"swoole_array_contains\0"),
        (0, b"join") => Some(b"swoole_array_join\0"),
        (0, b"isTyped") => Some(b"swoole_array_is_typed\0"),
        (0, b"isEmpty") => Some(b"swoole_array_is_empty\0"),
        (0, b"sort") => Some(b"sort\0"),
        (0, b"pop") => Some(b"array_pop\0"),
        (0, b"push") => Some(b"array_push\0"),
        (0, b"shift") => Some(b"array_shift\0"),
        (0, b"unshift") => Some(b"array_unshift\0"),
        (0, b"splice") => Some(b"array_splice\0"),
        (0, b"walk") => Some(b"array_walk\0"),
        (0, b"replaceStr") => Some(b"swoole_array_replace_str\0"),
        (0, b"iReplaceStr") => Some(b"swoole_array_ireplace_str\0"),
        (0, b"serialize") => Some(b"serialize\0"),
        (0, b"marshal") => Some(b"serialize\0"),
        (0, b"jsonEncode") => Some(b"json_encode\0"),
        (1, b"length") => Some(b"strlen\0"),
        (1, b"isEmpty") => Some(b"swoole_str_is_empty\0"),
        (1, b"lower") => Some(b"strtolower\0"),
        (1, b"upper") => Some(b"strtoupper\0"),
        (1, b"lowerFirst") => Some(b"lcfirst\0"),
        (1, b"upperFirst") => Some(b"ucfirst\0"),
        (1, b"upperWords") => Some(b"ucwords\0"),
        (1, b"addCSlashes") => Some(b"addcslashes\0"),
        (1, b"addSlashes") => Some(b"addslashes\0"),
        (1, b"chunkSplit") => Some(b"chunk_split\0"),
        (1, b"countChars") => Some(b"count_chars\0"),
        (1, b"htmlEntityDecode") => Some(b"html_entity_decode\0"),
        (1, b"htmlEntityEncode") => Some(b"htmlentities\0"),
        (1, b"htmlSpecialCharsEncode") => Some(b"htmlspecialchars\0"),
        (1, b"htmlSpecialCharsDecode") => Some(b"htmlspecialchars_decode\0"),
        (1, b"trim") => Some(b"trim\0"),
        (1, b"lTrim") => Some(b"ltrim\0"),
        (1, b"rTrim") => Some(b"rtrim\0"),
        (1, b"parseStr") => Some(b"swoole_parse_str\0"),
        (1, b"parseUrl") => Some(b"parse_url\0"),
        (1, b"contains") => Some(b"str_contains\0"),
        (1, b"incr") => Some(b"str_increment\0"),
        (1, b"decr") => Some(b"str_decrement\0"),
        (1, b"pad") => Some(b"str_pad\0"),
        (1, b"repeat") => Some(b"str_repeat\0"),
        (1, b"replace") => Some(b"swoole_str_replace\0"),
        (1, b"iReplace") => Some(b"swoole_str_ireplace\0"),
        (1, b"shuffle") => Some(b"str_shuffle\0"),
        (1, b"split") => Some(b"swoole_str_split\0"),
        (1, b"startsWith") => Some(b"str_starts_with\0"),
        (1, b"endsWith") => Some(b"str_ends_with\0"),
        (1, b"wordCount") => Some(b"str_word_count\0"),
        (1, b"iCompare") => Some(b"strcasecmp\0"),
        (1, b"compare") => Some(b"strcmp\0"),
        (1, b"find") => Some(b"strstr\0"),
        (1, b"iFind") => Some(b"stristr\0"),
        (1, b"stripTags") => Some(b"strip_tags\0"),
        (1, b"stripCSlashes") => Some(b"stripcslashes\0"),
        (1, b"stripSlashes") => Some(b"stripslashes\0"),
        (1, b"iIndexOf") => Some(b"stripos\0"),
        (1, b"indexOf") => Some(b"strpos\0"),
        (1, b"lastIndexOf") => Some(b"strrpos\0"),
        (1, b"iLastIndexOf") => Some(b"strripos\0"),
        (1, b"lastCharIndexOf") => Some(b"strrchr\0"),
        (1, b"substr") => Some(b"substr\0"),
        (1, b"substrCompare") => Some(b"substr_compare\0"),
        (1, b"substrCount") => Some(b"substr_count\0"),
        (1, b"substrReplace") => Some(b"substr_replace\0"),
        (1, b"reverse") => Some(b"strrev\0"),
        (1, b"md5") => Some(b"md5\0"),
        (1, b"sha1") => Some(b"sha1\0"),
        (1, b"crc32") => Some(b"crc32\0"),
        (1, b"hash") => Some(b"swoole_hash\0"),
        (1, b"hashCode") => Some(b"swoole_hashcode\0"),
        (1, b"base64Decode") => Some(b"base64_decode\0"),
        (1, b"base64Encode") => Some(b"base64_encode\0"),
        (1, b"urlDecode") => Some(b"urldecode\0"),
        (1, b"urlEncode") => Some(b"urlencode\0"),
        (1, b"rawUrlEncode") => Some(b"rawurlencode\0"),
        (1, b"rawUrlDecode") => Some(b"rawurldecode\0"),
        (1, b"match") => Some(b"swoole_str_match\0"),
        (1, b"matchAll") => Some(b"swoole_str_match_all\0"),
        (1, b"isNumeric") => Some(b"is_numeric\0"),
        (1, b"mbUpperFirst") => Some(b"mb_ucfirst\0"),
        (1, b"mbLowerFirst") => Some(b"mb_lcfirst\0"),
        (1, b"mbTrim") => Some(b"mb_trim\0"),
        (1, b"mbSubstrCount") => Some(b"mb_substr_count\0"),
        (1, b"mbSubstr") => Some(b"mb_substr\0"),
        (1, b"mbUpper") => Some(b"mb_strtoupper\0"),
        (1, b"mbLower") => Some(b"mb_strtolower\0"),
        (1, b"mbFind") => Some(b"mb_strstr\0"),
        (1, b"mbIndexOf") => Some(b"mb_strpos\0"),
        (1, b"mbLastIndexOf") => Some(b"mb_strrpos\0"),
        (1, b"mbILastIndexOf") => Some(b"mb_strripos\0"),
        (1, b"mbLastCharIndexOf") => Some(b"mb_strrchr\0"),
        (1, b"mbILastCharIndex") => Some(b"mb_strrichr\0"),
        (1, b"mbLength") => Some(b"mb_strlen\0"),
        (1, b"mbIFind") => Some(b"mb_stristr\0"),
        (1, b"mbIIndexOf") => Some(b"mb_stripos\0"),
        (1, b"mbCut") => Some(b"mb_strcut\0"),
        (1, b"mbRTrim") => Some(b"mb_rtrim\0"),
        (1, b"mbLTrim") => Some(b"mb_ltrim\0"),
        (1, b"mbDetectEncoding") => Some(b"mb_detect_encoding\0"),
        (1, b"mbConvertEncoding") => Some(b"mb_convert_encoding\0"),
        (1, b"mbConvertCase") => Some(b"mb_convert_case\0"),
        (1, b"unserialize") => Some(b"unserialize\0"),
        (1, b"unmarshal") => Some(b"unserialize\0"),
        (1, b"jsonDecode") => Some(b"swoole_str_json_decode\0"),
        (1, b"jsonDecodeToObject") => Some(b"swoole_str_json_decode_to_object\0"),
        (2, b"write") => Some(b"fwrite\0"),
        (2, b"read") => Some(b"fread\0"),
        (2, b"close") => Some(b"fclose\0"),
        (2, b"dataSync") => Some(b"fdatasync\0"),
        (2, b"sync") => Some(b"fsync\0"),
        (2, b"truncate") => Some(b"ftruncate\0"),
        (2, b"stat") => Some(b"fstat\0"),
        (2, b"seek") => Some(b"fseek\0"),
        (2, b"tell") => Some(b"ftell\0"),
        (2, b"lock") => Some(b"flock\0"),
        (2, b"eof") => Some(b"feof\0"),
        (2, b"getChar") => Some(b"fgetc\0"),
        (2, b"getLine") => Some(b"fgets\0"),
        _ => None,
    }
}

/// # Safety
/// Name is initialized for length bytes; output points to an independent usize.
/// Null name is permitted only for length0. Returned bytes have static lifetime.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phphelpers_alias(
    family: u32,
    name: *const u8,
    length: usize,
    output: *mut usize,
) -> *const c_char {
    if output.is_null() {
        return std::ptr::null();
    }
    unsafe {
        *output = 0;
    }
    if length > isize::MAX as usize || (length != 0 && name.is_null()) {
        return std::ptr::null();
    }
    let name = if length == 0 {
        &[]
    } else {
        unsafe { std::slice::from_raw_parts(name, length) }
    };
    match alias(family, name) {
        Some(value) => {
            unsafe {
                *output = value.len() - 1;
            }
            value.as_ptr().cast()
        }
        None => std::ptr::null(),
    }
}

#[repr(C)]
#[derive(Debug, Default, PartialEq, Eq)]
pub struct ArgumentPlan {
    pub head: u32,
    pub tail_begin: u32,
    pub tail_count: u32,
}

/// # Safety
/// Output is aligned writable storage; initialized only for a valid permutation.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phphelpers_arguments(
    count: i32,
    position: i32,
    output: *mut ArgumentPlan,
) -> u8 {
    if position < 0 || count <= position || output.is_null() {
        return 0;
    }
    unsafe {
        *output = ArgumentPlan {
            head: position as u32,
            tail_begin: (position + 1) as u32,
            tail_count: (count - position - 1) as u32,
        };
    }
    1
}

/// # Safety
/// Phase is native-owned aligned storage initialized to0; facts refreshed after effects.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phphelpers_merge(
    phase: *mut u32,
    inserted: u8,
    existing_array: u8,
) -> u32 {
    let Some(phase) = (unsafe { phase.as_mut() }) else {
        return 0;
    };
    merge_action(phase, inserted, existing_array)
}

fn merge_action(phase: &mut u32, inserted: u8, existing_array: u8) -> u32 {
    let (action, next) = match *phase {
        0 => (1, 1),
        1 if inserted != 0 => (0, 3),
        1 => (2, 2),
        2 => (if existing_array != 0 { 3 } else { 4 }, 3),
        _ => (0, 3),
    };
    *phase = next;
    action
}

/// Keyed variant of the frozen merge lifecycle. Numeric-key classification stays
/// native; Rust selects concrete HashTable effects without an extra dispatch.
/// # Safety
/// Same phase storage/lazy observation requirements as `swr_v1_phphelpers_merge`.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phphelpers_merge_keyed(
    phase: *mut u32,
    inserted: u8,
    existing_array: u8,
    numeric_key: u8,
) -> u32 {
    let Some(phase) = (unsafe { phase.as_mut() }) else {
        return 0;
    };
    match merge_action(phase, inserted, existing_array) {
        1 => {
            if numeric_key != 0 {
                1
            } else {
                2
            }
        }
        2 => {
            if numeric_key != 0 {
                3
            } else {
                4
            }
        }
        3 => 5,
        4 => {
            if numeric_key != 0 {
                6
            } else {
                7
            }
        }
        _ => 0,
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_phphelpers_call_success(result: i64, coroutine: u8) -> u8 {
    call_success(result, coroutine)
}

fn call_success(result: i64, coroutine: u8) -> u8 {
    u8::from(if coroutine != 0 {
        result >= 0
    } else {
        result == 0
    })
}

#[repr(u32)]
enum CallAction {
    Null = 0,
    Direct = 1,
    Coroutine = 2,
    Named = 3,
    ReleaseName = 4,
    ObserveException = 5,
    Fatal = 6,
    True = 7,
    False = 8,
    Variable = 9,
}

/// # Safety
/// Phase is aligned native-owned storage initialized to0. Mode is direct0,
/// coroutine1 or named2. Result and exception are fresh observations, consumed
/// only after their native call/effect; no engine pointer crosses this interface.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phphelpers_call_plan(
    phase: *mut u32,
    mode: u32,
    has_retval: u8,
    result: i64,
    exception: u8,
) -> u32 {
    use CallAction::*;
    let Some(phase) = (unsafe { phase.as_mut() }) else {
        return False as u32;
    };
    let invoke = match mode {
        0 => Direct,
        1 => Coroutine,
        _ => Named,
    };
    let (action, next) = match *phase {
        0 if mode == 1 && has_retval != 0 => (Null, 1),
        0 | 1 => (invoke, 2),
        2 if mode == 2 && result != 0 => (Null, 3),
        2 if mode == 2 => (ReleaseName, 4),
        2 | 4 => (ObserveException, 5),
        3 => (ReleaseName, 4),
        5 if exception != 0 => (Fatal, 6),
        _ if mode == 2 => (Variable, 6),
        _ if call_success(result, u8::from(mode == 1)) != 0 => (True, 6),
        _ => (False, 6),
    };
    *phase = next;
    action as u32
}

/// # Safety
/// Phase is native-owned aligned storage initialized to0, no retained pointer.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phphelpers_callable(phase: *mut u32, truthy: u8, valid: u8) -> u32 {
    let Some(phase) = (unsafe { phase.as_mut() }) else {
        return 0;
    };
    let (action, next) = match *phase {
        0 => (1, 1),
        1 if truthy == 0 => (3, 3),
        1 => (2, 2),
        2 => (if valid != 0 { 5 } else { 4 }, 3),
        _ => (0, 3),
    };
    *phase = next;
    action
}

/// # Safety
/// Phase is aligned native-owned storage initialized to0. Observation is fresh
/// value-defined/name-present fact, with no borrowed Zend pointer retained.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phphelpers_release(phase: *mut u32, observation: u8) -> u32 {
    let Some(phase) = (unsafe { phase.as_mut() }) else {
        return 0;
    };
    let (action, next) = match *phase {
        0 => (1, 1),
        1 if observation != 0 => (2, 2),
        1 | 2 => (3, 3),
        3 if observation != 0 => (4, 4),
        _ => (0, 4),
    };
    *phase = next;
    action
}

const UNDEF: u32 = 0;
const NULL: u32 = 1;
const BOOL: u32 = 2;
const LONG: u32 = 3;
const ARRAY: u32 = 6;
const OBJECT: u32 = 7;

/// Choose whether native key/count observations are needed before classification.
/// Existing key ABI and result codes stay unchanged;4 requests the lazy facts.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_phphelpers_key_route(expected: u32, actual: u32) -> u32 {
    if expected == UNDEF && actual == LONG {
        4
    } else {
        key_action(expected, actual, 0, 0)
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_phphelpers_key(expected: u32, actual: u32, key: i64, count: u32) -> u32 {
    key_action(expected, actual, key, count)
}

fn key_action(expected: u32, actual: u32, key: i64, count: u32) -> u32 {
    if expected != UNDEF {
        return if actual == expected { 0 } else { 1 };
    }
    if actual == LONG {
        return if key > i64::from(count) { 2 } else { 0 };
    }
    if actual == UNDEF || actual == NULL {
        0
    } else {
        3
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_phphelpers_value(expected: u32, actual: u32) -> u32 {
    value_action(expected, actual)
}

fn value_action(expected: u32, actual: u32) -> u32 {
    match (expected, actual) {
        (BOOL, BOOL) => 0,
        (a, b) if a != b => 1,
        (OBJECT, OBJECT) => 2,
        (ARRAY, ARRAY) => 3,
        _ => 0,
    }
}

/// # Safety
/// Inputs are initialized readable metadata spans of the supplied lengths.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phphelpers_type_equal(
    key_a: u32,
    value_a: u32,
    key_b: u32,
    value_b: u32,
    a: *const u8,
    a_len: usize,
    b: *const u8,
    b_len: usize,
) -> u8 {
    if key_a != key_b || value_a != value_b || a_len != b_len {
        return 0;
    }
    if a_len == 0 {
        return 1;
    }
    if a_len > isize::MAX as usize || a.is_null() || b.is_null() {
        return 0;
    }
    u8::from(unsafe {
        std::slice::from_raw_parts(a, a_len) == std::slice::from_raw_parts(b, b_len)
    })
}

unsafe extern "C" {
    fn isspace(value: i32) -> i32;
    fn strncasecmp(a: *const c_char, b: *const c_char, length: usize) -> i32;
}

fn kind(value: &[u8]) -> u32 {
    let equal = |literal: &[u8]| {
        value.len() == literal.len()
            && unsafe {
                strncasecmp(value.as_ptr().cast(), literal.as_ptr().cast(), value.len()) == 0
            }
    };
    if equal(b"int") {
        LONG
    } else if equal(b"float") {
        4
    } else if equal(b"string") {
        5
    } else if equal(b"bool") {
        BOOL
    } else if value.first() == Some(&b'<') && value.last() == Some(&b'>') {
        ARRAY
    } else if equal(b"resource") {
        8
    } else if equal(b"null") {
        NULL
    } else {
        OBJECT
    }
}

/// # Safety
/// Data is writable initialized native storage of length bytes, independent of
/// metadata. libc ctype takes unsigned byte values, matching the native caller.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phphelpers_compact(data: *mut u8, length: usize) -> usize {
    if length == 0 || data.is_null() || length > isize::MAX as usize {
        return 0;
    }
    let bytes = unsafe { std::slice::from_raw_parts_mut(data, length) };
    let mut output = 0;
    for input in 0..bytes.len() {
        if unsafe { isspace(i32::from(bytes[input])) } == 0 {
            bytes[output] = bytes[input];
            output += 1;
        }
    }
    output
}

/// # Safety
/// Data is readable for length initialized bytes. No retained pointer.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phphelpers_envelope(data: *const u8, length: usize) -> u8 {
    if length == 0 || data.is_null() || length > isize::MAX as usize {
        return 0;
    }
    let bytes = unsafe { std::slice::from_raw_parts(data, length) };
    u8::from(bytes.first() == Some(&b'<') && bytes.last() == Some(&b'>'))
}

#[repr(C)]
#[derive(Default)]
pub struct TypeLayout {
    pub key: u32,
    pub value: u32,
    pub offset: u16,
    pub length: u16,
}

#[repr(u32)]
enum DefinitionAction {
    False,
    True,
    TooLong,
    Lowercase,
    Normalize,
    EnvelopeError,
    ParseSelf,
    LookupClass,
    ClassError,
}

/// # Safety
/// Phase is independent aligned writable native storage initialized to zero.
/// Data is borrowed only at phase2, after native lowercase/copy/normalization,
/// and is readable for length initialized bytes. Native class lookup, its local
/// zend::String custody and all allocation/error/reentry run after return.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phphelpers_parse_definition(
    phase: *mut u32,
    data: *const u8,
    length: usize,
    kind: u32,
    observation: u8,
) -> u32 {
    use DefinitionAction::*;
    let Some(phase) = (unsafe { phase.as_mut() }) else {
        return False as u32;
    };
    let (action, next) = match *phase {
        0 if length >= 65535 => (TooLong, 5),
        0 => (Lowercase, 1),
        1 => (Normalize, 2),
        2 if unsafe { swr_v1_phphelpers_envelope(data, length) } != 0 => (ParseSelf, 3),
        2 => (EnvelopeError, 5),
        3 if observation == 0 => (False, 5),
        3 if kind == OBJECT => (LookupClass, 4),
        3 => (True, 5),
        4 => (if observation != 0 { True } else { ClassError }, 5),
        _ => (False, 5),
    };
    *phase = next;
    action as u32
}

#[repr(C)]
pub struct BuiltinState {
    pub phase: u32,
    pub index: i32,
}

#[repr(u32)]
enum BuiltinAction {
    Done,
    ObserveTyped,
    CaptureArguments,
    CheckArgument,
    ObserveReplacement,
    CheckReplacementArray,
    CheckReplacementScalar,
    CaptureSpliceSource,
    Push,
    Unshift,
    Splice,
    Restore,
}

fn builtin_original(operation: u32) -> BuiltinAction {
    match operation {
        0 => BuiltinAction::Push,
        1 => BuiltinAction::Unshift,
        _ => BuiltinAction::Splice,
    }
}

/// # Safety
/// State is independent aligned writable native storage initialized to phase0,
/// index1. Observations are copied after the returned native action completes.
/// Zend argument/HashTable iteration and original handlers execute after return.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phphelpers_builtin(
    state: *mut BuiltinState,
    operation: u32,
    count: i32,
    observation: u8,
) -> u32 {
    use BuiltinAction::*;
    let Some(state) = (unsafe { state.as_mut() }) else {
        return Done as u32;
    };
    if operation > 2 || state.index < 1 {
        return Done as u32;
    }
    loop {
        let (action, next) = match state.phase {
            0 if observation != 0 => (ObserveTyped, 1),
            0 => (builtin_original(operation), 9),
            1 if observation == 0 => (builtin_original(operation), 9),
            1 if operation < 2 => (CaptureArguments, 2),
            1 if count > 3 => (ObserveReplacement, 4),
            1 => (CaptureSpliceSource, 6),
            2 if state.index < count => (CheckArgument, 3),
            2 => (
                builtin_original(operation),
                if operation == 1 { 7 } else { 9 },
            ),
            3 if observation != 0 => {
                state.index += 1;
                state.phase = 2;
                continue;
            }
            3 => (Done, 9),
            4 => (
                if observation != 0 {
                    CheckReplacementArray
                } else {
                    CheckReplacementScalar
                },
                5,
            ),
            5 if observation != 0 => (CaptureSpliceSource, 6),
            5 => (Done, 9),
            6 => (Splice, 7),
            7 => (Restore, 9),
            _ => (Done, 9),
        };
        state.phase = next;
        return action as u32;
    }
}

#[repr(u32)]
enum MutationAction {
    Done,
    CopyMetadata,
    Route,
    Insert,
    FetchWriteConstant,
    FetchWriteVariable,
    FetchReadWriteConstant,
    FetchReadWriteVariable,
    Assign,
    CannotAdd,
    ObserveReference,
    ObserveOperation,
    TypedReference,
    Binary,
    ConcatError,
    NumericError,
    ReturnUsed,
    CopyResult,
    IsVariable,
    Addref,
    Free,
    NullResult,
}

fn mutation_success(operation: u32) -> (MutationAction, u32) {
    if operation == 0 {
        (MutationAction::IsVariable, 13)
    } else {
        (MutationAction::Free, 15)
    }
}

/// # Safety
/// Phase is independent aligned native scalar storage, initially zero. Each
/// observation belongs only to the immediately preceding native action. Native
/// COW, references, opcodes, allocation, callbacks and Zend cleanup run outside
/// this call; no native storage is retained.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phphelpers_mutation(
    phase: *mut u32,
    operation: u32,
    observation: u32,
) -> u32 {
    use MutationAction::*;
    let Some(phase) = (unsafe { phase.as_mut() }) else {
        return Done as u32;
    };
    if operation > 1 {
        return Done as u32;
    }
    let (action, next) = match *phase {
        0 if observation != 0 => (CopyMetadata, 1),
        0 | 1 => (Route, 2),
        2 if operation == 0 => match observation {
            1 => (Insert, 3),
            2 => (FetchWriteConstant, 4),
            _ => (FetchWriteVariable, 4),
        },
        2 => (
            if observation == 2 {
                FetchReadWriteConstant
            } else {
                FetchReadWriteVariable
            },
            4,
        ),
        3 if observation == 0 => (CannotAdd, 10),
        3 => (ReturnUsed, 9),
        4 if observation == 0 => (Free, 11),
        4 if operation == 0 => (Assign, 5),
        4 => (ObserveReference, 6),
        5 if observation == 0 => (Free, 11),
        5 => (ReturnUsed, 9),
        6 if observation == 2 => (TypedReference, 8),
        6 => (ObserveOperation, 7),
        7 => match operation_action(observation & 255, u8::from(observation & 256 != 0)) {
            1 => (ConcatError, 10),
            2 => (NumericError, 10),
            _ => (Binary, 8),
        },
        8 => (ReturnUsed, 9),
        9 if observation != 0 => (CopyResult, 12),
        9 | 12 => mutation_success(operation),
        10 => (Free, 11),
        11 => (ReturnUsed, 16),
        13 if observation != 0 => (Addref, 14),
        13 | 14 => (Free, 15),
        16 if observation != 0 => (NullResult, 15),
        _ => (Done, 15),
    };
    *phase = next;
    action as u32
}

#[repr(u32)]
enum ValidationAction {
    Done,
    TypeError,
    ObjectError,
    PlainArrayError,
    ArrayTypeError,
    ObserveInstance,
    ObserveArray,
    CompareArray,
}

/// # Safety
/// Phase is independent writable native scalar storage, initially zero. The
/// observation is copied only after the returned native action has completed.
/// No native pointer, callback or Zend frame is retained by Rust.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phphelpers_validate_value(
    phase: *mut u32,
    expected: u32,
    actual: u32,
    observation: u8,
) -> u32 {
    use ValidationAction::*;
    let Some(phase) = (unsafe { phase.as_mut() }) else {
        return Done as u32;
    };
    let (action, next) = match *phase {
        0 => match value_action(expected, actual) {
            1 => (TypeError, 4),
            2 => (ObserveInstance, 1),
            3 => (ObserveArray, 2),
            _ => (Done, 4),
        },
        1 => (if observation != 0 { Done } else { ObjectError }, 4),
        2 if observation != 0 => (CompareArray, 3),
        2 => (PlainArrayError, 4),
        3 => (
            if observation != 0 {
                Done
            } else {
                ArrayTypeError
            },
            4,
        ),
        _ => (Done, 4),
    };
    *phase = next;
    action as u32
}

/// # Safety
/// Backing is the initialized C-string prefix (before NUL), logical is the native
/// extent inside that backing, output is independent aligned writable storage.
/// Unsupported domains retain the original native path; no new diagnostic.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phphelpers_type_layout(
    data: *const u8,
    backing: usize,
    logical: u16,
    output: *mut TypeLayout,
) -> u32 {
    if data.is_null()
        || output.is_null()
        || backing > isize::MAX as usize
        || usize::from(logical) > backing
    {
        return 0;
    }
    let bytes = unsafe { std::slice::from_raw_parts(data, backing) };
    unsafe { write_type_layout(bytes, backing, logical, output) }
}

/// # Safety
/// Data is a readable initialized span including a NUL; logical bytes and their
/// terminating byte fit inside backing. Output is independent aligned storage.
/// Native allocation, diagnostics and class lookup happen after this returns.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phphelpers_type_span(
    data: *const u8,
    backing: usize,
    logical: u16,
    output: *mut TypeLayout,
) -> u32 {
    if data.is_null()
        || output.is_null()
        || backing > isize::MAX as usize
        || usize::from(logical) >= backing
    {
        return 0;
    }
    let bytes = unsafe { std::slice::from_raw_parts(data, backing) };
    let Some(c_prefix) = bytes.iter().position(|byte| *byte == 0) else {
        return 0;
    };
    unsafe { write_type_layout(bytes, c_prefix, logical, output) }
}

unsafe fn write_type_layout(
    bytes: &[u8],
    c_prefix: usize,
    logical: u16,
    output: *mut TypeLayout,
) -> u32 {
    let comma = bytes[..c_prefix].iter().position(|byte| *byte == b',');
    let (key, offset) = match comma {
        Some(position) if position > 0 && position < usize::from(logical) => {
            (kind(&bytes[1..position]), position + 1)
        }
        Some(_) => return 0,
        None => (UNDEF, 1),
    };
    if key != UNDEF && key != LONG && key != 5 {
        unsafe {
            *output = TypeLayout {
                key,
                value: UNDEF,
                offset: offset as u16,
                length: 0,
            };
        }
        return 2;
    }
    let Some(length) = usize::from(logical).checked_sub(offset + 1) else {
        return 0;
    };
    if length == 0 || offset + length > bytes.len() {
        return 0;
    }
    let value = kind(&bytes[offset..offset + length]);
    unsafe {
        *output = TypeLayout {
            key,
            value,
            offset: offset as u16,
            length: length as u16,
        };
    }
    1
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_phphelpers_operation(expected: u32, concat: u8) -> u32 {
    operation_action(expected, concat)
}

fn operation_action(expected: u32, concat: u8) -> u32 {
    if concat != 0 {
        if expected == 5 { 0 } else { 1 }
    } else if expected == LONG || expected == 4 {
        0
    } else {
        2
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_phphelpers_method_family(kind: u32) -> i32 {
    method_family(kind)
}

fn method_family(kind: u32) -> i32 {
    match kind {
        ARRAY => 0,
        5 => 1,
        8 => 2,
        _ => -1,
    }
}

#[repr(u32)]
enum TypedAction {
    Done = 0,
    Allocate = 1,
    Parse = 2,
    Free = 3,
    Null = 4,
    ObserveInitialTyped = 5,
    Compare = 6,
    CopyInitial = 7,
    Mismatch = 8,
    Create = 9,
    Publish = 10,
    ObserveNested = 11,
    ParseElement = 12,
    Destroy = 13,
    ObserveInitial = 14,
    Iterate = 15,
    ObserveTyped = 16,
    ObserveDefinition = 17,
    True = 18,
    False = 19,
    SetTrue = 20,
    SetFalse = 21,
    StringKey = 22,
    IndexKey = 23,
    Check = 24,
    Addref = 25,
    InsertString = 26,
    InsertIndex = 27,
}

/// # Safety
/// Phase is aligned native storage initialized to0. Modes construction0,
/// predicate1/initializer-entry2. Copied observations are freshly returned by the
/// requested native effect; key-string presence is consumed only in entry mode.
/// Native Zend allocation/storage/iteration/GC/callback execution is never in Rust.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phphelpers_typed(
    phase: *mut u32,
    mode: u32,
    observation: u8,
    string_key: u8,
) -> u32 {
    use TypedAction::*;
    let Some(phase) = (unsafe { phase.as_mut() }) else {
        return Done as u32;
    };
    let yes = observation != 0;
    let (action, next) = match (mode, *phase) {
        (0, 0) => (Allocate, 1),
        (0, 1) => (Parse, 2),
        (0, 2) if !yes => (Free, 3),
        (0, 2) => (ObserveInitialTyped, 4),
        (0, 3) => (Null, 99),
        (0, 4) if yes => (Compare, 5),
        (0, 4) => (Create, 7),
        (0, 5) => (if yes { CopyInitial } else { Mismatch }, 6),
        (0, 6) => (Free, 99),
        (0, 7) => (Publish, 8),
        (0, 8) => (ObserveNested, 9),
        (0, 9) if yes => (ParseElement, 10),
        (0, 9) => (ObserveInitial, 11),
        (0, 10) if !yes => (Destroy, 3),
        (0, 10) => (ObserveInitial, 11),
        (0, 11) => (if yes { Iterate } else { Done }, 99),
        (1, 0) => (ObserveTyped, 1),
        (1, 1) if !yes => (False, 99),
        (1, 1) => (ObserveDefinition, 2),
        (1, 2) if !yes => (True, 99),
        (1, 2) => (Allocate, 3),
        (1, 3) => (Parse, 4),
        (1, 4) if !yes => (Free, 5),
        (1, 4) => (Compare, 6),
        (1, 5) => (False, 99),
        (1, 6) => (if yes { SetTrue } else { SetFalse }, 7),
        (1, 7) => (Free, 99),
        (2, 0) => (if string_key != 0 { StringKey } else { IndexKey }, 1),
        (2, 1) => (Check, 2),
        (2, 2) if !yes => (Destroy, 3),
        (2, 2) => (Addref, 4),
        (2, 3) => (Null, 99),
        (2, 4) => (
            if string_key != 0 {
                InsertString
            } else {
                InsertIndex
            },
            99,
        ),
        _ => (Done, 99),
    };
    *phase = next;
    action as u32
}

#[repr(u32)]
enum InvocationAction {
    Done = 0,
    Resolve = 1,
    UnknownMethod = 2,
    UnknownFunction = 3,
    Arguments = 4,
    Allocate = 5,
    Copy = 6,
    Reorder = 7,
    Invoke = 8,
    ObserveTemporary = 9,
    ReleaseThis = 10,
    ReleaseArguments = 11,
}

/// # Safety
/// Phase is aligned native storage initialized to0. Mode method0/reorder1.
/// Observation is alias presence at0, function presence at1, and freshly observed
/// temporary-this after native invocation at6. All Zend and string lifetimes
/// remain native, with no retained pointer or borrow across effects.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phphelpers_invoke(
    phase: *mut u32,
    mode: u32,
    observation: u8,
) -> u32 {
    use InvocationAction::*;
    let Some(phase) = (unsafe { phase.as_mut() }) else {
        return Done as u32;
    };
    let (action, next) = match *phase {
        0 if mode == 1 => (Arguments, 2),
        0 => (
            if observation != 0 {
                Resolve
            } else {
                UnknownMethod
            },
            1,
        ),
        1 if observation == 0 => (UnknownFunction, 9),
        1 => (Arguments, 2),
        2 => (Allocate, 3),
        3 => (if mode == 1 { Reorder } else { Copy }, 4),
        4 => (Invoke, if mode == 1 { 8 } else { 5 }),
        5 => (ObserveTemporary, 6),
        6 if observation != 0 => (ReleaseThis, 8),
        6 | 8 => (ReleaseArguments, 9),
        _ => (Done, 9),
    };
    *phase = next;
    action as u32
}

#[repr(C)]
pub struct MethodState {
    pub phase: u32,
    pub family: i32,
}

#[repr(u32)]
enum MethodAction {
    Dispatch = 0,
    Continue = 1,
    Constant = 2,
    Variable = 3,
    Observe = 4,
    Reference = 5,
    Allocate = 6,
    Fill = 7,
    Array = 8,
    String = 9,
    Stream = 10,
    Publish = 11,
}

/// # Safety
/// State is aligned native storage initialized to{0,0}; operand constant0,
/// unused1/variable2. Observation is a copied module kind (reference10), refreshed
/// after each native observation. Rust never retains Zend values or VM frames.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phphelpers_method_frame(
    state: *mut MethodState,
    operand: u32,
    observation: u32,
) -> u32 {
    use MethodAction::*;
    let Some(state) = (unsafe { state.as_mut() }) else {
        return Dispatch as u32;
    };
    let (action, next) = match state.phase {
        0 if operand == 1 => (Dispatch, 8),
        0 => (if operand == 0 { Constant } else { Variable }, 1),
        1 => (Observe, 2),
        2 if observation == 10 => (Reference, 3),
        2 | 3 => {
            state.family = method_family(observation);
            (if state.family < 0 { Dispatch } else { Allocate }, 4)
        }
        4 => (Fill, 5),
        5 => (
            match state.family {
                0 => Array,
                1 => String,
                _ => Stream,
            },
            6,
        ),
        6 => (Publish, 7),
        7 => (Continue, 8),
        _ => (Dispatch, 8),
    };
    state.phase = next;
    action as u32
}

#[repr(u32)]
enum VmAction {
    Dispatch = 0,
    Continue = 1,
    GetArray = 2,
    Variable = 3,
    Constant = 4,
    Temporary = 5,
    Dereference = 6,
    ObserveArray = 7,
    ObserveTyped = 8,
    Value = 9,
    ConstantKey = 10,
    UnusedKey = 11,
    VariableKey = 12,
    Check = 13,
    Invoke = 14,
    Free = 15,
    Advance = 16,
    ObserveList = 17,
    ReferenceError = 18,
    ListError = 19,
}

/// # Safety
/// Phase is aligned native storage initialized to0. Operations assign0,
/// reference-foreach1/unset2; operand variable1/constant2/temporary0, key
/// constant0/unused1/variable2. Observation refreshed after the requested native
/// effect only. Native VM, storage and error execution remain outside Rust.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phphelpers_vm(
    phase: *mut u32,
    operation: u32,
    operand: u32,
    key: u32,
    observation: u8,
) -> u32 {
    use VmAction::*;
    let Some(phase) = (unsafe { phase.as_mut() }) else {
        return Dispatch as u32;
    };
    let (action, next) = match *phase {
        0 if operation != 1 => (GetArray, 1),
        0 => (
            match operand {
                1 => Variable,
                2 => Constant,
                _ => Temporary,
            },
            1,
        ),
        1 if operation == 1 => (Dereference, 2),
        1 | 2 => (ObserveArray, 3),
        3 if observation == 0 => (Dispatch, 11),
        3 => (ObserveTyped, 4),
        4 if observation == 0 => (Dispatch, 11),
        4 if operation == 0 => (Value, 5),
        4 if operation == 1 => (ReferenceError, 9),
        4 => (ObserveList, 7),
        5 => (
            match key {
                0 => ConstantKey,
                1 => UnusedKey,
                _ => VariableKey,
            },
            6,
        ),
        6 => (Check, 8),
        7 => (
            if observation != 0 {
                ListError
            } else {
                Dispatch
            },
            9,
        ),
        8 => (
            if observation != 0 { Invoke } else { Free },
            if observation != 0 { 10 } else { 9 },
        ),
        9 => (Continue, 11),
        10 => (Advance, 9),
        _ => (Dispatch, 11),
    };
    *phase = next;
    action as u32
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_phphelpers_opcode(operation: u32, typed: u8, list: u8) -> u32 {
    if typed == 0 {
        return 0;
    }
    match operation {
        0 => 1,
        1 => 2,
        2 if list != 0 => 3,
        _ => 0,
    }
}

/// # Safety
/// Phase is native-owned initialized aligned storage. Compiled is observed only
/// after native PCRE cache lookup. No library/Zend pointer crosses this call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phphelpers_regex(phase: *mut u32, compiled: u8) -> u32 {
    let Some(phase) = (unsafe { phase.as_mut() }) else {
        return 0;
    };
    let (action, next) = match *phase {
        0 => (1, 1),
        1 if compiled == 0 => (6, 6),
        1 => (2, 2),
        2 => (3, 3),
        3 => (4, 4),
        4 => (5, 5),
        _ => (0, 6),
    };
    *phase = next;
    action
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_phphelpers_json_options(options: i64, mask: i64, assoc: u8) -> i64 {
    if assoc != 0 {
        options | mask
    } else {
        options & !mask
    }
}

/// # Safety
/// Value is an initialized readable byte span; output is disjoint writable
/// native storage of capacity bytes, length is independent writable storage.
/// Native Zend allocation, publication and diagnostics occur outside this call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phphelpers_definition(
    key: u32,
    value: *const u8,
    value_length: usize,
    output: *mut u8,
    capacity: usize,
    length: *mut usize,
) -> u8 {
    let prefix: &[u8] = match key {
        LONG => b"<int,",
        5 => b"<string,",
        // Preserve the pinned no-key projection: its initial '<' is overwritten
        // by memcpy at offset0. This is not a formatting correction.
        _ => b"",
    };
    let Some(size) = prefix
        .len()
        .checked_add(value_length)
        .and_then(|n| n.checked_add(2))
    else {
        return 0;
    };
    if output.is_null()
        || length.is_null()
        || (value_length != 0 && value.is_null())
        || size > capacity
        || size > isize::MAX as usize
    {
        return 0;
    }
    unsafe {
        std::ptr::copy_nonoverlapping(prefix.as_ptr(), output, prefix.len());
        if value_length != 0 {
            std::ptr::copy_nonoverlapping(value, output.add(prefix.len()), value_length);
        }
        *output.add(size - 2) = b'>';
        *output.add(size - 1) = 0;
        *length = size - 1;
    }
    1
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn exact_aliases_and_unknown_names() {
        assert_eq!(alias(0, b"map"), Some(b"swoole_array_map\0".as_slice()));
        assert_eq!(alias(1, b"mbLength"), Some(b"mb_strlen\0".as_slice()));
        assert_eq!(alias(2, b"read"), Some(b"fread\0".as_slice()));
        assert_eq!(alias(0, b"MAP"), None);
        assert_eq!(alias(0, b"map\0"), None);
    }
    #[test]
    fn permutation_ranges_reproduce_native_rotation() {
        for count in 1..128 {
            for position in 0..count {
                let mut plan = ArgumentPlan::default();
                assert_eq!(
                    unsafe { swr_v1_phphelpers_arguments(count, position, &mut plan) },
                    1
                );
                let source: Vec<_> = (0..count).collect();
                let mut actual = source[1..1 + plan.head as usize].to_vec();
                actual.push(source[0]);
                actual.extend_from_slice(&source[plan.tail_begin as usize..]);
                let mut expected = source;
                expected[..=position as usize].rotate_left(1);
                assert_eq!(actual, expected);
                assert_eq!(plan.tail_count, (count - position - 1) as u32);
            }
        }
    }
    #[test]
    fn callable_observation_order_is_lazy() {
        for truthy in [0, 1] {
            for valid in [0, 1] {
                let mut phase = 0;
                assert_eq!(
                    unsafe { swr_v1_phphelpers_callable(&mut phase, truthy, valid) },
                    1
                );
                let next = unsafe { swr_v1_phphelpers_callable(&mut phase, truthy, valid) };
                if truthy == 0 {
                    assert_eq!(next, 3);
                } else {
                    assert_eq!(next, 2);
                    assert_eq!(
                        unsafe { swr_v1_phphelpers_callable(&mut phase, truthy, valid) },
                        if valid == 0 { 4 } else { 5 }
                    );
                }
                assert_eq!(
                    unsafe { swr_v1_phphelpers_callable(&mut phase, truthy, valid) },
                    0
                );
            }
        }
    }
    #[test]
    fn typed_list_range_and_bool_semantics() {
        assert_eq!(swr_v1_phphelpers_key(UNDEF, LONG, -1, 0), 0);
        assert_eq!(swr_v1_phphelpers_key(UNDEF, LONG, 2, 2), 0);
        assert_eq!(swr_v1_phphelpers_key(UNDEF, LONG, 3, 2), 2);
        assert_eq!(swr_v1_phphelpers_key(UNDEF, NULL, 0, 0), 0);
        assert_eq!(swr_v1_phphelpers_value(BOOL, BOOL), 0);
        assert_eq!(swr_v1_phphelpers_value(OBJECT, OBJECT), 2);
        assert_eq!(swr_v1_phphelpers_value(ARRAY, ARRAY), 3);
        for result in [-1, 0, 1, i64::MAX] {
            assert_eq!(
                swr_v1_phphelpers_call_success(result, 0),
                u8::from(result == 0)
            );
            assert_eq!(
                swr_v1_phphelpers_call_success(result, 1),
                u8::from(result >= 0)
            );
        }
    }
    #[test]
    fn shared_common_policy_preserves_positive_lifecycles() {
        for numeric in [0, 1] {
            for existing in [0, 1] {
                let mut phase = 0;
                let first =
                    unsafe { swr_v1_phphelpers_merge_keyed(&mut phase, 0, existing, numeric) };
                assert_eq!(first, if numeric != 0 { 1 } else { 2 });
                let next =
                    unsafe { swr_v1_phphelpers_merge_keyed(&mut phase, 0, existing, numeric) };
                assert_eq!(next, if numeric != 0 { 3 } else { 4 });
                let final_action =
                    unsafe { swr_v1_phphelpers_merge_keyed(&mut phase, 0, existing, numeric) };
                assert_eq!(
                    final_action,
                    if existing != 0 {
                        5
                    } else if numeric != 0 {
                        6
                    } else {
                        7
                    }
                );
                assert_eq!(
                    unsafe { swr_v1_phphelpers_merge_keyed(&mut phase, 0, existing, numeric) },
                    0
                );
            }
        }
        for (kind, family) in [(ARRAY, 0), (5, 1), (8, 2)] {
            assert_eq!(swr_v1_phphelpers_method_family(kind), family);
            assert_eq!(swr_v1_phphelpers_key_route(kind, kind), 0);
        }
        assert_eq!(swr_v1_phphelpers_operation(LONG, 0), 0);
        assert_eq!(swr_v1_phphelpers_operation(4, 0), 0);
        assert_eq!(swr_v1_phphelpers_operation(5, 1), 0);
    }
    #[test]
    fn initialized_type_span_keeps_frozen_prefix_contract() {
        let value = b"<i\0t>\0";
        let mut output = TypeLayout::default();
        assert_eq!(
            unsafe { swr_v1_phphelpers_type_layout(value.as_ptr(), 2, 5, &mut output) },
            0
        );
        assert_eq!(
            unsafe { swr_v1_phphelpers_type_span(value.as_ptr(), value.len(), 5, &mut output) },
            1
        );
        assert_eq!(
            (output.key, output.value, output.offset, output.length),
            (UNDEF, OBJECT, 1, 3)
        );
        for bytes in [b"<int>".as_slice(), b"".as_slice()] {
            output.offset = 77;
            assert_eq!(
                unsafe { swr_v1_phphelpers_type_span(bytes.as_ptr(), bytes.len(), 5, &mut output) },
                0
            );
            assert_eq!(output.offset, 77);
        }
    }
}
