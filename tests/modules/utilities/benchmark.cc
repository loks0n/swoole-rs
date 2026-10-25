#include <algorithm>
#include <cassert>
#include <cerrno>
#include <cctype>
#include <unistd.h>
#include <chrono>
#include <climits>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>
#include "swoole_rs_utilities.h"
#include "benchmark-config.h"
#ifdef HAVE_FUTEX
#include <linux/futex.h>
#include <sys/syscall.h>
#endif
using sw_atomic_t = volatile uint32_t;
#define sw_atomic_cmp_set(p,a,b) __sync_bool_compare_and_swap(p,a,b)
#define sw_atomic_sub_fetch(p,n) __sync_sub_and_fetch(p,n)
#define sw_atomic_fetch_add(p,n) __sync_fetch_and_add(p,n)
#define sw_likely(x) (x)
namespace reference {
using ulong_t = unsigned long;
#include "oracle.inc"
#include "benchmark-bytes.inc"
#include "benchmark-wait.inc"
}

// Real pinned bodies and published FFI, with ordinary reduction/call overhead.
// Unsigned char makes every hash input defined, including Austin's shifts.
__attribute__((noinline)) static uint64_t work(const std::string &name, bool rust, const std::string &input) {
    // Equal compiler-only barrier prevents loop-invariant native calls being
    // hoisted while the opaque external Rust call remains in every iteration.
    asm volatile("" ::: "memory");
    if (name.compare(0, 10, "lowercase-") == 0) {
        // Same native writable storage/copy and full output reduction for both.
        std::string output(input);
        if (rust) swr_v1_utils_lowercase(reinterpret_cast<uint8_t *>(output.data()), output.size(), 0);
        else reference::swoole_strtolower(output.data(), output.size());
        uint64_t checksum = output.size();
        for (unsigned char byte : output) checksum = checksum * 33 + byte;
        return checksum;
    }
    if (name.compare(0, 5, "hash-") == 0) {
        const unsigned algorithm = name[5] - '0';
        if (rust) return swr_v1_utils_hash(reinterpret_cast<const uint8_t *>(input.data()), input.size(), algorithm, 0);
        switch (algorithm) {
        case 0: return reference::swoole_hash_php(input.data(), input.size());
        case 1: return reference::swoole_hash_jenkins(input.data(), input.size());
        case 2: return reference::swoole_hash_austin(input.data(), input.size());
        }
    }
    if (name == "pretty") {
        if (!rust) {
            auto result = reference::pretty(input, true);
            return result.size() + (result.empty() ? 0 : static_cast<unsigned char>(result[0]));
        }
        size_t begin = 0, count = 0;
        if (swr_v1_utils_pretty_range(reinterpret_cast<const uint8_t *>(input.data()), input.size(), 1, &begin, &count))
            throw std::runtime_error("pretty span rejected");
        // Same native std::string storage operation as the integrated facade.
        auto result = input.substr(begin, count);
        return result.size() + (result.empty() ? 0 : static_cast<unsigned char>(result[0]));
    }
    const auto *data=reinterpret_cast<const uint8_t *>(input.data());
    const char *needle="needle"; const size_t length=6;
    if(name=="trim-left") { char *cursor=const_cast<char *>(input.data()); return rust ? swr_v2_utils_ltrim(&cursor,input.size(),0) : reference::ltrim(&cursor,input.size()); }
    if(name=="trim-right") return rust ? swr_v1_utils_trim(data,input.size(),1,0) : reference::rtrim(input.data(),input.size());
    if(name.compare(0,5,"find-")==0) {
        const unsigned mode=name=="find-binary" ? 0 : name=="find-casefold" ? 1 : 2;
        if(rust) return swr_v2_utils_search(input.data(),input.size(),needle,length,mode).offset;
        if(mode==2) return reference::swoole_strrnpos(input.data(),needle,input.size());
        const char *found=mode ? reference::swoole_strncasestr(input.data(),input.size(),needle,length) : reference::swoole_strnstr(input.data(),input.size(),needle,length);
        return found ? found-input.data() : -1;
    }
    if(name.compare(0,8,"compare-")==0) {
        const unsigned mode=static_cast<unsigned>(name.back()-'0');
        static const std::string compared(96,'x');
        if(rust) return swr_v1_utils_compare(data,input.size(),reinterpret_cast<const uint8_t *>(compared.data()),compared.size(),mode);
        switch(mode) {
        case 0:return reference::swoole_streq(input.data(),input.size(),compared.data(),compared.size());
        case 1:return reference::swoole_strcaseeq(input.data(),input.size(),compared.data(),compared.size());
        case 2:return reference::swoole_str_starts_with(input.data(),input.size(),compared.data(),compared.size());
        case 3:return reference::swoole_str_istarts_with(input.data(),input.size(),compared.data(),compared.size());
        case 4:return reference::starts_with(input,compared);
        case 5:return reference::ends_with(input.data(),input.size(),compared.data(),compared.size());
        }
    }
    if(name=="partition-before" || name=="partition-after") {
        const bool before=name=="partition-before";
        return rust ? swr_v1_utils_partition(data,input.size(),'n',before) : reference::substr_len(input.data(),input.size(),'n',before);
    }
    if(name=="policy-level") return rust ? swr_v1_utils_log_level(99) : reference::log_level(99);
    if(name=="policy-label" || name=="policy-rotation") {
        const char *value=name=="policy-label" ? (rust ? swr_v1_utils_log_label(4) : reference::log_label(4)) :
                                                (rust ? swr_v1_utils_log_rotation(3) : reference::log_rotation(3));
        return std::strlen(value)+static_cast<unsigned char>(value[0]);
    }
    if(name=="wait-ready" || name=="wake-ready") {
        alignas(uint32_t) uint32_t word=1; errno=EDOM;
#ifdef HAVE_FUTEX
        const unsigned futex=1;
#else
        const unsigned futex=0;
#endif
        const int result=name=="wait-ready" ? (rust ? swr_v1_utils_wait(&word,0,futex) : reference::sw_atomic_futex_wait(&word,0)) :
                                              (rust ? swr_v1_utils_wakeup(&word,1,futex) : reference::sw_atomic_futex_wakeup(&word,1));
        return static_cast<uint64_t>(word)+static_cast<uint64_t>(result)+static_cast<unsigned>(errno);
    }
    char output[256];
    size_t count;
    if (name == "micros") {
        count = rust ? swr_v1_utils_log_micros(reinterpret_cast<uint8_t *>(output), sizeof(output), 123456)
                     : reference::log_micros(output, sizeof(output), 123456);
    } else if (name == "line" || name == "truncated-line") {
        const size_t capacity = name == "line" ? sizeof(output) : 32;
        const char *date = "2026-10-24 02:00:00";
        count = rust ? swr_v1_utils_log_line(reinterpret_cast<uint8_t *>(output), capacity,
                                            reinterpret_cast<const uint8_t *>(date), 19, '@', 12345, 7, 4,
                                            reinterpret_cast<const uint8_t *>(input.data()), input.size())
                     : reference::log_line(output, capacity, date, 19, '@', 12345, 7, 4, input.data(), input.size());
    } else throw std::runtime_error("unknown workload");
    uint64_t checksum = count;
    for (size_t i = 0; i < count; ++i) checksum = checksum * 33 + static_cast<unsigned char>(output[i]);
    return checksum;
}

int main(int argc, char **argv) {
    try {
        if (argc != 5) throw std::runtime_error("--check|--measure native|rust workload iterations required");
        const std::string mode = argv[1], engine = argv[2], name = argv[3];
        const bool rust = engine == "rust";
        if (engine != "native" && !rust) throw std::runtime_error("unknown engine");
        if (mode != "--check" && mode != "--measure") throw std::runtime_error("unknown mode");
        size_t consumed = 0;
        const uint64_t iterations = std::stoull(argv[4], &consumed);
        if (!iterations || consumed != std::strlen(argv[4]) || iterations > 1000000000)
            throw std::runtime_error("invalid iteration count");
        std::string input = name == "pretty" ? "void namespace_name::LongClassName::method_name(int)" : std::string(96, 'x');
        if (name.compare(0, 5, "hash-") == 0) {
            const auto separator = name.find('-', 5);
            if (separator != 6 || name[5] < '0' || name[5] > '2') throw std::runtime_error("invalid hash workload");
            const auto length = std::stoul(name.substr(separator + 1), &consumed);
            if (consumed != name.size() - separator - 1 || (length != 32 && length != 256 && length != 4096))
                throw std::runtime_error("invalid hash length");
            input.resize(length);
            for (size_t i = 0; i < length; ++i) input[i] = static_cast<char>((i * 37 + 13) & 255);
        }
        if (name.compare(0, 10, "lowercase-") == 0) {
            const auto length = std::stoul(name.substr(10), &consumed);
            if (consumed != name.size() - 10 || (length != 32 && length != 256 && length != 4096))
                throw std::runtime_error("invalid lowercase length");
            input.resize(length);
            for (size_t i = 0; i < length; ++i) input[i] = static_cast<char>((i * 37 + 13) & 255);
        }
        if(name.compare(0,5,"trim-")==0) input="   \t"+input+" \n";
        if(name.compare(0,5,"find-")==0 || name.compare(0,10,"partition-")==0) input.replace(48,6,"needle");
        const auto expected = work(name, false, input);
        if (work(name, true, input) != expected) throw std::runtime_error("native/Rust warmup mismatch");
        uint64_t checksum = 0;
        // Only explicit measurement mode reads the clock. Preparation never does.
        std::chrono::steady_clock::time_point start;
        if (mode == "--measure") start = std::chrono::steady_clock::now();
        for (uint64_t i = 0; i < iterations; ++i) checksum += work(name, rust, input);
        const auto ns = mode == "--measure" ? std::chrono::duration_cast<std::chrono::nanoseconds>(
                                                  std::chrono::steady_clock::now() - start).count() : 0;
        if (checksum != expected * iterations) throw std::runtime_error("checksum mismatch");
        std::cout << "{\"workload\":\"" << name << "\",\"engine\":\"" << engine << "\",\"iterations\":" << iterations
                  << ",\"checksum\":" << checksum << ",\"elapsed_ns\":" << ns << "}\n";
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
