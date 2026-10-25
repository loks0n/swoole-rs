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
