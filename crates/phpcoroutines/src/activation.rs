//! Ordered first activation policy; all native effects happen between plan steps.
/// # Safety
/// Cursor is exclusive writable native stack POD, initially zeroed. Each scalar
/// observation is freshly supplied for the last request; no native pointer enters.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcoroutines_activation(stage: *mut u32, observation: u8) -> u32 {
    let stage = unsafe { &mut *stage };
    loop {
        let current = *stage;
        *stage = current.saturating_add(1);
        return match current {
            0 => 1, // activated
            1 if observation != 0 => {
                *stage = 99;
                0
            }
            1 => 2,                     // library lookup
            2 if observation != 0 => 3, // library truth conversion
            2 => {
                *stage = 4;
                4
            } // missing library: load
            3 if observation == 0 => 4,
            3 => continue,
            4 => 5,                     // reactor/init interrupt binding
            5 => 6,                     // global preemption
            6 if observation == 0 => 7, // local preemption only on false global
            6 => {
                *stage = 8;
                8
            }
            7 if observation != 0 => 8,
            7 => continue,
            8 => 9,                      // main thread
            9 if observation != 0 => 10, // hook flags
            9 => {
                *stage = 12;
                continue;
            }
            10 if observation != 0 => 11, // native enable hooks
            10 => continue,
            11 => 12, // native unsafe-function binding
            12 => {
                *stage = 99;
                13
            } // publish callbacks + activated
            _ => {
                *stage = 99;
                0
            }
        };
    }
}
