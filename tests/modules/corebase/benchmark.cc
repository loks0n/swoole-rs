// SPDX-License-Identifier: Apache-2.0
#include "swoole.h"
#include "swoole_protocol.h"
#include <chrono>
#include <cstring>
#include <iostream>
#include <string>

static volatile uint64_t sink;
static std::string requested;
static unsigned executed;

template<class F> static void workload(const char *name, uint64_t iterations, bool measure, F run) {
    if (!requested.empty() && requested != name) return;
    ++executed;
    uint64_t unit = measure ? run(1) : 0;  // matched in-process warmup, outside timing
    std::chrono::steady_clock::time_point start;
    if (measure) start = std::chrono::steady_clock::now();
    uint64_t result = run(iterations);
    auto elapsed = measure ? std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now() - start).count() : 0;
    if (measure && result != unit * iterations) std::exit(5);
    sink = result;
    std::cout << "{\"workload\":\"" << name << "\",\"iterations\":" << iterations
              << ",\"checksum\":" << result;
    if (measure) {
        std::cout << ",\"elapsed_ns\":" << elapsed;
    }
    std::cout << "}\n";
}

int main(int argc, char **argv) {
    if (argc == 2 && std::string(argv[1]) == "--identify") return 0;
    if ((argc != 4 && argc != 5) || (std::string(argv[1]) != "--check" && std::string(argv[1]) != "--measure")) return 2;
    requested = argc == 5 ? argv[4] : "";
    bool measure = std::string(argv[1]) == "--measure";
    uint64_t n = measure ? std::stoull(argv[2]) : 1;
    if (!n) return 2;
    const std::string directory = argv[3];
    swoole_init();
    if (!swoole_mkdir_recursive(directory)) return 3;
    workload("pack_type_sizes", n, measure, [](uint64_t count) {
        uint64_t sum = 0;
        const char kinds[] = {'c','C','s','S','n','v','l','L','N','V','q','Q','J','P'};
        for (uint64_t i = 0; i < count; ++i) for (char c : kinds) sum += swoole_type_size(c);
        return sum;
    });
    workload("gcd", n, measure, [](uint64_t count) {
        uint64_t sum = 0;
        for (uint64_t i = 0; i < count; ++i) sum += swoole_common_divisor(196605, 131070);
        return sum;
    });
    workload("lcm_wrapped", n, measure, [](uint64_t count) {
        uint64_t sum = 0;
        for (uint64_t i = 0; i < count; ++i) sum += swoole_common_multiple(65536, 65536);
        return sum;
    });
    workload("lcm_regular", n, measure, [](uint64_t count) {
        uint64_t sum = 0;
        for (uint64_t i = 0; i < count; ++i) sum += swoole_common_multiple(16, 12);
        return sum;
    });
    workload("decimal", n, measure, [](uint64_t count) {
        uint64_t sum = 0;
        for (uint64_t i = 0; i < count; ++i) {
            char buf[64];
            sum += swoole_itoa(buf, -2147483647L);
            sum += static_cast<unsigned char>(buf[0]) + static_cast<unsigned char>(buf[10]);
        }
        return sum;
    });
    workload("radix_alloc_release", n, measure, [](uint64_t count) {
        uint64_t sum = 0;
        for (uint64_t i = 0; i < count; ++i) {
            char *p = swoole_dec2hex(2684326179UL, 16);
            if (!p) std::exit(4);
            sum += std::strlen(p) + static_cast<unsigned char>(p[0]) + static_cast<unsigned char>(p[7]);
            sw_free(p);
        }
        return sum;
    });
    workload("hex", n, measure, [](uint64_t count) {
        uint64_t sum = 0;
        for (uint64_t i = 0; i < count; ++i) {
            size_t parsed;
            sum += swoole_hex2dec("0x9fff9123!", &parsed); sum += parsed;
        }
        return sum;
    });
    workload("version_equal", n, measure, [](uint64_t count) {
        uint64_t sum = 0;
        for (uint64_t i = 0; i < count; ++i) sum += 2 + swoole_version_compare("6.2.2", "6.2.2");
        return sum;
    });
    workload("version_different", n, measure, [](uint64_t count) {
        uint64_t sum = 0;
        for (uint64_t i = 0; i < count; ++i) sum += 2 + swoole_version_compare("6.2.2", "6.3.0");
        return sum;
    });
    const std::string file = "/var/www/application/public/index.php";
    workload("dirname", n, measure, [&](uint64_t count) {
        uint64_t sum = 0;
        for (uint64_t i = 0; i < count; ++i) sum += swoole::dirname(file).size();
        return sum;
    });
    workload("mkdir_existing", n, measure, [&](uint64_t count) {
        uint64_t sum = 0;
        for (uint64_t i = 0; i < count; ++i) sum += swoole_mkdir_recursive(directory);
        return sum;
    });
    swoole_clean();
    return executed ? 0 : 2;
}
