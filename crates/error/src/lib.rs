// SPDX-License-Identifier: Apache-2.0
// Message text derived from Swoole v6.2.2 src/core/error.cc,
// Copyright Swoole contributors; original author Tianfeng Han <rango@swoole.com>.
//! Swoole error dispatch and ignored state; native code supplies OS messages.
#![cfg_attr(
    not(test),
    deny(
        clippy::undocumented_unsafe_blocks,
        clippy::multiple_unsafe_ops_per_block
    )
)]

use std::ffi::c_char;

mod state;
pub use state::*;

// Keep C entry points free of an intermediate lookup frame.
#[inline(always)]
fn known_message(code: i32) -> *const c_char {
    match code {
        501 => c"Malloc fail",                        // SW_ERROR_MALLOC_FAIL
        502 => c"System call fail",                   // SW_ERROR_SYSTEM_CALL_FAIL
        503 => c"PHP fatal error",                    // SW_ERROR_PHP_FATAL_ERROR
        504 => c"Name too long",                      // SW_ERROR_NAME_TOO_LONG
        505 => c"Invalid params",                     // SW_ERROR_INVALID_PARAMS
        506 => c"Queue full",                         // SW_ERROR_QUEUE_FULL
        507 => c"Operation not support",              // SW_ERROR_OPERATION_NOT_SUPPORT
        508 => c"Protocol error",                     // SW_ERROR_PROTOCOL_ERROR
        509 => c"Wrong operation",                    // SW_ERROR_WRONG_OPERATION
        510 => c"PHP runtime notice",                 // SW_ERROR_PHP_RUNTIME_NOTICE
        511 => c"For test",                           // SW_ERROR_FOR_TEST
        550 => c"No payload",                         // SW_ERROR_NO_PAYLOAD
        600 => c"Undefined behavior",                 // SW_ERROR_UNDEFINED_BEHAVIOR
        601 => c"Not thread safety",                  // SW_ERROR_NOT_THREAD_SAFETY
        700 => c"File not exist",                     // SW_ERROR_FILE_NOT_EXIST
        701 => c"File too large",                     // SW_ERROR_FILE_TOO_LARGE
        702 => c"File empty",                         // SW_ERROR_FILE_EMPTY
        703 => c"Dir not exist",                      // SW_ERROR_DIR_NOT_EXIST
        710 => c"DNS Lookup duplicate request",       // SW_ERROR_DNSLOOKUP_DUPLICATE_REQUEST
        711 => c"DNS Lookup resolve failed",          // SW_ERROR_DNSLOOKUP_RESOLVE_FAILED
        712 => c"DNS Lookup resolve timeout",         // SW_ERROR_DNSLOOKUP_RESOLVE_TIMEOUT
        713 => c"DNS Lookup unsupported",             // SW_ERROR_DNSLOOKUP_UNSUPPORTED
        714 => c"DNS Lookup no server",               // SW_ERROR_DNSLOOKUP_NO_SERVER
        720 => c"Bad ipv6 address",                   // SW_ERROR_BAD_IPV6_ADDRESS
        721 => c"Unregistered signal",                // SW_ERROR_UNREGISTERED_SIGNAL
        722 => c"Bad host addr",                      // SW_ERROR_BAD_HOST_ADDR
        723 => c"Bad port",                           // SW_ERROR_BAD_PORT
        724 => c"Bad socket type",                    // SW_ERROR_BAD_SOCKET_TYPE
        800 => c"Event remove failed",                // SW_ERROR_EVENT_REMOVE_FAILED
        801 => c"Event add failed",                   // SW_ERROR_EVENT_ADD_FAILED
        802 => c"Event update failed",                // SW_ERROR_EVENT_UPDATE_FAILED
        803 => c"Event unknown data",                 // SW_ERROR_EVENT_UNKNOWN_DATA
        1001 => c"Session closed by server",          // SW_ERROR_SESSION_CLOSED_BY_SERVER
        1002 => c"Session closed by client",          // SW_ERROR_SESSION_CLOSED_BY_CLIENT
        1003 => c"Session closing",                   // SW_ERROR_SESSION_CLOSING
        1004 => c"Session closed",                    // SW_ERROR_SESSION_CLOSED
        1005 => c"Session not exist",                 // SW_ERROR_SESSION_NOT_EXIST
        1006 => c"Session invalid id",                // SW_ERROR_SESSION_INVALID_ID
        1007 => c"Session discard timeout data",      // SW_ERROR_SESSION_DISCARD_TIMEOUT_DATA
        1008 => c"Session discard data",              // SW_ERROR_SESSION_DISCARD_DATA
        1009 => c"Output buffer overflow",            // SW_ERROR_OUTPUT_BUFFER_OVERFLOW
        1010 => c"Output send yield",                 // SW_ERROR_OUTPUT_SEND_YIELD
        1011 => c"SSL not ready",                     // SW_ERROR_SSL_NOT_READY
        1012 => c"SSL cannot use senfile",            // SW_ERROR_SSL_CANNOT_USE_SENFILE
        1013 => c"SSL empty peer certificate",        // SW_ERROR_SSL_EMPTY_PEER_CERTIFICATE
        1014 => c"SSL verify failed",                 // SW_ERROR_SSL_VERIFY_FAILED
        1015 => c"SSL bad client",                    // SW_ERROR_SSL_BAD_CLIENT
        1016 => c"SSL bad protocol",                  // SW_ERROR_SSL_BAD_PROTOCOL
        1017 => c"SSL reset",                         // SW_ERROR_SSL_RESET
        1018 => c"SSL handshake failed",              // SW_ERROR_SSL_HANDSHAKE_FAILED
        1019 => c"SSL create context failed",         // SW_ERROR_SSL_CREATE_CONTEXT_FAILED
        1020 => c"SSL create session failed",         // SW_ERROR_SSL_CREATE_SESSION_FAILED
        1201 => c"Package length too large",          // SW_ERROR_PACKAGE_LENGTH_TOO_LARGE
        1202 => c"Package length not found",          // SW_ERROR_PACKAGE_LENGTH_NOT_FOUND
        1203 => c"Data length too large",             // SW_ERROR_DATA_LENGTH_TOO_LARGE
        1204 => c"Package malformed data",            // SW_ERROR_PACKAGE_MALFORMED_DATA
        2001 => c"Task package too big",              // SW_ERROR_TASK_PACKAGE_TOO_BIG
        2002 => c"Task dispatch fail",                // SW_ERROR_TASK_DISPATCH_FAIL
        2003 => c"Task timeout",                      // SW_ERROR_TASK_TIMEOUT
        3001 => c"Http2 stream id too big",           // SW_ERROR_HTTP2_STREAM_ID_TOO_BIG
        3002 => c"Http2 stream no header",            // SW_ERROR_HTTP2_STREAM_NO_HEADER
        3003 => c"Http2 stream not found",            // SW_ERROR_HTTP2_STREAM_NOT_FOUND
        3004 => c"Http2 stream ignore",               // SW_ERROR_HTTP2_STREAM_IGNORE
        3005 => c"Http2 send control frame failed",   // SW_ERROR_HTTP2_SEND_CONTROL_FRAME_FAILED
        3006 => c"Http2 internal error",              // SW_ERROR_HTTP2_INTERNAL_ERROR
        4001 => c"Aio bad request",                   // SW_ERROR_AIO_BAD_REQUEST
        4002 => c"Aio canceled",                      // SW_ERROR_AIO_CANCELED
        4003 => c"Aio timeout",                       // SW_ERROR_AIO_TIMEOUT
        5001 => c"Client no connection",              // SW_ERROR_CLIENT_NO_CONNECTION
        6001 => c"Socket closed",                     // SW_ERROR_SOCKET_CLOSED
        6002 => c"Socket poll timeout",               // SW_ERROR_SOCKET_POLL_TIMEOUT
        6003 => c"Socket not exists",                 // SW_ERROR_SOCKET_NOT_EXISTS
        7001 => c"Socks5 unsupport version",          // SW_ERROR_SOCKS5_UNSUPPORT_VERSION
        7002 => c"Socks5 unsupport method",           // SW_ERROR_SOCKS5_UNSUPPORT_METHOD
        7003 => c"Socks5 auth failed",                // SW_ERROR_SOCKS5_AUTH_FAILED
        7004 => c"Socks5 server error",               // SW_ERROR_SOCKS5_SERVER_ERROR
        7005 => c"Socks5 handshake failed",           // SW_ERROR_SOCKS5_HANDSHAKE_FAILED
        7006 => c"Socks5 connect failed",             // SW_ERROR_SOCKS5_CONNECT_FAILED
        7101 => c"Http proxy handshake error",        // SW_ERROR_HTTP_PROXY_HANDSHAKE_ERROR
        7102 => c"Http invalid protocol",             // SW_ERROR_HTTP_INVALID_PROTOCOL
        7103 => c"Http proxy handshake failed",       // SW_ERROR_HTTP_PROXY_HANDSHAKE_FAILED
        7104 => c"Http proxy bad response",           // SW_ERROR_HTTP_PROXY_BAD_RESPONSE
        7105 => c"Http conflict header",              // SW_ERROR_HTTP_CONFLICT_HEADER
        7106 => c"Http context unavailable",          // SW_ERROR_HTTP_CONTEXT_UNAVAILABLE
        7107 => c"Http cookie unavailable",           // SW_ERROR_HTTP_COOKIE_UNAVAILABLE
        8501 => c"Websocket bad client",              // SW_ERROR_WEBSOCKET_BAD_CLIENT
        8502 => c"Websocket bad opcode",              // SW_ERROR_WEBSOCKET_BAD_OPCODE
        8503 => c"Websocket unconnected",             // SW_ERROR_WEBSOCKET_UNCONNECTED
        8504 => c"Websocket handshake failed",        // SW_ERROR_WEBSOCKET_HANDSHAKE_FAILED
        8505 => c"Websocket pack failed",             // SW_ERROR_WEBSOCKET_PACK_FAILED
        8506 => c"Websocket unpack failed",           // SW_ERROR_WEBSOCKET_UNPACK_FAILED
        8507 => c"Websocket incomplete packet",       // SW_ERROR_WEBSOCKET_INCOMPLETE_PACKET
        9001 => c"Server must created before client", // SW_ERROR_SERVER_MUST_CREATED_BEFORE_CLIENT
        9002 => c"Server too many socket",            // SW_ERROR_SERVER_TOO_MANY_SOCKET
        9003 => c"Server worker terminated",          // SW_ERROR_SERVER_WORKER_TERMINATED
        9004 => c"Server invalid listen port",        // SW_ERROR_SERVER_INVALID_LISTEN_PORT
        9005 => c"Server too many listen port",       // SW_ERROR_SERVER_TOO_MANY_LISTEN_PORT
        9006 => c"Server pipe buffer full",           // SW_ERROR_SERVER_PIPE_BUFFER_FULL
        9007 => c"Server no idle worker",             // SW_ERROR_SERVER_NO_IDLE_WORKER
        9008 => c"Server only start one",             // SW_ERROR_SERVER_ONLY_START_ONE
        9009 => c"Server send in master",             // SW_ERROR_SERVER_SEND_IN_MASTER
        9010 => c"Server invalid request",            // SW_ERROR_SERVER_INVALID_REQUEST
        9011 => c"Server connect fail",               // SW_ERROR_SERVER_CONNECT_FAIL
        9012 => c"Server invalid command",            // SW_ERROR_SERVER_INVALID_COMMAND
        9013 => c"Server is not regular file",        // SW_ERROR_SERVER_IS_NOT_REGULAR_FILE
        9014 => c"Server send to woker timeout",      // SW_ERROR_SERVER_SEND_TO_WOKER_TIMEOUT
        9015 => c"Server invalid callback",           // SW_ERROR_SERVER_INVALID_CALLBACK
        9016 => c"Server unrelated thread",           // SW_ERROR_SERVER_UNRELATED_THREAD
        9101 => c"Server worker exit timeout",        // SW_ERROR_SERVER_WORKER_EXIT_TIMEOUT
        9102 => c"Server worker abnormal pipe data",  // SW_ERROR_SERVER_WORKER_ABNORMAL_PIPE_DATA
        9103 => c"Server worker unprocessed data",    // SW_ERROR_SERVER_WORKER_UNPROCESSED_DATA
        10001 => c"Coroutine out of coroutine",       // SW_ERROR_CO_OUT_OF_COROUTINE
        10002 => c"Coroutine has been bound",         // SW_ERROR_CO_HAS_BEEN_BOUND
        10003 => c"Coroutine has been discarded",     // SW_ERROR_CO_HAS_BEEN_DISCARDED
        10004 => c"Coroutine mutex double unlock",    // SW_ERROR_CO_MUTEX_DOUBLE_UNLOCK
        10005 => c"Coroutine block object locked",    // SW_ERROR_CO_BLOCK_OBJECT_LOCKED
        10006 => c"Coroutine block object waiting",   // SW_ERROR_CO_BLOCK_OBJECT_WAITING
        10007 => c"Coroutine yield failed",           // SW_ERROR_CO_YIELD_FAILED
        10008 => c"Coroutine getcontext failed",      // SW_ERROR_CO_GETCONTEXT_FAILED
        10009 => c"Coroutine swapcontext failed",     // SW_ERROR_CO_SWAPCONTEXT_FAILED
        10010 => c"Coroutine makecontext failed",     // SW_ERROR_CO_MAKECONTEXT_FAILED
        10011 => c"Coroutine iocpinit failed",        // SW_ERROR_CO_IOCPINIT_FAILED
        10012 => c"Coroutine protect stack failed",   // SW_ERROR_CO_PROTECT_STACK_FAILED
        10013 => c"Coroutine std thread link error",  // SW_ERROR_CO_STD_THREAD_LINK_ERROR
        10014 => c"Coroutine disabled multi thread",  // SW_ERROR_CO_DISABLED_MULTI_THREAD
        10015 => c"Coroutine cannot cancel",          // SW_ERROR_CO_CANNOT_CANCEL
        10016 => c"Coroutine not exists",             // SW_ERROR_CO_NOT_EXISTS
        10017 => c"Coroutine canceled",               // SW_ERROR_CO_CANCELED
        10018 => c"Coroutine timedout",               // SW_ERROR_CO_TIMEDOUT
        10019 => c"Coroutine socket close wait",      // SW_ERROR_CO_SOCKET_CLOSE_WAIT
        _ => return std::ptr::null(),
    }
    .as_ptr()
}

/// Return an immutable process-lifetime message, never to be freed; unknown is null.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_error_message(code: i32) -> *const c_char {
    known_message(code)
}

/// Resolve known codes, invoking an optional nonthrowing native formatter only on misses.
/// The formatter must not enter Zend, retain Rust state, or unwind through this frame.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_error_resolve(
    code: i32,
    fallback: Option<extern "C" fn(i32) -> *const c_char>,
) -> *const c_char {
    let known = known_message(code);
    if known.is_null() {
        fallback.map_or(std::ptr::null(), |format| format(code))
    } else {
        known
    }
}

/// Resolve system, known and unknown errors without heap allocation.
/// # Safety
/// Calls which return the mutable unknown-message buffer must be externally
/// serialized, as in the original snprintf buffer. Known-message calls are pure.
/// The optional system formatter must not unwind, enter Zend or retain Rust state.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_error_strerror(
    code: i32,
    system: Option<extern "C" fn(i32) -> *const c_char>,
) -> *const c_char {
    use std::io::Write;
    static mut UNKNOWN: [u8; 32] = [0; 32];
    if code < 500 {
        return system.map_or(std::ptr::null(), |format| format(code));
    }
    let known = known_message(code);
    if !known.is_null() {
        return known;
    }
    // SAFETY: The caller serializes unknown-message use. No mutable reference
    // survives this call; the C-string pointer and storage lifetime match upstream.
    let buffer = unsafe { &mut *std::ptr::addr_of_mut!(UNKNOWN) };
    let mut remaining = &mut buffer[..31];
    let colon = if cfg!(target_vendor = "apple") {
        ":"
    } else {
        ""
    };
    // The longest prefix + int32 decimal representation is 26 bytes including NUL.
    if write!(remaining, "Unknown error{colon} {code}").is_err() {
        return std::ptr::null();
    }
    let used = 31 - remaining.len();
    buffer[used] = 0;
    buffer.as_ptr().cast()
}
