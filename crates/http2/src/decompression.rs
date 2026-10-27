//! Native zlib/String execution follows each returned plan; no buffer borrow crosses it.
#[repr(C)]
pub struct Http2DecompressPlan {
    pub publish_length: u32,
    pub action: u32,
}

/// # Safety
/// `out` points to writable storage for one plan. Zlib status values are the
/// pinned `Z_OK=0/Z_STREAM_END=1` contract; other statuses retain native errors.
#[no_mangle]
pub unsafe extern "C" fn sw_rs_http2_decompress_plan(
    after_extend: u32,
    status: i32,
    total_out: usize,
    capacity: usize,
    available_input: u32,
    out: *mut Http2DecompressPlan,
) {
    // Native extension can change stream input facts; query them again after return.
    let action = if after_extend != 0 {
        if available_input == 0 {
            1
        } else {
            2
        }
    } else {
        match status {
            1 => 1,
            0 if total_out.wrapping_add(4096) >= capacity => 3,
            0 if available_input == 0 => 1,
            0 => 2,
            _ => 0,
        }
    };
    out.write(Http2DecompressPlan {
        publish_length: u32::from(after_extend == 0 && status >= 0),
        action,
    });
}
