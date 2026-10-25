#include "swoole_base64.h"
#include "swoole_rs_base64.h"
#include <algorithm>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <limits>
#include <string>
#include <vector>
#include <array>
#include <thread>
#include <sys/wait.h>
#include <unistd.h>

namespace oracle {
size_t base64_encode(const unsigned char *, size_t, char *);
size_t base64_decode(const char *, size_t, char *);
}
void original_base64_encode();
void original_base64_decode();

static uint64_t state = 0x151b09835a46f7d3;
static uint8_t random_byte() {
    state ^= state << 13; state ^= state >> 7; state ^= state << 17;
    return static_cast<uint8_t>(state);
}
static size_t encodes = 0, decodes = 0;

static void compare(const std::vector<uint8_t> &bytes, bool encode) {
    // Prefix offsets deliberately exercise unaligned input/output. All output
    // bytes, including provisional writes and both red zones, must match.
    auto input = bytes;
    input.insert(input.begin(), 0xa5);
    for (uint8_t sentinel : {0x00, 0xa5, 0xff}) {
        size_t capacity = encode ? (bytes.size() + 2) / 3 * 4 + 1 : bytes.size() + 1;
        std::vector<char> expected(capacity + 34, static_cast<char>(sentinel));
        auto actual = expected;
        const auto *in = input.data() + 1;
        size_t a, b;
        if (encode) {
            a = oracle::base64_encode(in, bytes.size(), expected.data() + 17);
            b = swoole::base64_encode(in, bytes.size(), actual.data() + 17);
            ++encodes;
        } else {
            a = oracle::base64_decode(reinterpret_cast<const char *>(in), bytes.size(), expected.data() + 17);
            b = swoole::base64_decode(reinterpret_cast<const char *>(in), bytes.size(), actual.data() + 17);
            ++decodes;
        }
        if (a != b || actual != expected) {
            std::cerr << "Mismatch encode=" << encode << " length=" << bytes.size() << " input=";
            for (auto c : bytes) std::cerr << std::hex << unsigned(c) << ',';
            std::cerr << std::endl;
            std::abort();
        }
    }
}

static int benchmark(bool check_only, bool positive_only = false, bool encode_only = false) {
    // Preparation exercises every exact workload without reading the clock.
    // Timing still requires an acknowledged host-wide exclusive lease.
    struct Workload { const char *name; bool decode; std::vector<uint8_t> bytes; };
    std::vector<Workload> workloads;
    for (size_t length : {1, 2, 3, 20, 64, 1024, 65536}) {
        std::vector<uint8_t> input(length);
        for (auto &c : input) c = random_byte();
        if (encode_only) {
            workloads.push_back({"valid", false, std::move(input)});
        } else {
            std::vector<uint8_t> coded((length + 2) / 3 * 4 + 1);
            coded.resize(oracle::base64_encode(input.data(), input.size(), reinterpret_cast<char *>(coded.data())));
            workloads.push_back({"valid", false, std::move(input)});
            workloads.push_back({"valid", true, std::move(coded)});
        }
    }
    if (!positive_only) for (const char *value : {"!m9v", "Zm!v", "Zm9v!", "Z", "Zh"}) {
        std::string text(value);
        workloads.push_back({value, true, {text.begin(), text.end()}});
    }
    for (const auto &workload : workloads) compare(workload.bytes, !workload.decode);
    if (check_only) {
        std::cout << "{\"preflight_passed\":true,\"workloads\":" << workloads.size()
                  << ",\"positive_only\":" << (positive_only ? "true" : "false")
                  << ",\"encode_only\":" << (encode_only ? "true" : "false")
                  << ",\"encodes\":" << encodes << ",\"decodes\":" << decodes
                  << ",\"timed\":false}" << std::endl;
        return 0;
    }
    uint64_t checksum = 0;
    std::cout << "{\"errors\":0,\"trials\":7,\"positive_only\":" << (positive_only ? "true" : "false") << ",\"samples\":[";
    bool first = true;
    for (const auto &workload : workloads) {
        const auto &input = workload.bytes;
        const size_t capacity = workload.decode ? input.size() + 1 : (input.size() + 2) / 3 * 4 + 1;
        std::vector<char> output(capacity);
        const size_t iterations = std::max<size_t>(1, 8 * 1024 * 1024 / input.size());
        for (unsigned trial = 0; trial < 7; ++trial) {
            for (unsigned position = 0; position < 2; ++position) {
                const bool rust = (position + trial) % 2;
                auto encoder = rust ? swoole::base64_encode : oracle::base64_encode;
                auto decoder = rust ? swoole::base64_decode : oracle::base64_decode;
                std::fill(output.begin(), output.end(), static_cast<char>(0xa5));
                const auto start = std::chrono::steady_clock::now();
                for (size_t i = 0; i < iterations; ++i) {
                    const size_t n = workload.decode ? decoder(reinterpret_cast<const char *>(input.data()), input.size(), output.data())
                                                     : encoder(input.data(), input.size(), output.data());
                    // Invalid or one-sextet input returns zero; still observe
                    // its partial/untouched output without modulo-by-zero.
                    checksum += n + static_cast<uint8_t>(output[n ? i % n : 0]);
                }
                const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(
                    std::chrono::steady_clock::now() - start).count();
                if (!first) std::cout << ',';
                first = false;
                std::cout << "{\"engine\":\"" << (rust ? "rust" : "upstream") << "\",\"operation\":\""
                          << (workload.decode ? "decode" : "encode") << "\",\"workload\":\"" << workload.name
                          << "\",\"length\":" << input.size() << ",\"trial\":" << trial
                          << ",\"iterations\":" << iterations << ",\"nanoseconds\":" << elapsed << '}';
            }
        }
    }
    std::cout << "],\"checksum\":" << checksum << '}' << std::endl;
    return 0;
}

static void concurrent_and_fork_calls() {
    std::vector<uint8_t> input(257);
    for (size_t i = 0; i < input.size(); ++i) input[i] = static_cast<uint8_t>(i);
    std::vector<char> coded((input.size() + 2) / 3 * 4 + 1, '\0');
    const auto n = oracle::base64_encode(input.data(), input.size(), coded.data());
    auto check = [&] {
        std::vector<char> encoded(coded.size(), '\0'), decoded(input.size() + 1, '\0');
        assert(swoole::base64_encode(input.data(), input.size(), encoded.data()) == n);
        assert(encoded == coded);
        // Decoder requires encoded length + 1 writable bytes, even when the
        // resulting plaintext is shorter. Keep that frozen allocation contract.
        decoded.resize(n + 1);
        assert(swoole::base64_decode(coded.data(), n, decoded.data()) == input.size());
        assert(std::equal(input.begin(), input.end(), decoded.begin(),
                          [](uint8_t a, char b) { return a == static_cast<uint8_t>(b); }));
        assert(decoded[input.size()] == 0);
    };
    std::array<std::thread, 8> threads;
    for (auto &thread : threads) thread = std::thread([&] { for (int i = 0; i < 100; ++i) check(); });
    for (auto &thread : threads) thread.join();
    const auto pid = fork();
    assert(pid >= 0);
    if (pid == 0) { check(); _exit(0); }
    int status = -1;
    assert(waitpid(pid, &status, 0) == pid);
    assert(WIFEXITED(status) && WEXITSTATUS(status) == 0);
}

int main(int argc, char **argv) {
    if (argc == 2 && std::string(argv[1]) == "--check-encode-positive-benchmark") return benchmark(true, true, true);
    if (argc == 2 && std::string(argv[1]) == "--encode-positive-benchmark") return benchmark(false, true, true);
    if (argc == 2 && std::string(argv[1]) == "--check-positive-benchmark") return benchmark(true, true);
    if (argc == 2 && std::string(argv[1]) == "--positive-benchmark") return benchmark(false, true);
    if (argc == 2 && std::string(argv[1]) == "--benchmark") return benchmark(false);
    if (argc == 2 && std::string(argv[1]) == "--check-benchmark") return benchmark(true);
    if (argc == 2 && std::string(argv[1]) == "--encode-positive") {
        original_base64_encode();
        for (unsigned a = 0; a < 256; ++a) {
            compare({static_cast<uint8_t>(a)}, true);
            for (unsigned b = 0; b < 256; ++b)
                compare({static_cast<uint8_t>(a), static_cast<uint8_t>(b)}, true);
        }
        for (size_t length : {3, 4, 5, 7, 8, 9, 15, 16, 17, 63, 64, 65, 127, 128, 129, 1023, 1024, 1025, 65535, 65536, 65537}) {
            std::vector<uint8_t> bytes(length);
            for (auto &byte : bytes) byte = random_byte();
            compare(bytes, true);
        }
        std::cout << "{\"passed\":true,\"encode_positive_only\":true,\"encodes\":" << encodes
                  << ",\"decodes\":0,\"concurrent_calls\":0,\"fork_child\":false}" << std::endl;
        return 0;
    }
    if (argc == 2 && std::string(argv[1]) == "--decode-positive") {
        original_base64_decode();
        auto canonical = [](const std::vector<uint8_t> &bytes) {
            std::vector<uint8_t> coded((bytes.size() + 2) / 3 * 4 + 1);
            coded.resize(oracle::base64_encode(bytes.data(), bytes.size(), reinterpret_cast<char *>(coded.data())));
            compare(coded, false);
        };
        for (unsigned a = 0; a < 256; ++a) {
            canonical({static_cast<uint8_t>(a)});
            for (unsigned b = 0; b < 256; ++b)
                canonical({static_cast<uint8_t>(a), static_cast<uint8_t>(b)});
        }
        for (size_t length : {3, 4, 5, 7, 8, 9, 15, 16, 17, 63, 64, 65, 127, 128, 129, 1023, 1024, 1025, 65535, 65536, 65537}) {
            std::vector<uint8_t> bytes(length);
            for (auto &byte : bytes) byte = random_byte();
            canonical(bytes);
        }
        std::cout << "{\"passed\":true,\"decode_positive_only\":true,\"encodes\":0,\"decodes\":" << decodes
                  << ",\"concurrent_calls\":0,\"fork_child\":false}" << std::endl;
        return 0;
    }
    original_base64_encode();
    original_base64_decode();
    concurrent_and_fork_calls();
    // Empty encode is an explicit defensive Rust definition: never call the
    // undefined upstream encoder with zero length, including in sanitizer runs.
    uint8_t output[16];
    std::fill(std::begin(output), std::end(output), 0xa5);
    assert(swr_v1_base64_encode(nullptr, 0, output) == 0 && output[0] == 0);
    assert(std::all_of(output + 1, output + 16, [](auto v) { return v == 0xa5; }));
    for (auto function : {swr_v1_base64_encode, swr_v1_base64_decode}) {
        std::fill(std::begin(output), std::end(output), 0xa5);
        assert(function(nullptr, 1, output) == 0);
        assert(function(output, 1, nullptr) == 0);
        assert(function(output, std::numeric_limits<size_t>::max(), output + 8) == 0);
        assert(std::all_of(output, output + 16, [](auto v) { return v == 0xa5; }));
    }
    compare({}, false);
    for (unsigned a = 0; a < 256; ++a) {
        compare({static_cast<uint8_t>(a)}, true);
        compare({static_cast<uint8_t>(a)}, false);
        for (unsigned b = 0; b < 256; ++b) {
            std::vector<uint8_t> bytes{static_cast<uint8_t>(a), static_cast<uint8_t>(b)};
            compare(bytes, true);
            compare(bytes, false);
        }
    }
    // Exhaust all short strings of representative valid sextets, padding,
    // internal punctuation, whitespace, NUL and high bytes.
    const std::vector<uint8_t> alphabet{'A', 'Z', 'a', '9', '+', '/', '=', '!', ' ', 0, 0xff};
    for (size_t length = 1, combinations = alphabet.size(); length <= 5; ++length, combinations *= alphabet.size()) {
        for (size_t code = 0; code < combinations; ++code) {
            auto value = code;
            std::vector<uint8_t> bytes(length);
            for (auto &byte : bytes) { byte = alphabet[value % alphabet.size()]; value /= alphabet.size(); }
            compare(bytes, false);
        }
    }
    // Every byte at each position through two quartets, exercising the entire
    // decoder classification table, immediate '=', and invalid-data partial writes.
    for (size_t length = 1; length <= 8; ++length) {
        for (size_t position = 0; position < length; ++position) {
            for (unsigned value = 0; value < 256; ++value) {
                std::vector<uint8_t> bytes(length, '/');
                bytes[position] = static_cast<uint8_t>(value);
                compare(bytes, false);
            }
        }
    }
    for (size_t trial = 0; trial < 4096; ++trial) {
        const size_t length = trial < 256 ? trial + 1 : (random_byte() * 16 + random_byte() % 16 + 1);
        std::vector<uint8_t> bytes(length);
        for (auto &byte : bytes) byte = random_byte();
        compare(bytes, true);
        compare(bytes, false);
        std::vector<uint8_t> coded((length + 2) / 3 * 4 + 1);
        coded.resize(oracle::base64_encode(bytes.data(), length, reinterpret_cast<char *>(coded.data())));
        compare(coded, false);
        for (size_t trim = 1; trim <= 3 && trim < coded.size(); ++trim) {
            compare({coded.begin(), coded.end() - trim}, false);
        }
    }
    std::cout << "{\"passed\":true,\"original_core_tests\":2,\"encode_comparisons\":" << encodes
              << ",\"decode_comparisons\":" << decodes
              << ",\"concurrent_calls\":1600,\"fork_child\":true,\"empty_encode_oracle_excluded\":true}" << std::endl;
}
