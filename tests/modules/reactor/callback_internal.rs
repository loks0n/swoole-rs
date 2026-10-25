//! Actual prior/current Rust bodies; Native payload identities remain integers.
#[path = "owner.rs"]
mod owner;
#[path = "baseline.rs"]
mod baseline;
#[path = "selected.rs"]
mod selected;

macro_rules! observe {
    ($api:ident, $count:expr) => {{
        use $api::*;
        let mut owner = std::ptr::null_mut();
        let mut copy = std::ptr::null_mut();
        let mut output = 0;
        let mut trace = Vec::new();
        for kind in 0..2 {
            for index in 0..$count {
                let key = ((index * 19) % 71) as i32 - 35;
                let candidate = 1000 + kind as usize * 100 + index;
                for candidate in [0, candidate, 0] {
                    let status = unsafe {
                        swr_v1_reactor_callbacks_ensure(
                            &mut owner, kind, key, candidate, &mut output,
                        )
                    };
                    trace.extend([status as i64, output as i64]);
                }
                let status = unsafe {
                    swr_v1_reactor_callbacks_insert(&mut owner, kind, key, 9999, &mut output)
                };
                trace.extend([status as i64, output as i64]);
                let status = unsafe {
                    swr_v1_reactor_callbacks_lookup(owner, kind, key, &mut output)
                };
                trace.extend([status as i64, output as i64]);
            }
        }
        let mut state = ReactorCallbackCopy::default();
        loop {
            let status = unsafe {
                swr_v1_reactor_callbacks_copy_next(owner, &mut state, &mut output)
            };
            trace.extend([status as i64, output as i64, state.cursor.key as i64]);
            if status == 0 { break; }
            assert!((1..=2).contains(&status));
            let status = unsafe {
                swr_v1_reactor_callbacks_insert(
                    &mut copy, state.kind, state.cursor.key, output, &mut output,
                )
            };
            assert_eq!(status, 1);
        }
        for kind in 0..2 {
            let mut cursor = ReactorCallbackCursor::default();
            loop {
                let status = unsafe {
                    swr_v1_reactor_callbacks_next(copy, kind, &mut cursor, 1, &mut output)
                };
                trace.extend([status as i64, output as i64, cursor.key as i64]);
                if status == 0 { break; }
                assert_eq!(status, 1);
            }
            for index in (0..$count).step_by(2) {
                let key = ((index * 19) % 71) as i32 - 35;
                let status = unsafe {
                    swr_v1_reactor_callbacks_erase(owner, kind, key, &mut output)
                };
                trace.extend([status as i64, output as i64]);
            }
        }
        loop {
            let status = unsafe { swr_v1_reactor_callbacks_clear_next(&mut owner, &mut output) };
            trace.extend([status as i64, output as i64]);
            if status == 0 { break; }
            assert!((1..=2).contains(&status));
        }
        assert!(owner.is_null());
        let mut kind = 0;
        loop {
            let status = unsafe { swr_v1_reactor_callbacks_drain(copy, &mut kind, &mut output) };
            trace.extend([status as i64, kind as i64, output as i64]);
            if status == 0 { break; }
            assert_eq!(status, 1);
        }
        assert_eq!(unsafe { swr_v1_reactor_callbacks_free(copy) }, 0);
        trace
    }};
}

fn main() {
    assert_eq!(std::mem::size_of::<baseline::ReactorCallbacks>(), std::mem::size_of::<selected::ReactorCallbacks>());
    assert_eq!(std::mem::align_of::<baseline::ReactorCallbacks>(), std::mem::align_of::<selected::ReactorCallbacks>());
    let mut observations = 0;
    for count in [0, 1, 3, 17, 65] {
        let baseline = observe!(baseline, count);
        let selected = observe!(selected, count);
        assert_eq!(baseline, selected);
        observations += selected.len();
    }
    println!("{{\"schemas\":5,\"scalar_observations\":{},\"native_effects\":false}}", observations);
}
