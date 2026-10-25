//! Connection decisions over copied outcomes; socket/PHP/HPACK effects remain native.
pub mod connection_action {
    pub const START: u32 = 0;
    pub const CREATE: u32 = 1;
    pub const SETUP: u32 = 2;
    pub const SSL: u32 = 3;
    pub const PROTOCOL: u32 = 4;
    pub const CONNECT: u32 = 5;
    pub const RESET: u32 = 6;
    pub const INFLATE: u32 = 7;
    pub const DEFLATE: u32 = 8;
    pub const PREFACE: u32 = 9;
    pub const SETTINGS: u32 = 10;
    pub const PUBLISH: u32 = 11;
    pub const IO_ERROR: u32 = 12;
    pub const INFLATE_ERROR: u32 = 13;
    pub const DEFLATE_ERROR: u32 = 14;
    pub const CLOSE: u32 = 15;
    pub const ALREADY: u32 = 16;
    pub const CREATE_ERROR: u32 = 17;
    pub const FALSE: u32 = 18;
    pub const TRUE: u32 = 19;
    pub const CLOSE_START: u32 = 20;
    pub const DISCONNECT: u32 = 21;
    pub const NO_SOCKET: u32 = 22;
    pub const CLOSE_SOCKET: u32 = 23;
    pub const CLOSE_ERROR: u32 = 24;
}

/// `outcome` is the previous native result. `detail` is read only at START
/// (socket present) and SETUP (fresh SSL requirement). No native identity escapes.
#[no_mangle]
pub extern "C" fn sw_rs_http2_connection_next(stage: u32, outcome: u32, detail: u32) -> u32 {
    use connection_action::*;
    match stage {
        START => {
            if detail != 0 {
                ALREADY
            } else {
                CREATE
            }
        }
        CREATE => {
            if outcome != 0 {
                SETUP
            } else {
                CREATE_ERROR
            }
        }
        SETUP => {
            if detail != 0 {
                SSL
            } else {
                PROTOCOL
            }
        }
        SSL | CONNECT if outcome == 0 => IO_ERROR,
        SSL => PROTOCOL,
        PROTOCOL => CONNECT,
        CONNECT => RESET,
        RESET => INFLATE,
        INFLATE => {
            if outcome != 0 {
                DEFLATE
            } else {
                INFLATE_ERROR
            }
        }
        DEFLATE => {
            if outcome != 0 {
                PREFACE
            } else {
                DEFLATE_ERROR
            }
        }
        PREFACE => {
            if outcome != 0 {
                SETTINGS
            } else {
                CLOSE
            }
        }
        SETTINGS => {
            if outcome != 0 {
                PUBLISH
            } else {
                CLOSE
            }
        }
        IO_ERROR | INFLATE_ERROR | DEFLATE_ERROR => CLOSE,
        PUBLISH => TRUE,
        CLOSE_START => {
            if outcome != 0 {
                DISCONNECT
            } else {
                NO_SOCKET
            }
        }
        DISCONNECT => CLOSE_SOCKET,
        CLOSE_SOCKET => {
            if outcome != 0 {
                TRUE
            } else {
                CLOSE_ERROR
            }
        }
        _ => FALSE,
    }
}
