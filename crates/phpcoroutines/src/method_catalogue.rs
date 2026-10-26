//! Sole frontend method catalogue. Native owns handler/arginfo/Zend ABI projections.
use core::ffi::{CStr, c_char};
struct Method {
    name: &'static CStr,
    binding: u32,
    is_static: bool,
    time_only: bool,
}
impl Method {
    const fn public(name: &'static CStr, binding: u32) -> Self {
        Self {
            name,
            binding,
            is_static: false,
            time_only: false,
        }
    }
    const fn public_static(name: &'static CStr, binding: u32) -> Self {
        Self {
            name,
            binding,
            is_static: true,
            time_only: false,
        }
    }
    const fn with_time(mut self) -> Self {
        self.time_only = true;
        self
    }
}
const TABLE_0: &[Method] = &[
    Method::public_static(c"create", 0),
    Method::public_static(c"defer", 1),
    Method::public_static(c"set", 2),
    Method::public_static(c"getOptions", 3),
    Method::public_static(c"exists", 4),
    Method::public_static(c"yield", 5),
    Method::public_static(c"cancel", 6),
    Method::public_static(c"join", 7),
    Method::public_static(c"isCanceled", 8),
    Method::public_static(c"setTimeLimit", 9),
    Method::public_static(c"suspend", 10),
    Method::public_static(c"resume", 11),
    Method::public_static(c"stats", 12),
    Method::public_static(c"getCid", 13),
    Method::public_static(c"getuid", 14),
    Method::public_static(c"getPcid", 15),
    Method::public_static(c"getContext", 16),
    Method::public_static(c"getBackTrace", 17),
    Method::public_static(c"printBackTrace", 18),
    Method::public_static(c"getElapsed", 19),
    Method::public_static(c"getStackUsage", 20),
    Method::public_static(c"list", 21),
    Method::public_static(c"listCoroutines", 22),
    Method::public_static(c"enableScheduler", 23),
    Method::public_static(c"disableScheduler", 24),
    Method::public_static(c"getExecuteTime", 25).with_time(),
    Method::public_static(c"gethostbyname", 26),
    Method::public_static(c"dnsLookup", 27),
    Method::public_static(c"exec", 28),
    Method::public_static(c"sleep", 29),
    Method::public_static(c"getaddrinfo", 30),
    Method::public_static(c"statvfs", 31),
    Method::public_static(c"readFile", 32),
    Method::public_static(c"writeFile", 33),
    Method::public_static(c"wait", 34),
    Method::public_static(c"waitPid", 35),
    Method::public_static(c"waitSignal", 36),
    Method::public_static(c"waitEvent", 37),
];
const TABLE_1: &[Method] = &[
    Method::public(c"getFlags", 0),
    Method::public(c"getStatus", 1),
];
const TABLE_2: &[Method] = &[
    Method::public(c"add", 0),
    Method::public(c"parallel", 1),
    Method::public(c"set", 2),
    Method::public(c"getOptions", 3),
    Method::public(c"start", 4),
];
const TABLE_3: &[Method] = &[
    Method::public_static(c"gethostbyname", 0),
    Method::public_static(c"dnsLookup", 1),
    Method::public_static(c"exec", 2),
    Method::public_static(c"sleep", 3),
    Method::public_static(c"getaddrinfo", 4),
    Method::public_static(c"statvfs", 5),
    Method::public_static(c"readFile", 6),
    Method::public_static(c"writeFile", 7),
    Method::public_static(c"wait", 8),
    Method::public_static(c"waitPid", 9),
    Method::public_static(c"waitSignal", 10),
    Method::public_static(c"waitEvent", 11),
];
#[repr(C)]
pub struct MethodCursor {
    next: u32,
    output: u32,
}
#[repr(C)]
pub struct MethodPlan {
    done: u32,
    slot: u32,
    handler: u32,
    flags: u32,
    name: *const c_char,
}
/// Return the next logical row or its exact packed sentinel. Opaque handler
/// ordinals select Native constant bindings; no Native function/Zend pointer
/// enters Rust. Names are immutable static bytes for the module lifetime.
/// # Safety
/// Cursor is distinct writable Native stack POD, initially zero, fixed catalogue
/// kind0..3 and capability bits for its whole sequence. Call until done. Native
/// resolves the binding and writes one stable Zend ABI projection after return;
/// no Rust frame/borrow survives projection or registration.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_method(
    cursor: *mut MethodCursor,
    kind: u32,
    capabilities: u8,
    public: u32,
    static_flag: u32,
) -> MethodPlan {
    let table = match kind {
        0 => TABLE_0,
        1 => TABLE_1,
        2 => TABLE_2,
        3 => TABLE_3,
        _ => &[],
    };
    // SAFETY: per this function's `# Safety` contract, `cursor` is live, aligned and exclusive.
    let cursor = unsafe { &mut *cursor };
    while let Some(method) = table.get(cursor.next as usize) {
        let handler = method.binding;
        cursor.next += 1;
        if method.time_only && capabilities & 1 == 0 {
            continue;
        }
        let slot = cursor.output;
        cursor.output += 1;
        return MethodPlan {
            done: 0,
            slot,
            handler,
            flags: public | if method.is_static { static_flag } else { 0 },
            name: method.name.as_ptr(),
        };
    }
    MethodPlan {
        done: 1,
        slot: cursor.output,
        handler: 0,
        flags: 0,
        name: core::ptr::null(),
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn complete_catalogues_pack_only_native_time_capability() {
        for caps in [0, 1] {
            for (kind, count) in [(0, 37 + caps as usize), (1, 2), (2, 5), (3, 12)] {
                let mut cursor = MethodCursor { next: 0, output: 0 };
                let mut rows = Vec::new();
                loop {
                    let p = unsafe {
                        swr_v1_phpcoroutines_method(&mut cursor, kind, caps, 0x400, 0x80)
                    };
                    assert_eq!(p.slot as usize, rows.len());
                    if p.done != 0 {
                        assert!(p.name.is_null());
                        break;
                    }
                    let name = unsafe { CStr::from_ptr(p.name) }.to_str().unwrap();
                    assert_eq!(p.flags, if kind == 0 || kind == 3 { 0x480 } else { 0x400 });
                    if kind == 0 && caps == 0 {
                        assert_ne!(p.handler, 25);
                        assert_ne!(name, "getExecuteTime");
                    }
                    rows.push((name, p.handler));
                }
                assert_eq!(rows.len(), count);
                if kind == 0 {
                    assert_eq!(rows[10], ("suspend", 10));
                    assert_eq!(rows[14], ("getuid", 14));
                    assert_eq!(rows[22], ("listCoroutines", 22));
                }
            }
        }
    }
    #[test]
    fn stable_static_names_and_terminal_cursor() {
        let mut first = MethodCursor { next: 0, output: 0 };
        let mut second = MethodCursor { next: 0, output: 0 };
        let a = unsafe { swr_v1_phpcoroutines_method(&mut first, 0, 0, 1, 2) };
        let b = unsafe { swr_v1_phpcoroutines_method(&mut second, 0, 1, 1, 2) };
        assert_eq!(a.name, b.name);
        while unsafe { swr_v1_phpcoroutines_method(&mut first, 0, 0, 1, 2) }.done == 0 {}
        let p = unsafe { swr_v1_phpcoroutines_method(&mut first, 0, 0, 1, 2) };
        assert_eq!((p.done, p.slot), (1, 37));
        assert!(p.name.is_null());
    }
}
