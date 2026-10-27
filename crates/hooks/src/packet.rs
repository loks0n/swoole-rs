//! `Socket::recv_packet` of the coroutine socket: one packet, length-prefixed,
//! EOF-delimited or whatever one `recv` returns, read into the socket's read
//! buffer. Native code keeps the availability check, the read timer and the
//! buffer's allocation, and passes the socket's effects in `PacketOps`.
use core::ffi::c_void;

/// `SW_BUFFER_SIZE_BIG`: the most one EOF-protocol `recv` asks for.
const BIG: usize = 65536;

/// The leading fields of `swoole::String`, in its order.
#[repr(C)]
#[derive(Clone, Copy)]
pub struct ReadBuffer {
    pub length: usize,
    pub size: usize,
    pub offset: libc::off_t,
    pub str: *mut u8,
}

/// The socket's protocol settings and effects. Every callback gets `context`.
#[repr(C)]
pub struct PacketOps {
    pub context: *mut c_void,
    /// The socket's read buffer; `extend` and `reduce` may move its bytes.
    pub buffer: *mut ReadBuffer,
    pub length_check: bool,
    pub eof_check: bool,
    pub eof: *const u8,
    pub eof_len: u8,
    pub length_type: u8,
    pub length_size: u8,
    pub length_offset: u16,
    pub max_length: u32,
    /// `Socket::recv` and `Socket::recv_all`.
    pub recv: unsafe extern "C" fn(*mut c_void, *mut u8, usize) -> isize,
    pub recv_all: unsafe extern "C" fn(*mut c_void, *mut u8, usize) -> isize,
    /// `protocol.get_package_length` over the first `length` bytes; stores
    /// `PacketLength::header_len`.
    pub package_length: unsafe extern "C" fn(*mut c_void, *const u8, u32, *mut u32) -> isize,
    pub extend: unsafe extern "C" fn(*mut c_void, usize),
    pub reduce: unsafe extern "C" fn(*mut c_void, libc::off_t),
    /// Sets the socket error: 0 no package length, 1 too large (with a warning
    /// naming `length`), 2 no EOF within `package_max_length`.
    pub fail: unsafe extern "C" fn(*mut c_void, u32, isize),
    /// `errCode == ETIMEDOUT`.
    pub timed_out: unsafe extern "C" fn(*mut c_void) -> bool,
}

struct Packet<'a> {
    ops: &'a PacketOps,
}

impl Packet<'_> {
    fn buffer(&self) -> ReadBuffer {
        // SAFETY: `buffer` is the live read buffer for the whole call (swr_v1_hook_recv_packet).
        unsafe { self.ops.buffer.read() }
    }

    fn set_length(&self, length: usize) {
        // SAFETY: as in `buffer`; no reference into it is held across callbacks.
        unsafe { (*self.ops.buffer).length = length };
    }

    fn set_offset(&self, offset: usize) {
        #[expect(
            clippy::cast_possible_wrap,
            reason = "upstream assigns size_t to off_t"
        )]
        // SAFETY: as in `set_length`.
        unsafe {
            (*self.ops.buffer).offset = offset as libc::off_t;
        };
    }

    /// `String::clear`.
    fn clear(&self) {
        self.set_length(0);
        self.set_offset(0);
    }

    fn recv(&self, at: usize, length: usize) -> isize {
        let buffer = self.buffer();
        // SAFETY: `at` is within the buffer's `size` bytes, as upstream's pointer was.
        unsafe { (self.ops.recv)(self.ops.context, buffer.str.wrapping_add(at), length) }
    }

    fn fail(&self, kind: u32, length: isize) {
        // SAFETY: a native effect on the live socket in `context`.
        unsafe { (self.ops.fail)(self.ops.context, kind, length) };
    }

    fn timed_out(&self) -> bool {
        // SAFETY: a native read of the live socket in `context`.
        unsafe { (self.ops.timed_out)(self.ops.context) }
    }

    fn extend(&self, size: usize) {
        // SAFETY: a native effect on the live read buffer; `buffer` is re-read after it.
        unsafe { (self.ops.extend)(self.ops.context, size) };
    }

    /// `recv_packet_with_length_protocol`.
    fn length_protocol(&self) -> isize {
        let ops = self.ops;
        let mut header_len = u32::from(ops.length_offset) + u32::from(ops.length_size);
        let buffered = self.buffer().length;
        // A custom package_length_func has neither a size nor a type.
        let mut known = buffered > 0
            && (buffered >= header_len as usize || ops.length_size == 0 && ops.length_type == 0);
        loop {
            if !known {
                let buffer = self.buffer();
                let received = self.recv(
                    buffer.length,
                    (header_len as usize).wrapping_sub(buffer.length),
                );
                if received <= 0 {
                    return received;
                }
                self.set_length(buffer.length + received.unsigned_abs());
            }
            known = false;
            let buffer = self.buffer();
            let mut header = 0;
            #[expect(
                clippy::cast_possible_truncation,
                reason = "upstream's (uint32_t) read_buffer->length"
            )]
            // SAFETY: the buffer's first `length` bytes are initialized; `header` is writable.
            let packet = unsafe {
                (ops.package_length)(
                    ops.context,
                    buffer.str,
                    buffer.length as u32,
                    &raw mut header,
                )
            };
            if packet < 0 {
                self.fail(0, packet);
                return 0;
            }
            if packet == 0 {
                if header != 0 {
                    header_len = header;
                }
                continue;
            }
            if packet.unsigned_abs() > ops.max_length as usize {
                self.clear();
                self.fail(1, packet);
                return -1;
            }
            let wanted = packet.unsigned_abs();
            if wanted <= buffer.length {
                self.set_offset(wanted);
                return packet;
            }
            if wanted > buffer.size {
                self.extend(wanted);
            }
            let buffer = self.buffer();
            // SAFETY: the buffer now holds `wanted` bytes, as upstream's pointer assumed.
            let mut received = unsafe {
                (ops.recv_all)(
                    ops.context,
                    buffer.str.wrapping_add(buffer.length),
                    wanted - buffer.length,
                )
            };
            if received > 0 {
                let length = buffer.length + received.unsigned_abs();
                self.set_length(length);
                if length == wanted {
                    self.set_offset(wanted);
                    return packet;
                }
                received = if self.timed_out() { -1 } else { 0 };
            }
            return received;
        }
    }

    /// `recv_packet_with_eof_protocol`.
    fn eof_protocol(&self) -> isize {
        let ops = self.ops;
        // SAFETY: `eof` points to `eof_len` bytes of the socket's protocol.
        let eof = unsafe { core::slice::from_raw_parts(ops.eof, usize::from(ops.eof_len)) };
        let maximum = ops.max_length as usize;
        let mut buffered = self.buffer().length > 0;
        loop {
            if !buffered {
                let buffer = self.buffer();
                let received = self.recv(
                    buffer.length,
                    buffer.size.wrapping_sub(buffer.length).min(BIG),
                );
                if received <= 0 {
                    self.clear();
                    return received;
                }
                let length = buffer.length + received.unsigned_abs();
                self.set_length(length);
                if length < eof.len() {
                    continue;
                }
            }
            buffered = false;
            let buffer = self.buffer();
            if let Some(found) = find(&buffer, eof) {
                let offset = found + eof.len();
                self.set_offset(offset);
                return offset.cast_signed();
            }
            if buffer.length == maximum {
                self.clear();
                self.fail(2, 0);
                return -1;
            }
            if buffer.length == buffer.size && buffer.size < maximum {
                self.extend((buffer.size * 2).min(maximum));
            }
        }
    }
}

/// `swoole_strnpos` over the buffered bytes, whose length it takes as `uint32_t`.
fn find(buffer: &ReadBuffer, needle: &[u8]) -> Option<usize> {
    #[expect(
        clippy::cast_possible_truncation,
        reason = "swoole_strnpos takes a uint32_t length"
    )]
    let length = buffer.length as u32 as usize;
    if needle.is_empty() || needle.len() > length {
        return None;
    }
    // SAFETY: the buffer's first `length` bytes are initialized.
    let haystack = unsafe { core::slice::from_raw_parts(buffer.str, length) };
    haystack
        .windows(needle.len())
        .position(|window| window == needle)
}

/// `Socket::recv_packet` after its availability check, read timer and
/// `get_read_buffer`: the packet's length, or `recv`'s result.
///
/// # Safety
/// `ops` and its buffer are live and exclusively this socket's for the call;
/// its callbacks act on the socket in `context`.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn swr_v1_hook_recv_packet(ops: *const PacketOps) -> isize {
    // SAFETY: the caller passes a live table (see above).
    let ops = unsafe { &*ops };
    let packet = Packet { ops };
    let offset = packet.buffer().offset;
    // Unprocessed data.
    if offset > 0 {
        // SAFETY: a native effect on the live read buffer.
        unsafe { (ops.reduce)(ops.context, offset) };
    }
    let received = if ops.length_check {
        packet.length_protocol()
    } else if ops.eof_check {
        packet.eof_protocol()
    } else {
        let buffer = packet.buffer();
        let received = packet.recv(0, buffer.size);
        if received > 0 {
            packet.set_length(received.unsigned_abs());
            packet.set_offset(received.unsigned_abs());
        }
        received
    };
    // Keep incomplete length-prefixed packets for a subsequent read after a timeout.
    if received <= 0 && !(ops.length_check && received < 0 && packet.timed_out()) {
        packet.clear();
    }
    received
}

#[cfg(test)]
#[expect(
    clippy::cast_possible_truncation,
    clippy::cast_possible_wrap,
    clippy::cast_sign_loss,
    reason = "the test socket drives the native integer interfaces with small lengths"
)]
mod tests {
    use super::*;
    use std::collections::VecDeque;

    /// A socket whose `recv` hands out `chunks` in order, then 0 (EOF).
    struct Fake {
        storage: Vec<u8>,
        buffer: ReadBuffer,
        chunks: VecDeque<Vec<u8>>,
        failures: Vec<u32>,
        timed_out: bool,
    }

    unsafe fn fake<'a>(context: *mut c_void) -> &'a mut Fake {
        unsafe { &mut *context.cast::<Fake>() }
    }

    unsafe extern "C" fn recv(context: *mut c_void, at: *mut u8, length: usize) -> isize {
        let fake = unsafe { fake(context) };
        let Some(mut chunk) = fake.chunks.pop_front() else {
            return 0;
        };
        if chunk.len() > length {
            fake.chunks.push_front(chunk.split_off(length));
        }
        unsafe { at.copy_from_nonoverlapping(chunk.as_ptr(), chunk.len()) };
        chunk.len() as isize
    }

    unsafe extern "C" fn recv_all(context: *mut c_void, at: *mut u8, length: usize) -> isize {
        let mut total = 0;
        while total < length {
            let received = unsafe { recv(context, at.add(total), length - total) };
            if received <= 0 {
                break;
            }
            total += received as usize;
        }
        total as isize
    }

    /// A 4-byte big-endian body length after a 2-byte tag.
    unsafe extern "C" fn package_length(
        _: *mut c_void,
        at: *const u8,
        length: u32,
        _: *mut u32,
    ) -> isize {
        if length < 6 {
            return 0;
        }
        let bytes = unsafe { core::slice::from_raw_parts(at.add(2), 4) };
        6 + u32::from_be_bytes(bytes.try_into().unwrap()) as isize
    }

    unsafe extern "C" fn extend(context: *mut c_void, size: usize) {
        let fake = unsafe { fake(context) };
        fake.storage.resize(size, 0);
        fake.buffer.str = fake.storage.as_mut_ptr();
        fake.buffer.size = size;
    }

    unsafe extern "C" fn reduce(context: *mut c_void, offset: libc::off_t) {
        let fake = unsafe { fake(context) };
        let offset = offset as usize;
        fake.storage.copy_within(offset..fake.buffer.length, 0);
        fake.buffer.length -= offset;
        fake.buffer.offset = 0;
    }

    unsafe extern "C" fn fail(context: *mut c_void, kind: u32, _: isize) {
        unsafe { fake(context) }.failures.push(kind);
    }

    unsafe extern "C" fn timed_out(context: *mut c_void) -> bool {
        unsafe { fake(context) }.timed_out
    }

    fn run(
        chunks: &[&[u8]],
        size: usize,
        length_check: bool,
        eof: &[u8],
        max_length: u32,
    ) -> (Vec<isize>, Box<Fake>) {
        let mut fake = Box::new(Fake {
            storage: vec![0; size],
            buffer: ReadBuffer {
                length: 0,
                size,
                offset: 0,
                str: core::ptr::null_mut(),
            },
            chunks: chunks.iter().map(|chunk| chunk.to_vec()).collect(),
            failures: Vec::new(),
            timed_out: false,
        });
        fake.buffer.str = fake.storage.as_mut_ptr();
        let context = (&raw mut *fake).cast::<c_void>();
        let ops = PacketOps {
            context,
            buffer: &raw mut fake.buffer,
            length_check,
            eof_check: !eof.is_empty(),
            eof: eof.as_ptr(),
            eof_len: eof.len() as u8,
            length_type: b'N',
            length_size: 4,
            length_offset: 2,
            max_length,
            recv,
            recv_all,
            package_length,
            extend,
            reduce,
            fail,
            timed_out,
        };
        let mut results = Vec::new();
        loop {
            let result = unsafe { swr_v1_hook_recv_packet(&raw const ops) };
            results.push(result);
            if result <= 0 {
                break;
            }
        }
        (results, fake)
    }

    #[test]
    fn length_protocol_reassembles_split_and_coalesced_packets() {
        let first = [b"ab" as &[u8], &[0, 0, 0, 3], b"xyz"].concat();
        let second = [b"cd" as &[u8], &[0, 0, 0, 1], b"q"].concat();
        let wire = [first.clone(), second.clone()].concat();
        let (results, _) = run(&[&wire[..4], &wire[4..12], &wire[12..]], 8, true, b"", 1024);
        assert_eq!(results, [9, 7, 0]);
    }

    #[test]
    fn length_protocol_rejects_oversized_packets() {
        let wire = [b"ab" as &[u8], &[0, 0, 4, 0]].concat();
        let (results, fake) = run(&[&wire], 64, true, b"", 1024);
        assert_eq!(results, [-1]);
        assert_eq!(fake.failures, [1]);
        assert_eq!(fake.buffer.length, 0);
    }

    #[test]
    fn eof_protocol_splits_on_the_delimiter_and_grows_the_buffer() {
        let (results, fake) = run(&[b"hello\r\nwor", b"ld\r\n"], 4, false, b"\r\n", 1024);
        assert_eq!(results, [7, 7, 0]);
        assert!(fake.buffer.size > 4);
    }

    #[test]
    fn eof_protocol_fails_at_the_maximum_without_a_delimiter() {
        let (results, fake) = run(&[b"0123456789abcdef"], 16, false, b"\r\n", 16);
        assert_eq!(results, [-1]);
        assert_eq!(fake.failures, [2]);
    }

    #[test]
    fn partial_length_body_keeps_its_bytes_only_after_a_timeout() {
        // Upstream 0f96dc478: -1 after a timeout keeps the partial packet; 0 clears it.
        let wire = [b"ab" as &[u8], &[0, 0, 0, 8], b"part"].concat();
        for (timed_out, expected, kept) in [(true, -1, 10), (false, 0, 0)] {
            let mut fake = Box::new(Fake {
                storage: vec![0; 64],
                buffer: ReadBuffer {
                    length: 0,
                    size: 64,
                    offset: 0,
                    str: core::ptr::null_mut(),
                },
                chunks: VecDeque::from([wire.clone()]),
                failures: Vec::new(),
                timed_out,
            });
            fake.buffer.str = fake.storage.as_mut_ptr();
            let ops = PacketOps {
                context: (&raw mut *fake).cast(),
                buffer: &raw mut fake.buffer,
                length_check: true,
                eof_check: false,
                eof: b"".as_ptr(),
                eof_len: 0,
                length_type: b'N',
                length_size: 4,
                length_offset: 2,
                max_length: 1024,
                recv,
                recv_all,
                package_length,
                extend,
                reduce,
                fail,
                timed_out: self::timed_out,
            };
            assert_eq!(unsafe { swr_v1_hook_recv_packet(&raw const ops) }, expected);
            assert_eq!(fake.buffer.length, kept);
        }
    }

    #[test]
    fn raw_receive_returns_each_read() {
        let (results, fake) = run(&[b"abc", b"de"], 16, false, b"", 1024);
        assert_eq!(results, [3, 2, 0]);
        assert_eq!(fake.buffer.length, 0);
    }
}
