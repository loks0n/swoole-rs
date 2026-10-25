#include "swoole_rs_crc32.h"
#include <array>
#include <cassert>
#include <cstdio>
#include <thread>
#include <vector>
#include <sys/wait.h>
#include <unistd.h>

uint32_t upstream_crc32(const char *, size_t);
uint32_t swoole_crc32(const char *, size_t);

void hash_crc32();

int main() {
    hash_crc32();
    size_t cases = 0;
    auto check = [&](const uint8_t *data, size_t size) {
        const auto expected = upstream_crc32(reinterpret_cast<const char *>(data), size);
        assert(swr_v1_crc32(data, size) == expected);
        assert(swoole_crc32(reinterpret_cast<const char *>(data), size) == expected);
        ++cases;
    };
    check(nullptr, 0);
#ifndef SWR_CRC32_POSITIVE_ONLY
    assert(swr_v1_crc32(nullptr, 1) == 0);
    const uint8_t byte = 1;
    assert(swr_v1_crc32(&byte, SIZE_MAX) == 0);
    assert(swr_v1_crc32(reinterpret_cast<const uint8_t *>(UINTPTR_MAX), 1) == 0);
    assert(swr_v1_crc32(reinterpret_cast<const uint8_t *>(UINTPTR_MAX - 7), 8) == 0);
#endif
    assert(swr_v1_crc32(reinterpret_cast<const uint8_t *>("123456789"), 9) == 0xcbf43926);
    std::vector<uint8_t> storage(65536 + 16);
    uint32_t seed = 0x1234abcd;
    auto random = [&]() {
        seed ^= seed << 13;
        seed ^= seed >> 17;
        seed ^= seed << 5;
        return seed;
    };
    for (auto &value : storage) value = random();
    for (size_t size : {0, 1, 2, 3, 7, 8, 15, 16, 31, 32, 63, 64, 127, 128,
                        255, 256, 511, 512, 1023, 1024, 4095, 4096, 65535, 65536}) {
        for (size_t offset = 0; offset < 16; ++offset) check(storage.data() + offset, size);
    }
    for (unsigned value = 0; value < 256; ++value) {
        storage[0] = value;
        check(storage.data(), 1);
    }
    for (unsigned value = 0; value < 65536; ++value) {
        storage[1] = value;
        storage[2] = value >> 8;
        check(storage.data() + 1, 2);
    }
    for (size_t trial = 0; trial < 10000; ++trial) {
        const size_t size = random() % 4097;
        for (size_t i = 0; i < size; ++i) storage[i + 1] = random();
        check(storage.data() + 1, size);
    }
#ifndef SWR_CRC32_POSITIVE_ONLY
    const auto expected = upstream_crc32(reinterpret_cast<const char *>(storage.data()), storage.size());
    std::array<std::thread, 8> threads;
    for (auto &thread : threads) thread = std::thread([&] {
        for (int iteration = 0; iteration < 100; ++iteration) {
            assert(swr_v1_crc32(storage.data(), storage.size()) == expected);
            assert(swoole_crc32(reinterpret_cast<const char *>(storage.data()), storage.size()) == expected);
        }
    });
    for (auto &thread : threads) thread.join();
    const auto child = fork();
    assert(child >= 0);
    if (child == 0) {
        const bool same = swr_v1_crc32(storage.data(), storage.size()) == expected &&
            swoole_crc32(reinterpret_cast<const char *>(storage.data()), storage.size()) == expected;
        _exit(same ? 0 : 1);
    }
    int status = -1;
    assert(waitpid(child, &status, 0) == child);
    assert(WIFEXITED(status) && WEXITSTATUS(status) == 0);
    std::printf("{\"differential_cases\":%zu,\"concurrent_calls\":1600,\"fork_child\":true}\n", cases);
#else
    std::printf("{\"differential_cases\":%zu,\"concurrent_calls\":0,\"fork_child\":false,\"positive_only\":true}\n", cases);
#endif
}
