// This driver contains no CRC algorithm; both candidates are linked separately.
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <string>
#include <cstring>
#include <vector>

uint32_t upstream_crc32(const char *, size_t);
uint32_t swoole_crc32(const char *, size_t);

int main(int argc, char **argv) {
    if (argc != 5 && argc != 6) return 2;
    const std::string engine = argv[1];
    const size_t length = std::stoull(argv[2]);
    const size_t iterations = std::stoull(argv[3]);
    const bool check_only = std::string(argv[4]) == "check";
    if ((engine != "upstream" && engine != "rust") || !iterations || length > 1048576 ||
        (!check_only && std::string(argv[4]) != "measure")) return 2;
    const std::string pattern = argc == 6 ? argv[5] : "binary";
    std::vector<char> input(length);
    if (pattern == "binary") {
        for (size_t i = 0; i < length; ++i) input[i] = static_cast<char>((i * 37 + 11) & 255);
    } else if (pattern == "ipv6-loopback" && length == 28) {
        std::memcpy(input.data(), "::1", 3);
    } else return 2;
    auto function = engine == "upstream" ? upstream_crc32 : swoole_crc32;
    const uint32_t expected = upstream_crc32(input.data(), length);
    if (swoole_crc32(input.data(), length) != expected) return 1;
    if (check_only) {
        std::printf("{\"preflight_passed\":true,\"length\":%zu,\"crc32\":%u,\"pattern\":\"%s\"}\n", length, expected, pattern.c_str());
        return 0;
    }
    uint64_t checksum = 0;
    const auto start = std::chrono::steady_clock::now();
    for (size_t i = 0; i < iterations; ++i) checksum += function(input.data(), length);
    const double seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
    if (checksum != static_cast<uint64_t>(expected) * iterations) return 1;
    std::printf("{\"engine\":\"%s\",\"length\":%zu,\"iterations\":%zu,\"seconds\":%.9f,"
                "\"checksum\":%llu,\"errors\":0,\"pattern\":\"%s\"}\n", engine.c_str(), length, iterations, seconds,
                static_cast<unsigned long long>(checksum), pattern.c_str());
}
