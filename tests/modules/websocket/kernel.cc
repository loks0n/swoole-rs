// Exercise exported C symbols, independent of Rust's type system and callers.
#include "swoole_rs_websocket.h"
#include <array>
#include <cassert>
#include <climits>
#include <cstdio>
#include <cstring>
#include <limits>

int main() {
    // All lengths at representation boundaries, every flag and opcode byte,
    // deliberately unaligned wire headers, and incremental masked headers.
    for (uint64_t length : {uint64_t(0), uint64_t(125), uint64_t(126), uint64_t(65535),
                            uint64_t(65536), uint64_t(1) << 32}) {
        for (unsigned flags = 0; flags < 256; ++flags) {
            for (unsigned opcode = 0; opcode < 256; ++opcode) {
                std::array<uint8_t, 16> wire;
                wire.fill(0xa5);
                const size_t size = swr_v1_ws_write_header(length, opcode, flags, wire.data() + 1, 10);
                assert(size == (length < 126 ? 2 : length <= 65535 ? 4 : 10));
                assert(wire[0] == 0xa5 && wire[size + 1] == 0xa5);
                assert(wire[1] == ((opcode & 15) | ((flags & 1) ? 128 : 0) | ((flags & 4) ? 64 : 0)));
                assert(wire[2] == (((flags & 32) ? 128 : 0) | (size == 2 ? length : size == 4 ? 126 : 127)));
                if (size > 2) {
                    uint64_t decoded = 0;
                    for (size_t index = 3; index < 1 + size; ++index) {
                        decoded = (decoded << 8) | wire[index];
                    }
                    assert(decoded == length);
                }
                const size_t full_header = size + ((flags & 32) ? 4 : 0);
                for (size_t available = 0; available <= full_header; ++available) {
                    uint32_t header = 99;
                    const int64_t total = swr_v1_ws_frame_length(wire.data() + 1, available, &header);
                    assert(total == (available < full_header ? 0 : int64_t(full_header + length)));
                    assert(header == (available < 2 ? 99 : available < size ? size : full_header));
                }
            }
        }
    }
    std::array<uint8_t, 16> wire{};
    for (bool masked : {false, true}) {
        const uint64_t header_size = masked ? 14 : 10;
        for (uint64_t payload : {uint64_t(INT64_MAX) - header_size,
                                 uint64_t(INT64_MAX) - header_size + 1, UINT64_MAX}) {
            assert(swr_v1_ws_write_header(payload, 2, masked ? 32 : 0, wire.data(), wire.size()) == 10);
            uint32_t header = 99;
            assert(swr_v1_ws_frame_length(wire.data(), wire.size(), &header) ==
                   (payload == uint64_t(INT64_MAX) - header_size ? INT64_MAX : -1));
            assert(header == header_size);
        }
    }
    for (size_t capacity = 0; capacity < 10; ++capacity) {
        wire.fill(0xa5);
        assert(swr_v1_ws_write_header(UINT64_MAX, 2, 32, wire.data(), capacity) == 0);
        for (auto byte : wire) assert(byte == 0xa5);
    }
    uint32_t header = 99;
    assert(swr_v1_ws_frame_length(nullptr, 0, &header) == 0 && header == 99);
    assert(swr_v1_ws_frame_length(nullptr, 1, &header) == -1 && header == 99);
    assert(swr_v1_ws_frame_length(wire.data(), SIZE_MAX, &header) == -1);
    assert(swr_v1_ws_frame_length(wire.data(), 2, nullptr) == -1);
    assert(swr_v1_ws_write_header(1, 2, 1, nullptr, 10) == 0);
    assert(swr_v1_ws_write_header(1, 2, 1, wire.data(), SIZE_MAX) == 0);
    assert(swr_v1_ws_mask(nullptr, 0, nullptr) == 0);
    assert(swr_v1_ws_mask(nullptr, 1, wire.data()) == -1);
    assert(swr_v1_ws_mask(wire.data(), 1, nullptr) == -1);
    assert(swr_v1_ws_mask(wire.data(), SIZE_MAX, wire.data()) == -1);

    for (size_t length = 1; length <= 1024; ++length) {
        std::array<uint8_t, 1026> bytes;
        for (size_t i = 0; i < bytes.size(); ++i) bytes[i] = uint8_t(i);
        const auto original = bytes;
        const uint8_t key[] = {0x37, 0xfa, 0x21, 0x3d};
        assert(swr_v1_ws_mask(bytes.data() + 1, length, key) == 0);
        for (size_t i = 0; i < length; ++i) assert(bytes[i + 1] == (original[i + 1] ^ key[i % 4]));
        assert(bytes[0] == original[0] && bytes[length + 1] == original[length + 1]);
        assert(swr_v1_ws_mask(bytes.data() + 1, length, key) == 0);
        assert(bytes == original);
    }
    // Every byte alignment and word tail, including keys partly overlapping
    // either payload boundary. Read the expected key from the original buffer:
    // masking must snapshot all four bytes before any payload write.
    for (size_t alignment = 0; alignment < 8; ++alignment) {
        for (size_t length = 0; length <= 33; ++length) {
            std::array<uint8_t, 64> bytes;
            const size_t start = 8 + alignment;
            for (size_t key_offset = start - 4; key_offset <= start + length; ++key_offset) {
                for (size_t i = 0; i < bytes.size(); ++i) bytes[i] = uint8_t(i * 37 + 19);
                const auto original = bytes;
                assert(swr_v1_ws_mask(bytes.data() + start, length, bytes.data() + key_offset) == 0);
                for (size_t i = 0; i < bytes.size(); ++i) {
                    const bool masked = i >= start && i < start + length;
                    const auto expected = masked ? original[i] ^ original[key_offset + (i - start) % 4]
                                                 : original[i];
                    assert(bytes[i] == expected);
                }
            }
        }
    }
    std::puts("WebSocket kernel C ABI: boundary, flag, incremental, overflow, masking and alias checks passed");
}
