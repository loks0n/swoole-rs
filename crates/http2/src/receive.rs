//! Server DATA effect selection; native shared ownership/buffers/callbacks stay outside.
use crate::sw_rs_http2_data_rejected;

#[repr(C)]
pub struct Http2ReceiveFacts {
    pub length: usize,
    pub buffered_length: usize,
    pub maximum: u32,
    pub ended: u32,
    pub end_stream: u32,
    pub parse_body: u32,
    pub form: u32,
    pub multipart: u32,
}

pub mod receive_action {
    pub const START: u32 = 0;
    pub const CONTEXT: u32 = 1;
    pub const BUFFER: u32 = 2;
    pub const RESET: u32 = 3;
    pub const REMOVE: u32 = 4;
    pub const APPEND: u32 = 5;
    pub const FLOW: u32 = 6;
    pub const LENGTH: u32 = 7;
    pub const END_BUFFER: u32 = 8;
    pub const FORM: u32 = 9;
    pub const MULTIPART: u32 = 10;
    pub const HANDLE: u32 = 11;
    pub const WARN: u32 = 12;
    pub const ERROR: u32 = 13;
    pub const DONE: u32 = 14;
}

/// # Safety
/// `facts` points to a readable copied snapshot, not modified during this call.
#[no_mangle]
pub unsafe extern "C" fn sw_rs_http2_receive_next(
    stage: u32,
    success: u32,
    facts: *const Http2ReceiveFacts,
) -> u32 {
    use receive_action::*;
    let facts = &*facts;
    let finish = || if facts.end_stream != 0 { LENGTH } else { DONE };
    match stage {
        START => {
            if success != 0 {
                CONTEXT
            } else {
                WARN
            }
        }
        CONTEXT => {
            if facts.length != 0 {
                BUFFER
            } else {
                finish()
            }
        }
        BUFFER => {
            if sw_rs_http2_data_rejected(
                facts.buffered_length,
                facts.length,
                facts.maximum,
                facts.ended,
            ) != 0
            {
                RESET
            } else {
                APPEND
            }
        }
        RESET => REMOVE,
        APPEND => FLOW,
        FLOW => finish(),
        LENGTH => {
            if success != 0 {
                END_BUFFER
            } else {
                HANDLE
            }
        }
        END_BUFFER if facts.parse_body != 0 && facts.form != 0 => FORM,
        END_BUFFER if facts.multipart != 0 => MULTIPART,
        END_BUFFER | FORM => HANDLE,
        MULTIPART => {
            if success != 0 {
                HANDLE
            } else {
                ERROR
            }
        }
        REMOVE | HANDLE => DONE,
        _ => ERROR,
    }
}
