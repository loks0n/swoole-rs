//! Sole inline Coroutine identity words. Native owns every pointed-to object,
//! thread-local scope and effect; only coupled publication happens here.
use std::ffi::c_void;

#[repr(C)]
pub struct CoroutineIdentity {
    pub token: *mut c_void,
}

/// # Safety
/// Cell is initialized readable storage, serialized as the original pointer.
/// The copied token is never interpreted or dereferenced in Rust.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_coroutine_identity_read(
    cell: *const CoroutineIdentity,
) -> *mut c_void {
    unsafe { (*cell).token }
}

/// # Safety
/// Cell is writable storage without racing access. Original initialization or
/// publication happens at this call; no prior contents/pointee are accessed.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_coroutine_identity_publish(
    cell: *mut CoroutineIdentity,
    token: *mut c_void,
) {
    unsafe { cell.write(CoroutineIdentity { token }) };
}

/// Whole current/origin routing at the original lifecycle publication barriers.
/// ENTER copies current into origin, then publishes self as current. LEAVE
/// refreshes origin after Native effects, then restores current. No context,
/// function, clock or callback effect happens while this frame is live.
/// # Safety
/// Current and origin are distinct live initialized exclusive pointer cells in
/// the calling Native thread's original scope. Tokens remain Native-owned.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_coroutine_identity_route(
    current: *mut CoroutineIdentity,
    origin: *mut CoroutineIdentity,
    own: *mut c_void,
    operation: u32,
) {
    match operation {
        0 => unsafe {
            let parent = (*current).token;
            origin.write(CoroutineIdentity { token: parent });
            current.write(CoroutineIdentity { token: own });
        },
        1 => unsafe {
            let parent = (*origin).token;
            current.write(CoroutineIdentity { token: parent });
        },
        _ => {}
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::mem::MaybeUninit;
    use std::ptr;

    #[test]
    fn coupled_publication_refreshes_tokens_without_touching_native_objects() {
        let mut a = 1_u8;
        let mut b = 2_u8;
        let mut c = 3_u8;
        let a = ptr::from_mut(&mut a).cast();
        let b = ptr::from_mut(&mut b).cast();
        let c = ptr::from_mut(&mut c).cast();
        let mut current = CoroutineIdentity { token: a };
        let mut origin = CoroutineIdentity {
            token: ptr::null_mut(),
        };
        let mut task = MaybeUninit::<CoroutineIdentity>::uninit();
        unsafe {
            swr_v1_coroutine_identity_publish(task.as_mut_ptr(), b);
            assert_eq!(swr_v1_coroutine_identity_read(task.as_ptr()), b);
            swr_v1_coroutine_identity_route(&raw mut current, &raw mut origin, b, 0);
            assert_eq!((current.token, origin.token), (b, a));
            // An external Native effect may replace the original parent. LEAVE
            // observes that new identity, rather than a pre-effect snapshot.
            swr_v1_coroutine_identity_publish(&raw mut origin, c);
            swr_v1_coroutine_identity_route(&raw mut current, &raw mut origin, b, 1);
            assert_eq!((current.token, origin.token), (c, c));
            swr_v1_coroutine_identity_route(ptr::null_mut(), ptr::null_mut(), b, 2);
            swr_v1_coroutine_identity_publish(task.as_mut_ptr(), ptr::null_mut());
            assert!(swr_v1_coroutine_identity_read(task.as_ptr()).is_null());
        }
        assert_eq!(
            std::mem::size_of::<CoroutineIdentity>(),
            std::mem::size_of::<*mut c_void>()
        );
        assert_eq!(
            std::mem::align_of::<CoroutineIdentity>(),
            std::mem::align_of::<*mut c_void>()
        );
    }
}
