// Compare actual pinned C++ length parsing with the frozen Rust ABI.
#include "swoole_websocket.h"
#include "swoole_rs_websocket.h"
#include <array>
#include <cstdio>
#include <cstring>
#include <limits>

int main() {
    const std::array<std::array<uint8_t, 4>, 4> keys{{
        {{0, 0, 0, 0}}, {{255, 255, 255, 255}}, {{0x37, 0xfa, 0x21, 0x3d}}, {{0, 255, 128, 1}}
    }};
    size_t comparisons = 0;
    for (uint64_t payload : {uint64_t(0), uint64_t(1), uint64_t(125), uint64_t(126),
                             uint64_t(65535), uint64_t(65536)}) {
        for (bool masked : {false, true}) {
            for (const auto &key : keys) {
                std::array<uint8_t, 16> wire{};
                wire[0] = 0x82; // FIN + binary; encode independently of either implementation.
                const size_t base = payload < 126 ? 2 : payload <= 65535 ? 4 : 10;
                wire[1] = (masked ? 128 : 0) | (base == 2 ? payload : base == 4 ? 126 : 127);
                if (base > 2) {
                    for (size_t i = 0; i < base - 2; ++i) {
                        wire[2 + i] = uint8_t(payload >> (8 * (base - 3 - i)));
                    }
                }
                if (masked) std::memcpy(wire.data() + base, key.data(), key.size());
                const size_t header_size = base + (masked ? key.size() : 0);
                // Pinned C++ uses typed extended-length loads. Its extended
                // integer starts at +2, so base+6 keeps those loads aligned.
                // Rust receives the identical bytes at every alignment below.
                alignas(8) std::array<uint8_t, 32> reference{};
                std::memcpy(reference.data() + 6, wire.data(), header_size);
                for (size_t alignment = 0; alignment < 8; ++alignment) {
                    alignas(8) std::array<uint8_t, 32> input{};
                    std::memcpy(input.data() + alignment, wire.data(), header_size);
                    for (size_t available = 0; available <= header_size; ++available) {
                        swoole::PacketLength pl{reinterpret_cast<const char *>(reference.data() + 6),
                                                uint32_t(available), 99};
                        const ssize_t upstream = swoole::websocket::get_package_length(nullptr, nullptr, &pl);
                        uint32_t rust_header = 99;
                        const int64_t rust = swr_v1_ws_frame_length(input.data() + alignment, available, &rust_header);
                        ++comparisons;
                        if (rust != upstream || rust_header != pl.header_len) {
                            std::fprintf(stderr, "prefix mismatch payload=%llu masked=%d alignment=%zu prefix=%zu "
                                         "C++=%lld/header%u Rust=%lld/header%u\n",
                                         static_cast<unsigned long long>(payload), masked, alignment, available,
                                         static_cast<long long>(upstream), pl.header_len,
                                         static_cast<long long>(rust), rust_header);
                            return 1;
                        }
                    }
                }
            }
        }
    }
    // Do not invoke upstream's signed addition at overflow. Rust deliberately
    // rejects totals above signed pointer size, independently of this oracle.
    size_t overflow_checks = 0;
    for (bool masked : {false, true}) {
        const uint64_t header_size = masked ? 14 : 10;
        for (uint64_t payload : {uint64_t(std::numeric_limits<ssize_t>::max()) - header_size + 1,
                                 std::numeric_limits<uint64_t>::max()}) {
            std::array<uint8_t, 16> wire{};
            wire[0] = 0x82;
            wire[1] = (masked ? 128 : 0) | 127;
            for (size_t i = 0; i < 8; ++i) wire[2 + i] = uint8_t(payload >> (8 * (7 - i)));
            uint32_t header = 99;
            const int64_t result = swr_v1_ws_frame_length(wire.data(), header_size, &header);
            ++overflow_checks;
            if (result != -1 || header != header_size) {
                std::fprintf(stderr, "Rust overflow rejection failed\n");
                return 1;
            }
        }
    }
    std::printf("{\"prefix_comparisons\":%zu,\"mismatches\":0,\"rust_overflow_checks\":%zu}\n",
                comparisons, overflow_checks);
}
