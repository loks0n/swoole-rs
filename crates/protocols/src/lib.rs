//! Packet codecs and protocol decisions. All native I/O, allocation callbacks,
//! connection storage and PHP execution happen after these calls return.
mod bus;
mod mqtt;
mod pool;
mod redis;
mod reply;
mod socks;
pub use bus::*;
pub use mqtt::*;
pub use pool::*;
pub use redis::*;
pub use reply::*;
pub use socks::*;

/// # Safety
/// A non-null pointer covers `length` readable bytes borrowed for this call.
unsafe fn input<'a>(data: *const u8, length: usize) -> Option<&'a [u8]> {
    if length > isize::MAX as usize || (data.is_null() && length != 0) {
        None
    } else if length == 0 {
        Some(&[])
    } else {
        Some(unsafe { std::slice::from_raw_parts(data, length) })
    }
}

/// # Safety
/// Output covers capacity exclusive writable bytes and is disjoint from inputs.
unsafe fn output<'a>(data: *mut u8, capacity: usize, required: usize) -> Option<&'a mut [u8]> {
    if data.is_null() || capacity > isize::MAX as usize || capacity < required {
        None
    } else {
        Some(unsafe { std::slice::from_raw_parts_mut(data, required) })
    }
}
