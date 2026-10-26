//! Pinned upstream C++ for differential tests. Add a module's original files to
//! `upstream/` unchanged, compile them in `build.rs`, and declare them here.

pub mod base64 {
    unsafe extern "C" {
        /// Upstream `swoole::base64_encode`. Undefined for zero length.
        #[link_name = "swr_oracle_base64_encode"]
        pub fn encode(input: *const u8, length: usize, output: *mut u8) -> usize;
        /// Upstream `swoole::base64_decode`.
        #[link_name = "swr_oracle_base64_decode"]
        pub fn decode(input: *const u8, length: usize, output: *mut u8) -> usize;
        /// Runs upstream's `core-tests/src/protocol/base64.cpp` against the native
        /// adapter; returns the number of failed assertions. The caller's binary
        /// must link `swr_v1_base64_*`.
        #[link_name = "swr_original_base64_failures"]
        pub fn original_test_failures() -> i32;
    }
}

pub mod crc32 {
    unsafe extern "C" {
        /// Upstream `swoole_crc32`.
        #[link_name = "swr_oracle_crc32"]
        pub fn crc32(data: *const u8, size: usize) -> u32;
        /// Runs upstream's `TEST(hash, crc32)` from `core-tests/src/core/hash.cpp`
        /// against the native adapter; returns the number of failed assertions.
        /// The caller's binary must link `swr_v1_crc32`.
        #[link_name = "swr_original_crc32_failures"]
        pub fn original_test_failures() -> i32;
    }
}

pub mod websocket {
    /// Fields of upstream's `websocket::Frame` after `decode`; flags as `Frame::get_flags()`.
    #[repr(C)]
    #[derive(Clone, Copy, Debug, Default, PartialEq)]
    pub struct Frame {
        pub payload_length: u64,
        pub header_length: u16,
        pub opcode: u8,
        pub flags: u8,
        pub length_code: u8,
        pub mask_key: [u8; 4],
    }

    unsafe extern "C" {
        /// Upstream `get_package_length_impl` over `length` bytes; `header_length`
        /// is the `PacketLength::header_len` it starts from and leaves.
        #[link_name = "swr_oracle_ws_frame_length"]
        pub fn frame_length(data: *const u8, length: usize, header_length: *mut u32) -> isize;
        /// Upstream `websocket::decode`, which unmasks the payload in place.
        #[link_name = "swr_oracle_ws_decode"]
        pub fn decode(data: *mut u8, length: usize, frame: *mut Frame) -> bool;
        /// Upstream `websocket::mask`.
        #[link_name = "swr_oracle_ws_mask"]
        pub fn mask(data: *mut u8, length: usize, key: *const u8);
    }
}

pub mod http {
    unsafe extern "C" {
        /// Upstream `http_server::url_decode`, in place over `length + 1` bytes
        /// (it writes a terminator); returns the decoded length.
        #[link_name = "swr_oracle_http_url_decode"]
        pub fn url_decode(data: *mut u8, length: usize) -> usize;
        /// Upstream `http_server::url_encode`, copied with its NUL into `output`
        /// (capacity `3 * length + 1`); returns the encoded length.
        #[link_name = "swr_oracle_http_url_encode"]
        pub fn url_encode(data: *const u8, length: usize, output: *mut u8) -> usize;
        /// Every `http_server::parse_cookie` callback as u32 key length, key,
        /// u32 value length, value, into `output` (capacity `8 * length + 16`).
        #[link_name = "swr_oracle_http_cookies"]
        pub fn cookies(data: *const u8, length: usize, output: *mut u8) -> usize;
    }
}

pub mod framing {
    unsafe extern "C" {
        /// Upstream `swoole_unpack`: reads the format's width from `data`.
        #[link_name = "swr_oracle_framing_unpack"]
        pub fn unpack(format: u8, data: *const u8) -> i64;
        /// Upstream `Protocol::default_length_func` for this length type, field
        /// size, field offset and body offset; `header_length` is what it leaves
        /// in `PacketLength::header_len`.
        #[link_name = "swr_oracle_framing_length"]
        pub fn length(
            format: u8,
            size: u8,
            offset: u16,
            body_offset: u16,
            data: *const u8,
            length: u32,
            header_length: *mut u32,
        ) -> isize;
    }
}
