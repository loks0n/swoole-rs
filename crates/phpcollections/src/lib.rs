//! PHP `Swoole\Coroutine\Channel` (with the `php` feature, see docs/zend.md),
//! and `Swoole\Table` decisions over copied metadata, whose native storage and
//! effects remain in the C++ facade.
#![cfg_attr(
    not(test),
    deny(
        clippy::undocumented_unsafe_blocks,
        clippy::multiple_unsafe_ops_per_block
    )
)]

#[cfg(feature = "php")]
mod channel;
#[cfg(feature = "php")]
pub use channel::*;

/// Native `TableColumn` tags are pinned and checked by the native adapter.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_phpcollections_kind(kind: i64) -> u32 {
    match kind {
        1 => 1,
        2 => 2,
        3 => 3,
        _ => 0,
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_phpcollections_string_invalid(kind: i64, size: i64) -> u8 {
    u8::from(kind == 3 && size < 1)
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_phpcollections_key_warning(length: usize, limit: usize) -> u8 {
    u8::from(length >= limit)
}

/// Native count and column size use `size_t`; multiplication has unsigned wrap.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_phpcollections_count(mode: isize, rows: usize, columns: usize) -> usize {
    if mode == 0 {
        rows
    } else {
        rows.wrapping_mul(columns)
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_phpcollections_clear_cell(present: u8, is_null: u8) -> u8 {
    u8::from(present == 0 || is_null != 0)
}

/// 0 missing, 1 individual field, 2 full row; no pointer crosses the ABI.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_phpcollections_get_action(row: u8, field: u8) -> u32 {
    if row == 0 {
        0
    } else if field != 0 {
        1
    } else {
        2
    }
}

/// Operands are copied only after native Zend conversion. Row storage and return
/// publication happen after this call; no signed integer overflow is redefined.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_phpcollections_float_update(value: f64, amount: f64, subtract: u8) -> f64 {
    if subtract != 0 {
        value - amount
    } else {
        value + amount
    }
}

/// Compute only the native signed-long defined arithmetic domain.
///
/// # Safety
/// A non-null output points to one writable, aligned native long for this call.
/// On overflow or null output, no write occurs and the caller retains its native
/// undefined-domain operation; this is not an overflow behavior correction.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_phpcollections_integer_update(
    value: core::ffi::c_long,
    amount: core::ffi::c_long,
    subtract: u8,
    output: *mut core::ffi::c_long,
) -> u8 {
    let result = if subtract != 0 {
        value.checked_sub(amount)
    } else {
        value.checked_add(amount)
    };
    match result {
        Some(result) if !output.is_null() => {
            // SAFETY: caller supplies an aligned writable scalar, borrowed only here.
            unsafe {
                output.write(result);
            }
            1
        }
        _ => 0,
    }
}

/// Select a single field write from freshly copied column/value metadata.
/// New rows clear absent/null fields; updates convert explicit null normally.
/// Native conversion, storage and string release execute after this call.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_phpcollections_write_action(
    kind: i64,
    initialize: u8,
    present: u8,
    is_null: u8,
) -> u32 {
    if initialize != 0 && (present == 0 || is_null != 0) {
        0 // clear newly allocated cell
    } else {
        match kind {
            3 => 3, // string conversion/store/release
            2 => 2, // double conversion/store
            _ => 1, // original integer fallback, including unknown tags
        }
    }
}

/// Whole per-value effect sequence, low byte first. Operations:1 single-field
/// read,2 array materialization,3 write. Fresh copied facts select the sequence;
/// every row/Zend conversion/materialization/store/release runs after return.
/// No pointer, name, native value or iterator is retained by this call.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_phpcollections_value_plan(
    operation: u32,
    kind: i64,
    column: u8,
    initialize: u8,
    present: u8,
    is_null: u8,
) -> u64 {
    let actions: &[u8] = match operation {
        1 if column == 0 => &[1], // missing field returns false
        1 | 2 => match (kind, operation) {
            (1, 1) => &[2, 5], // read native long, publish scalar
            (2, 1) => &[3, 6],
            (3, 1) => &[4, 7],
            (1, 2) => &[2, 8], // read native long, insert current column name
            (2, 2) => &[3, 9],
            (3, 2) => &[4, 10],
            _ => &[11], // native invariant abort, not a behavior correction
        },
        3 if initialize != 0 && (present == 0 || is_null != 0) => &[12],
        3 => match kind {
            3 => &[15, 18, 19], // convert string, store, release native temporary
            2 => &[14, 17],
            _ => &[13, 16], // exact original integer fallback
        },
        _ => &[],
    };
    actions.iter().enumerate().fold(0, |plan, (index, action)| {
        plan | (u64::from(*action) << (index * 8))
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn value_sequences_preserve_complete_native_effect_order() {
        for kind in [-1, 0, 1, 2, 3, 77] {
            for operation in [1, 2] {
                let expected = match (operation, kind) {
                    (1, 1) => 2 | (5 << 8),
                    (1, 2) => 3 | (6 << 8),
                    (1, 3) => 4 | (7 << 8),
                    (2, 1) => 2 | (8 << 8),
                    (2, 2) => 3 | (9 << 8),
                    (2, 3) => 4 | (10 << 8),
                    _ => 11,
                };
                assert_eq!(
                    swr_v1_phpcollections_value_plan(operation, kind, 1, 0, 0, 0),
                    expected
                );
            }
            assert_eq!(swr_v1_phpcollections_value_plan(1, kind, 0, 0, 0, 0), 1);
            for initialize in [0, 1, 255] {
                for present in [0, 1, 255] {
                    for null in [0, 1, 255] {
                        let expected = if initialize != 0 && (present == 0 || null != 0) {
                            12
                        } else {
                            match kind {
                                3 => 15 | (18 << 8) | (19 << 16),
                                2 => 14 | (17 << 8),
                                _ => 13 | (16 << 8),
                            }
                        };
                        assert_eq!(
                            swr_v1_phpcollections_value_plan(3, kind, 1, initialize, present, null),
                            expected
                        );
                    }
                }
            }
        }
        assert_eq!(swr_v1_phpcollections_value_plan(0, 1, 1, 0, 1, 0), 0);
    }

    #[test]
    fn constructors_and_types() {
        for kind in -8..16 {
            assert_eq!(
                swr_v1_phpcollections_kind(kind),
                if (1..=3).contains(&kind) {
                    u32::try_from(kind).expect("1..=3 fits u32")
                } else {
                    0
                }
            );
            for size in [i64::MIN, -1, 0, 1, i64::MAX] {
                assert_eq!(
                    swr_v1_phpcollections_string_invalid(kind, size),
                    u8::from(kind == 3 && size < 1)
                );
            }
        }
    }
    #[test]
    fn binary_lengths_counts_and_optional_values() {
        for n in [0, 1, 63, 64, usize::MAX] {
            assert_eq!(swr_v1_phpcollections_key_warning(n, 64), u8::from(n >= 64));
            for cols in [0, 1, 7, usize::MAX] {
                assert_eq!(swr_v1_phpcollections_count(0, n, cols), n);
                assert_eq!(
                    swr_v1_phpcollections_count(-1, n, cols),
                    n.wrapping_mul(cols)
                );
            }
        }
        for row in 0..=1 {
            for field in 0..=1 {
                assert_eq!(
                    swr_v1_phpcollections_get_action(row, field),
                    if row == 0 {
                        0
                    } else if field != 0 {
                        1
                    } else {
                        2
                    }
                );
                assert_eq!(
                    swr_v1_phpcollections_clear_cell(row, field),
                    u8::from(row == 0 || field != 0)
                );
            }
        }
    }
}
