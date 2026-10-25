//! Frontend class/constant/property catalogue and ordered native startup effects.
use std::ffi::c_char;

#[repr(C)]
pub struct BootstrapState {
    pub index: u32,
    pub phase: u32,
    pub cli: u8,
}
#[repr(C)]
pub struct BootstrapPlan {
    pub action: u32,
    pub id: u32,
    pub name: *const c_char,
    pub length: usize,
}
#[derive(Clone, Copy)]
enum Row {
    Class {
        id: u32,
        name: &'static [u8],
        alias: Option<&'static [u8]>,
        copy: bool,
        fixup: bool,
    },
    Constant(u32, &'static [u8]),
    Property(&'static [u8]),
    Effect(u32),
    Cli,
}
const fn class(
    id: u32,
    name: &'static [u8],
    alias: Option<&'static [u8]>,
    copy: bool,
    fixup: bool,
) -> Row {
    Row::Class {
        id,
        name,
        alias,
        copy,
        fixup,
    }
}
const CORE: &[Row] = &[
    class(0, b"Swoole\\Coroutine\0", Some(b"Co\0"), false, true),
    class(
        1,
        b"Swoole\\Coroutine\\Iterator\0",
        Some(b"Co\\Iterator\0"),
        false,
        false,
    ),
    class(
        2,
        b"Swoole\\Coroutine\\Context\0",
        Some(b"Co\\Context\0"),
        false,
        false,
    ),
    Row::Constant(0, b"SWOOLE_DEFAULT_MAX_CORO_NUM\0"),
    Row::Constant(1, b"SWOOLE_CORO_MAX_NUM_LIMIT\0"),
    Row::Constant(2, b"SWOOLE_CORO_INIT\0"),
    Row::Constant(3, b"SWOOLE_CORO_WAITING\0"),
    Row::Constant(4, b"SWOOLE_CORO_RUNNING\0"),
    Row::Constant(5, b"SWOOLE_CORO_END\0"),
    class(3, b"Swoole\\ExitException\0", None, true, false),
    Row::Property(b"flags\0"),
    Row::Property(b"status\0"),
    class(
        4,
        b"Swoole\\Coroutine\\CanceledException\0",
        None,
        true,
        true,
    ),
    class(
        5,
        b"Swoole\\Coroutine\\TimeoutException\0",
        None,
        true,
        true,
    ),
    Row::Constant(6, b"SWOOLE_EXIT_IN_COROUTINE\0"),
    Row::Constant(7, b"SWOOLE_EXIT_IN_SERVER\0"),
    Row::Cli,
    Row::Effect(0),
    Row::Effect(1),
    Row::Effect(2),
    Row::Effect(3),
    Row::Effect(4),
];
const SCHEDULER: &[Row] = &[class(
    0,
    b"Swoole\\Coroutine\\Scheduler\0",
    Some(b"Co\\Scheduler\0"),
    true,
    true,
)];
const SYSTEM: &[Row] = &[
    class(
        0,
        b"Swoole\\Coroutine\\System\0",
        Some(b"Co\\System\0"),
        false,
        true,
    ),
    Row::Constant(0, b"FILE_LOCK\0"),
];
fn plan(action: u32, id: u32, name: Option<&'static [u8]>) -> BootstrapPlan {
    BootstrapPlan {
        action,
        id,
        name: name.map_or(std::ptr::null(), |n| n.as_ptr().cast()),
        length: name.map_or(0, |n| n.len() - 1),
    }
}

/// Native class slots/handlers/arginfo/opcode/autoload storage stay authoritative.
/// Every native effect happens after return; names are immutable static bytes.
/// # Safety
/// State is exclusive zero-initialized native POD. Kind stays fixed (core0,
/// Scheduler1,System2). Observation answers the latest native presence request;
/// exit_opcode is the actual PHP-version compilation capability.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_bootstrap(
    state: *mut BootstrapState,
    kind: u32,
    observation: u8,
    exit_opcode: u8,
) -> BootstrapPlan {
    let rows = match kind {
        0 => CORE,
        1 => SCHEDULER,
        2 => SYSTEM,
        _ => return plan(0, 0, None),
    };
    let state = unsafe { &mut *state };
    loop {
        let Some(row) = rows.get(state.index as usize) else {
            return plan(0, 0, None);
        };
        match *row {
            Row::Class {
                id,
                name,
                alias,
                copy,
                fixup,
            } => {
                let phase = state.phase;
                state.phase = state.phase.saturating_add(1);
                match phase {
                    0 => return plan(1, id, Some(name)), // native register
                    1 if alias.is_some() => return plan(2, id, alias), // fresh short-name flag
                    1 => state.phase = 3,
                    2 if observation != 0 => return plan(3, id, alias), // native alias
                    2 => {}
                    3 if copy => return plan(4, id, None),
                    4 if fixup => return plan(5, id, None),
                    5.. => {
                        state.index += 1;
                        state.phase = 0;
                    }
                    _ => {}
                }
            }
            Row::Cli if state.phase == 0 => {
                state.phase = 1;
                return plan(8, 0, None);
            }
            Row::Cli => {
                state.cli = u8::from(observation != 0);
                state.phase = 0;
                state.index += 1;
            }
            Row::Constant(id, name) => {
                state.index += 1;
                return plan(6, id, Some(name));
            }
            Row::Property(name) => {
                state.index += 1;
                return plan(7, 0, Some(name));
            }
            Row::Effect(id) => {
                state.index += 1;
                if id < 3 && (state.cli == 0 || id == 0 && exit_opcode == 0) {
                    continue;
                }
                return plan(9, id, None);
            }
        }
    }
}
