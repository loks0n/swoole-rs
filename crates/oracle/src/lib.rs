//! Pinned upstream C++ for differential tests. Add a module's original files to
//! `upstream/` unchanged, compile them in `build.rs`, and declare them here.
#![cfg_attr(
    not(test),
    deny(
        clippy::undocumented_unsafe_blocks,
        clippy::multiple_unsafe_ops_per_block
    )
)]

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

pub mod http_frame {
    use std::ffi::c_char;

    /// The `Request` fields request framing reads and writes, and the buffer offset.
    #[repr(C)]
    #[derive(Clone, Copy, Debug, Default, PartialEq)]
    pub struct State {
        pub offset: usize,
        pub content_length: u64,
        pub method: u32,
        pub version: u32,
        pub excepted: u32,
        pub known_length: u32,
        pub url_offset: u32,
        pub url_length: u32,
        pub line_length: u32,
        pub header_length: u32,
    }

    /// Request framing compiled from one engine's http.cc: `upstream` is the pinned
    /// file, `candidate` the file with the http overlay patch, which calls the Rust
    /// exports (the caller's binary must link `swr_v1_http_*`).
    pub struct Engine {
        /// `operation` 0 `get_protocol`, 1 `get_header_length`, 2
        /// `get_chunked_body_length` over `length` bytes followed by a NUL;
        /// returns `SW_OK` (0) or `SW_ERR` (-1).
        pub frame: unsafe extern "C" fn(u32, *mut c_char, usize, *mut State) -> i32,
        /// `Request::has_expect_header` over `length` bytes followed by a NUL.
        pub expect: unsafe extern "C" fn(*mut c_char, usize) -> bool,
        /// `Request::get_header(name)` with this url offset, url length and header
        /// length, copied into `output` (capacity `length`); returns its size.
        pub header: unsafe extern "C" fn(
            *mut c_char,
            usize,
            u32,
            u32,
            u32,
            *const c_char,
            *mut c_char,
        ) -> usize,
        /// `get_method_string`.
        pub method: unsafe extern "C" fn(i32) -> *const c_char,
    }

    unsafe extern "C" {
        fn swr_oracle_http_frame_upstream(
            operation: u32,
            data: *mut c_char,
            length: usize,
            state: *mut State,
        ) -> i32;
        fn swr_oracle_http_expect_upstream(data: *mut c_char, length: usize) -> bool;
        fn swr_oracle_http_header_upstream(
            data: *mut c_char,
            length: usize,
            url_offset: u32,
            url_length: u32,
            header_length: u32,
            name: *const c_char,
            output: *mut c_char,
        ) -> usize;
        fn swr_oracle_http_method_upstream(method: i32) -> *const c_char;
        fn swr_oracle_http_frame_candidate(
            operation: u32,
            data: *mut c_char,
            length: usize,
            state: *mut State,
        ) -> i32;
        fn swr_oracle_http_expect_candidate(data: *mut c_char, length: usize) -> bool;
        fn swr_oracle_http_header_candidate(
            data: *mut c_char,
            length: usize,
            url_offset: u32,
            url_length: u32,
            header_length: u32,
            name: *const c_char,
            output: *mut c_char,
        ) -> usize;
        fn swr_oracle_http_method_candidate(method: i32) -> *const c_char;
    }

    pub const UPSTREAM: Engine = Engine {
        frame: swr_oracle_http_frame_upstream,
        expect: swr_oracle_http_expect_upstream,
        header: swr_oracle_http_header_upstream,
        method: swr_oracle_http_method_upstream,
    };
    pub const CANDIDATE: Engine = Engine {
        frame: swr_oracle_http_frame_candidate,
        expect: swr_oracle_http_expect_candidate,
        header: swr_oracle_http_header_candidate,
        method: swr_oracle_http_method_candidate,
    };
}

pub mod protocols {
    use std::ffi::c_char;

    /// MQTT's length decoder and RESP's parse compiled from one engine's sources:
    /// `upstream` is the pinned file, `candidate` the file with the protocols overlay
    /// patch, which calls the Rust exports (the caller's binary must link them).
    pub struct Engine {
        /// `mqtt::get_package_length` over `size` bytes.
        pub mqtt_length: unsafe extern "C" fn(*const c_char, u32) -> i64,
        /// `redis::parse` over `length` bytes followed by a NUL, from errno 0: each
        /// string as u32 length and bytes in a buffer of `*size` bytes (release with
        /// [`free`]); `*error` is errno afterwards.
        pub resp_parse:
            unsafe extern "C" fn(*const c_char, usize, *mut usize, *mut i32) -> *mut c_char,
    }

    unsafe extern "C" {
        fn swr_oracle_mqtt_length_upstream(data: *const c_char, size: u32) -> i64;
        fn swr_oracle_resp_parse_upstream(
            data: *const c_char,
            length: usize,
            size: *mut usize,
            error: *mut i32,
        ) -> *mut c_char;
        fn swr_oracle_mqtt_length_candidate(data: *const c_char, size: u32) -> i64;
        fn swr_oracle_resp_parse_candidate(
            data: *const c_char,
            length: usize,
            size: *mut usize,
            error: *mut i32,
        ) -> *mut c_char;
        /// Releases a `resp_parse` buffer.
        #[link_name = "swr_oracle_free"]
        pub fn free(pointer: *mut c_char);
    }

    pub const UPSTREAM: Engine = Engine {
        mqtt_length: swr_oracle_mqtt_length_upstream,
        resp_parse: swr_oracle_resp_parse_upstream,
    };
    pub const CANDIDATE: Engine = Engine {
        mqtt_length: swr_oracle_mqtt_length_candidate,
        resp_parse: swr_oracle_resp_parse_candidate,
    };
}
