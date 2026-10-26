use std::ffi::c_char;

#[repr(C)]
#[derive(Clone, Copy)]
pub struct PhpEventAlias {
    pub method: *const c_char,
    pub method_length: usize,
    pub function: *const c_char,
    pub function_length: usize,
}

#[repr(C)]
pub struct PhpEventMethod {
    pub alias: PhpEventAlias,
    pub handler: u32,
    pub flags: u32,
}

// The sole logical catalogue is in original class-method order. Native retains
// only typed handler/arginfo bindings and the mandatory stable Zend projection.
const METHODS: [(&[u8], &[u8]); 11] = [
    (b"add\0", b"swoole_event_add\0"),
    (b"del\0", b"swoole_event_del\0"),
    (b"set\0", b"swoole_event_set\0"),
    (b"isset\0", b"swoole_event_isset\0"),
    (b"dispatch\0", b"swoole_event_dispatch\0"),
    (b"defer\0", b"swoole_event_defer\0"),
    (b"cycle\0", b"swoole_event_cycle\0"),
    (b"write\0", b"swoole_event_write\0"),
    (b"wait\0", b"swoole_event_wait\0"),
    (b"rshutdown\0", b"swoole_event_rshutdown\0"),
    (b"exit\0", b"swoole_event_exit\0"),
];
// Alias publication historically has a different order; names are not copied.
const ALIAS_ORDER: [usize; 11] = [0, 1, 2, 8, 3, 4, 5, 6, 7, 10, 9];

fn record(index: usize, legacy_alias: bool) -> Option<PhpEventMethod> {
    let handler = if legacy_alias {
        *ALIAS_ORDER.get(index)?
    } else {
        index
    };
    let &(method, function) = METHODS.get(handler)?;
    Some(PhpEventMethod {
        alias: PhpEventAlias {
            method: method.as_ptr().cast(),
            method_length: method.len() - 1,
            function: function.as_ptr().cast(),
            function_length: function.len() - 1,
        },
        handler: u32::try_from(handler).ok()?,
        flags: 0,
    })
}

/// Complete immutable class/alias record. Native supplies actual Zend flag bits;
/// Rust owns their public-static combination. Unknown indices/null output return
/// zero without writing. Names remain static for the registration lifetime.
/// # Safety
/// Non-null output is aligned independent writable POD storage.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpevents_catalogue(
    index: usize,
    legacy_alias: u8,
    public_flag: u32,
    static_flag: u32,
    output: *mut PhpEventMethod,
) -> u8 {
    let Some(mut method) = record(index, legacy_alias != 0) else {
        return 0;
    };
    if output.is_null() {
        return 0;
    }
    method.flags = public_flag | static_flag;
    // Native output may be uninitialized: write the POD without borrowing it.
    unsafe { output.write(method) };
    1
}

/// Frozen legacy alias ABI, backed by the same sole catalogue.
/// # Safety
/// Non-null output is aligned independent writable POD storage.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpevents_alias(index: usize, output: *mut PhpEventAlias) -> u8 {
    let Some(method) = record(index, true) else {
        return 0;
    };
    if output.is_null() {
        return 0;
    }
    unsafe { output.write(method.alias) };
    1
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::ffi::CStr;
    #[test]
    fn orders_flags_and_static_lifetime() {
        let class = [
            "add",
            "del",
            "set",
            "isset",
            "dispatch",
            "defer",
            "cycle",
            "write",
            "wait",
            "rshutdown",
            "exit",
        ];
        let aliases = [
            "add",
            "del",
            "set",
            "wait",
            "isset",
            "dispatch",
            "defer",
            "cycle",
            "write",
            "exit",
            "rshutdown",
        ];
        for (legacy, names) in [(false, class), (true, aliases)] {
            for (index, expected) in names.iter().enumerate() {
                let mut output = record(index, legacy).unwrap();
                assert_eq!(
                    unsafe {
                        swr_v1_phpevents_catalogue(index, legacy as u8, 0x100, 0x40, &mut output)
                    },
                    1
                );
                assert_eq!(
                    unsafe { CStr::from_ptr(output.alias.method) }.to_bytes(),
                    expected.as_bytes()
                );
                assert_eq!(output.alias.method_length, expected.len());
                assert_eq!(output.flags, 0x140);
                let direct = record(output.handler as usize, false).unwrap();
                assert_eq!(output.alias.method, direct.alias.method);
                assert_eq!(output.alias.function, direct.alias.function);
                let saved = output.alias.method;
                assert_eq!(
                    unsafe { swr_v1_phpevents_catalogue(11, legacy as u8, 0, 0, &mut output) },
                    0
                );
                assert_eq!(output.alias.method, saved);
            }
        }
        assert_eq!(
            unsafe { swr_v1_phpevents_catalogue(0, 0, 1, 2, std::ptr::null_mut()) },
            0
        );
        assert_eq!(
            unsafe { swr_v1_phpevents_alias(0, std::ptr::null_mut()) },
            0
        );
    }
}
