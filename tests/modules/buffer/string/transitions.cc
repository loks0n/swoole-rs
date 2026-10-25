// Positive owned transitions only: no unsafe zero allocation/overflow oracle.
#include "test_core.h"
#include <iostream>
#include <unordered_set>
using swoole::String;
namespace {
unsigned checks = 0, allocations = 0, frees = 0;
std::unordered_set<void *> live;
void check(bool ok, const char *message) {
    if (!ok) throw std::runtime_error(message);
    ++checks;
}
void *allocate(size_t size) {
    void *p = std::malloc(size);
    if (p) { live.insert(p); ++allocations; }
    return p;
}
void *resize(void *p, size_t size) {
    check(live.count(p) == 1, "native realloc custody");
    void *q = std::realloc(p, size);
    if (q) { live.erase(p); live.insert(q); }
    return q;
}
void dispose(void *p) {
    check(live.erase(p) == 1, "native disposal custody");
    ++frees; std::free(p);
}
const swoole::Allocator allocator{allocate, std::calloc, resize, dispose};
void empty_metadata(const String &value) {
    check(!value.str && !value.length && !value.size && !value.offset, "empty metadata");
    check(value.allocator == &allocator, "moved/released allocator retained");
}
}
int main() {
    SwooleG.std_allocator = {std::malloc, std::calloc, std::realloc, std::free};
    SwooleG.pagesize = 4096;
    try {
        for (size_t capacity : {size_t(8), size_t(16), size_t(64)}) {
            String source(capacity, &allocator); source.append("a\0b", 3); source.offset = 2;
            char *owner = source.str; unsigned before = frees;
            source.clear();
            check(source.str == owner && source.size == capacity && source.length == 0 && source.offset == 0,
                  "clear preserves allocation and resets logical fields");
            check(source.allocator == &allocator && frees == before, "clear has no allocation effect");
            source.append("x\0y", 3); source.offset = 1;
            String moved(std::move(source));
            check(moved.str == owner && moved.size == capacity && moved.length == 3 && moved.offset == 1,
                  "move retains owner and metadata");
            check(moved.allocator == &allocator && frees == before, "move preserves allocator/no disposal");
            empty_metadata(source);
            char *released = moved.release();
            check(released == owner && !std::memcmp(released, "x\0y", 3), "release exact detached owner bytes");
            empty_metadata(moved);
            check(frees == before && live.count(released) == 1, "release does not free");
            dispose(released);
        }
        {
            String source(16, &allocator), target(8, &allocator);
            source.append("abc", 3); source.offset = 2; target.append("old", 3);
            char *owner = source.str; char *old = target.str; unsigned before = frees;
            target = std::move(source);
            check(target.str == owner && target.length == 3 && target.offset == 2, "move assignment metadata");
            check(frees == before + 1 && !live.count(old), "move assignment disposes destination first");
            empty_metadata(source);
            auto *same = &target;
            target = std::move(*same);
            check(target.str == owner && target.length == 3 && frees == before + 1, "self assignment unchanged");
            char *detached = target.release(); dispose(detached);
        }
        for (size_t reported : {size_t(7), size_t(15), size_t(33), size_t(64)}) {
            String value(64, &allocator); value.append("abc", 3);
            value.size = reported; // Public metadata advertises a readable prefix of its allocation.
            value.extend();
            check(value.size == SW_MEM_ALIGNED_SIZE(reported * 2), "positive double-and-align capacity");
            check(value.to_std_string() == "abc", "capacity transition preserves bytes");
        }
        for (bool full : {false, true}) {
            String value(8, &allocator);
            const char *bytes = full ? "12345678" : "abc";
            const size_t length = full ? 8 : 3;
            value.append(bytes, length); value.offset = 1;
            value.set_null_terminated();
            check(value.length == length && value.offset == 1, "NUL retains logical metadata");
            check(value.size == (full ? 16 : 8), "NUL precise capacity");
            check(value.str[length] == 0 && !std::memcmp(value.str, bytes, length), "NUL and initialized prefix");
        }
        {
            char bytes[8] = {'a', 'b', 'c', 'z'};
            String borrowed; borrowed.str = bytes; borrowed.size = sizeof(bytes);
            borrowed.length = 3; borrowed.offset = 1;
            borrowed.set_null_terminated();
            check(bytes[3] == 0 && !std::memcmp(bytes, "abc", 3), "borrowed writable terminator bytes");
            check(borrowed.allocator == nullptr && borrowed.str == bytes && borrowed.length == 3 &&
                  borrowed.size == sizeof(bytes) && borrowed.offset == 1, "borrowed terminator never adopts owner");
        }
        {
            String literal("abc");
            check(literal.length == 3 && literal.str[3] == 0 && literal.to_std_string() == "abc", "byte constructor NUL");
            String binary(std::string("a\0b", 3));
            check(binary.length == 3 && binary.str[3] == 0 && binary.to_std_string() == std::string("a\0b", 3), "delegating binary constructor NUL");
        }
        check(live.empty(), "all native owners disposed");
        check(allocations == frees, "native allocation/free balance");
        std::cout << "{\"positive_transition_checks\":" << checks << ",\"native_allocations\":"
                  << allocations << ",\"native_frees\":" << frees << ",\"errors\":0}\n";
    } catch (const std::exception &error) { std::cerr << error.what() << '\n'; return 1; }
}
