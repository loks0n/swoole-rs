#include "swoole_string.h"
#include "system-allocator.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <new>
using swoole::String;
static void require(bool ok, const char *message) { if (!ok) throw message; }
static void bytes(const String &s, size_t length) {
    require(s.length == length, "length");
    for (size_t i = 0; i < length; ++i) require(static_cast<unsigned char>(s.str[i]) == i % 256, "bytes");
}
int main(int argc, char **argv) {
    if (argc < 2) return 2;
    SwooleG.std_allocator = {std::malloc, std::calloc, std::realloc, std::free}; SwooleG.pagesize = 4096;
    const char *scenario = argv[1], *error = nullptr;
    const long failure_index = argc > 2 ? std::strtol(argv[2], nullptr, 10) : -1;
    bool failed = false, dangling = false; size_t abandoned_zero_owners = 0;
    char block[256]; for (size_t i = 0; i < 256; ++i) block[i] = static_cast<char>(i);
    // Initialize libc++ exception thread bookkeeping before recording String ownership.
    try { throw std::bad_alloc(); } catch (const std::bad_alloc &) {}
    try { throw "warm exception bookkeeping"; } catch (const char *) {}
    swr_test_allocator_begin(!std::strcmp(scenario, "cold") && failure_index >= 0 ? failure_index + 1 : -1);
    try {
        if (!std::strcmp(scenario, "cold")) {
            String value(64);
            for (unsigned i = 0; i < 16; ++i) {
                char *old = value.str; const auto capacity = value.size; value.offset = i ? 1 : 0;
                try { value.append(block, sizeof(block)); }
                catch (const std::bad_alloc &) {
                    failed = true; require(long(i) == failure_index && value.str == old && value.size == capacity &&
                        value.offset == (i ? 1 : 0), "cold failure ownership"); bytes(value, i * 256); break;
                }
                require(value.str != old && value.size == (i + 1) * 256, "exact moved growth");
                bytes(value, (i + 1) * 256);
            }
            require(failed == (failure_index >= 0), "cold failure not reached");
        } else if (!std::strcmp(scenario, "malloc-failure")) {
            swr_test_allocator_end(); swr_test_allocator_begin(0);
            try { String value(8); } catch (const std::bad_alloc &) { failed = true; }
            require(failed, "constructor did not fail");
        } else if (!std::strcmp(scenario, "calloc")) {
            auto *p = static_cast<unsigned char *>(std::calloc(8, 4)); require(p, "calloc allocation");
            for (size_t i = 0; i < 32; ++i) require(p[i] == 0, "calloc bytes"); std::free(p);
        } else if (!std::strcmp(scenario, "calloc-failure")) {
            swr_test_allocator_end(); swr_test_allocator_begin(0);
            auto *p = std::calloc(8, 4); require(!p, "calloc did not fail"); failed = true;
        } else if (!std::strcmp(scenario, "realloc-null")) {
            auto *p = static_cast<unsigned char *>(std::realloc(nullptr, 16)); require(p, "realloc null");
            std::memset(p, 0xab, 16); auto *q = static_cast<unsigned char *>(std::realloc(p, 32));
            require(q && q != p, "realloc null owner did not move");
            for (size_t i = 0; i < 16; ++i) require(q[i] == 0xab, "realloc prefix");
            std::free(q); std::free(nullptr);
        } else if (!std::strcmp(scenario, "alias-rebase-failure")) {
            swr_test_allocator_end(); swr_test_allocator_begin(1);
            String value(8); value.append("abcdef", 6); value.offset = 3; char *old = value.str;
            try { value.append(value.str + 1, 5); } catch (const std::bad_alloc &) { failed = true; }
            require(failed && value.str == old && value.length == 6 && value.size == 8 && value.offset == 3 &&
                    !std::memcmp(value.str, "abcdef", 6), "alias failure ownership");
        } else if (!std::strcmp(scenario, "alias-defined")) {
            String value(16); value.append("abcdef", 6); value.append(value.str + 1, 3);
            require(value.length == 9 && !std::memcmp(value.str, "abcdefbcd", 9), "disjoint interior append");
        } else if (!std::strcmp(scenario, "alias-rebase")) {
            String value(8); value.append("abcdef", 6); char *old = value.str;
            value.append(value.str + 1, 5);
            require(value.str != old && value.size == 16 && value.length == 11 &&
                    !std::memcmp(value.str, "abcdefbcdef", 11), "interior rebase");
        } else if (!std::strcmp(scenario, "zero-owned-grow")) {
            char *old;
            { String value(0); old = value.str; value.reserve(16);
              require(value.size == 16 && value.length == 0, "zero growth state"); }
            if (swr_test_allocator_live(old)) { abandoned_zero_owners = 1; std::free(old); }
        } else if (!std::strcmp(scenario, "zero-shrink")) {
            String value(8); char *old = value.str;
            try { value.reserve(0); } catch (const std::bad_alloc &) { failed = true; }
            dangling = failed && value.str == old && !swr_test_allocator_live(old);
            // Preserve and report the dangling reference without making fixture cleanup double-free it.
            if (dangling) value.str = nullptr;
            else require(value.size == 0 && value.length == 0, "zero shrink state");
        } else throw "unknown scenario";
    } catch (const char *message) { error = message; }
      catch (...) { error = "unexpected exception"; }
    const auto trace = swr_test_allocator_end();
    std::printf("{\"scenario\":\"%s\",\"failure_index\":%ld,\"operation_failed\":%s,\"dangling_owner\":%s,"
                "\"abandoned_zero_owners\":%zu,\"live_after_cleanup\":%zu,\"error\":", scenario, failure_index,
                failed ? "true" : "false", dangling ? "true" : "false", abandoned_zero_owners, trace.live);
    if (error) std::printf("\"%s\"", error); else std::printf("null");
    std::printf(",\"events\":[");
    for (size_t i = 0; i < trace.count; ++i) {
        const auto &e = trace.events[i];
        std::printf("%s{\"operation\":\"%c\",\"size\":%zu,\"failed\":%s,\"moved\":%s}", i ? "," : "", e.operation,
                    e.size, e.failed ? "true" : "false", e.moved ? "true" : "false");
    }
    std::puts("]}"); return error || trace.live ? 1 : 0;
}
