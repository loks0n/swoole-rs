//! Proposal-only concrete Rust header store; no production ABI/activation.
#![allow(clippy::missing_safety_doc)]
use std::alloc::{Layout, alloc, dealloc};
use std::{ptr, slice};
struct Row { key: Vec<u8>, value: Vec<u8> }
#[derive(Default)]
pub struct HeaderStore { rows: Vec<Row>, phase: u32 }
#[repr(C)]
pub struct Sizes { key: usize, value: usize }
unsafe fn bytes<'a>(p: *const u8, n: usize) -> Option<&'a [u8]> {
    if n == 0 { Some(&[]) } else if p.is_null() || n > isize::MAX as usize { None }
    else { Some(unsafe { slice::from_raw_parts(p, n) }) }
}
fn copy(source: &[u8]) -> Result<Vec<u8>, ()> {
    let mut v = Vec::new(); v.try_reserve(source.len()).map_err(|_| ())?;
    v.extend_from_slice(source); Ok(v)
}
#[unsafe(no_mangle)]
pub extern "C" fn model_headers_new() -> *mut HeaderStore {
    let p = unsafe { alloc(Layout::new::<HeaderStore>()).cast::<HeaderStore>() };
    if !p.is_null() { unsafe { p.write(HeaderStore::default()) }; } p
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn model_headers_free(p: *mut HeaderStore) {
    if !p.is_null() { unsafe { ptr::drop_in_place(p); dealloc(p.cast(), Layout::new::<HeaderStore>()); } }
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn model_headers_set(p: *mut HeaderStore, k: *const u8, kn: usize, v: *const u8, vn: usize) -> i32 {
    let (Some(s), Some(k), Some(v)) = (unsafe { p.as_mut() }, unsafe { bytes(k,kn) }, unsafe { bytes(v,vn) }) else {return -1;};
    if s.phase != 0 { return -2; }
    // Retain every ordered publication, including duplicates. Replaying them
    // preserves native value capacities as well as last-value and bucket order.
    if s.rows.try_reserve(1).is_err() {return -1;}
    let (Ok(key), Ok(value)) = (copy(k), copy(v)) else {return -1;};
    s.rows.push(Row {key,value}); 0
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn model_headers_prepare(p: *mut HeaderStore) -> usize {
    let Some(s) = (unsafe { p.as_mut() }) else {return usize::MAX;};
    if s.phase != 0 {return usize::MAX;}
    s.phase=1; s.rows.len()
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn model_headers_sizes(p: *const HeaderStore, index: usize, out: *mut Sizes) -> i32 {
    let (Some(s),Some(out)) = (unsafe {p.as_ref()},unsafe {out.as_mut()}) else {return -1;};
    if s.phase != 1 {return -2;}
    let Some(row)=s.rows.get(index) else {return -1;};
    *out=Sizes{key:row.key.len(),value:row.value.len()}; 0
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn model_headers_copy(p: *const HeaderStore, index: usize, k: *mut u8, kn: usize, v: *mut u8, vn: usize) -> i32 {
    let Some(s)=(unsafe {p.as_ref()}) else {return -1;};
    if s.phase != 1 {return -2;}
    let Some(row)=s.rows.get(index) else {return -1;};
    if kn != row.key.len() || vn != row.value.len() || (kn != 0 && k.is_null()) || (vn != 0 && v.is_null()) {return -1;}
    // Native allocates disjoint output strings before this call. No pointer escapes.
    if kn != 0 {unsafe {ptr::copy_nonoverlapping(row.key.as_ptr(),k,kn)};}
    if vn != 0 {unsafe {ptr::copy_nonoverlapping(row.value.as_ptr(),v,vn)};}
    0
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn model_headers_commit(p: *mut HeaderStore) -> i32 {
    let Some(s)=(unsafe {p.as_mut()}) else {return -1;};
    if s.phase != 1 {return -2;}
    s.rows.clear(); s.phase=2; 0
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn model_headers_owned_entries(p: *const HeaderStore) -> usize {
    unsafe {p.as_ref()}.map_or(usize::MAX,|s|s.rows.len())
}
