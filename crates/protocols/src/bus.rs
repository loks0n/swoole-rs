//! Packet chunking and fairness decisions; native code retains shared-memory
//! headers, socket writes, packet buffers and allocator ownership.
const CHUNK: u8 = 4;
const BEGIN: u8 = 8;
const END: u8 = 16;

#[repr(C)]
#[derive(Clone, Copy, Debug, Default)]
pub struct BusWriter {
    pub remaining: u32,
    pub offset: u32,
    pub maximum: u32,
    pub minimum: u32,
    pub flags: u8,
    pub mode: u8, // 0 empty;1 direct;2 chunks;3 complete.
}
#[repr(C)]
#[derive(Clone, Copy, Debug, Default)]
pub struct BusChunk {
    pub offset: u32,
    pub length: u32,
    pub flags: u8,
    pub mode: u8,
}

impl BusWriter {
    pub fn new(
        length: u32,
        maximum: u32,
        minimum: u32,
        has_payload: bool,
        always: bool,
    ) -> Option<Self> {
        if minimum == 0 || (maximum == 0 && has_payload && length != 0) {
            return None;
        }
        let mut writer = Self {
            remaining: length,
            maximum,
            minimum,
            ..Self::default()
        };
        if !has_payload || length == 0 {
            writer.remaining = 0;
        } else if !always && length <= maximum {
            writer.mode = 1;
        } else {
            writer.mode = 2;
            writer.flags = CHUNK | BEGIN;
        }
        Some(writer)
    }
    pub fn next_chunk(&self) -> BusChunk {
        let length = if self.mode == 2 {
            self.remaining.min(self.maximum)
        } else {
            self.remaining
        };
        BusChunk {
            offset: self.offset,
            length,
            flags: self.flags
                | if self.mode == 2 && self.remaining <= self.maximum {
                    END
                } else {
                    0
                },
            mode: self.mode,
        }
    }
    pub fn complete(&mut self, success: bool, reduce: bool) -> i32 {
        if self.mode > 2
            || (self.maximum == 0 && self.mode != 0)
            || self.offset.checked_add(self.remaining).is_none()
        {
            return -1;
        }
        if !success {
            if !reduce || self.maximum <= self.minimum {
                return -1;
            }
            self.maximum = self.minimum;
            if self.mode == 1 {
                self.mode = 2;
                self.flags = CHUNK | BEGIN;
            } else {
                self.flags &= !END;
            }
            return 1;
        }
        let chunk = self.next_chunk();
        self.flags = chunk.flags & !BEGIN;
        if self.mode == 2 {
            self.remaining -= chunk.length;
            self.offset += chunk.length;
        } else {
            self.remaining = 0;
        }
        if self.remaining == 0 {
            self.mode = 3;
        }
        0
    }
}

/// # Safety
/// Output is aligned/exclusive writable. No allocation or retained pointer.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_bus_writer_init(
    length: u32,
    maximum: u32,
    minimum: u32,
    has_payload: u8,
    always: u8,
    output: *mut BusWriter,
) -> i32 {
    if output.is_null() {
        return -1;
    }
    let Some(writer) = BusWriter::new(length, maximum, minimum, has_payload != 0, always != 0)
    else {
        return -1;
    };
    // SAFETY: `output` is non-null (checked above), aligned and writable per the export's contract.
    unsafe { output.write(writer) };
    0
}
/// # Safety
/// Writer is aligned/initialized/readable, output aligned/writable and disjoint.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_bus_writer_next(
    writer: *const BusWriter,
    output: *mut BusChunk,
) -> i32 {
    if writer.is_null() || output.is_null() {
        return -1;
    }
    // SAFETY: `writer` is non-null (checked above), aligned and initialized per the export's contract.
    let writer = unsafe { writer.read() };
    if writer.mode > 3 || (writer.maximum == 0 && writer.mode != 0 && writer.mode != 3) {
        return -1;
    }
    // SAFETY: `output` is non-null (checked above), aligned and writable per the export's contract.
    unsafe { output.write(writer.next_chunk()) };
    0
}
/// # Safety
/// Writer is an aligned initialized exclusive writable native-owned value.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_bus_writer_complete(
    writer: *mut BusWriter,
    success: u8,
    reduce: u8,
) -> i32 {
    if writer.is_null() {
        return -1;
    }
    // SAFETY: non-null (checked above), aligned, initialized and exclusively lent.
    let writer = unsafe { &mut *writer };
    if (writer.maximum == 0 && writer.mode != 0)
        || writer.minimum == 0
        || writer.offset.checked_add(writer.remaining).is_none()
    {
        return -1;
    }
    writer.complete(success != 0, reduce != 0)
}

/// Increment is uint16 wrapping, preserving read_with_buffer's existing double
/// count before prepare_packet. End always wins over the fairness threshold.
#[unsafe(no_mangle)]
pub extern "C" fn swr_v1_bus_receive_step(count: u16, end: u8, limit: u16) -> u32 {
    let count = count.wrapping_add(1);
    let action = if end != 0 {
        2
    } else {
        u32::from(count >= limit)
    };
    u32::from(count) | (action << 16)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn reduction_retries_current_chunk_and_preserves_begin_end() {
        let mut writer = BusWriter::new(2000, 4096, 1024, true, false).unwrap();
        assert_eq!(writer.next_chunk().mode, 1);
        assert_eq!(writer.complete(false, true), 1);
        let first = writer.next_chunk();
        assert_eq!((first.length, first.flags), (1024, 12));
        assert_eq!(writer.complete(true, false), 0);
        let last = writer.next_chunk();
        assert_eq!((last.offset, last.length, last.flags), (1024, 976, 20));
        assert_eq!(writer.complete(false, true), -1);
        assert_eq!(writer.complete(true, false), 0);
        assert_eq!(writer.mode, 3);
    }
    #[test]
    fn zero_payload_and_fairness_boundaries() {
        assert_eq!(
            BusWriter::new(99, 1024, 128, false, false)
                .unwrap()
                .next_chunk()
                .length,
            0
        );
        assert_eq!(swr_v1_bus_receive_step(31, 0, 32), 32 | (1 << 16));
        assert_eq!(swr_v1_bus_receive_step(31, 1, 32), 32 | (2 << 16));
        assert_eq!(swr_v1_bus_receive_step(u16::MAX, 0, 32), 0);
    }
}
