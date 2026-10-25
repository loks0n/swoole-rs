#include "oracle.h"
#include <iostream>
#include <vector>
#include <csetjmp>
#include <climits>
void run_original_assertions();
namespace {
void check(bool ok, const char *message) { if (!ok) throw std::runtime_error(message); }
std::jmp_buf bailout;
bool bailout_next = false;
bool allocation_failure = false;
unsigned allocations = 0;
}
void *sw_malloc(size_t n) { if (bailout_next) std::longjmp(bailout, 1); ++allocations; return allocation_failure ? nullptr : std::malloc(n); }
void sw_free(void *p) { std::free(p); }
size_t sw_snprintf(char *data, size_t size, const char *format, ...) {
    va_list args; va_start(args, format); int n = std::vsnprintf(data, size, format, args); va_end(args); return n < 0 ? 0 : size_t(n);
}
int main(int argc, char **argv) {
    if (argc == 2 && std::string(argv[1]) == "diagnose-reference-overflow") {
        auto result = upstream::url_encode("!", 1); sw_free(result); return 0;
    }
    try {
        if (argc == 2 && std::string(argv[1]) == "url-positive-only") {
            uint32_t random = 8293;
            auto next = [&]() { random ^= random << 13; random ^= random >> 17; random ^= random << 5; return random; };
            for (size_t n = 0; n < 4096; ++n) {
                // Existing defined-success corpus: leading unreserved byte
                // leaves pinned reference space for its terminator. No decode,
                // empty/fully-escaped reference, failure or diagnostic profile.
                std::string input("A");
                for (size_t i = 0; i < n % 257; ++i) input += char(next());
                auto before = upstream::url_encode(input.data(), input.size());
                allocations = 0; auto after = candidate::url_encode(input.data(), input.size());
                check(allocations == 1 && std::strcmp(before, after) == 0, "encoded bytes/single allocation");
                sw_free(before); sw_free(after);
            }
            std::cout << "{\"positive_encoding_cases\":4096,\"original_tests_executed\":0,\"errors\":0}\n";
            return 0;
        }
        run_original_assertions();
        unsigned cases = 0;
        for (int code = -128; code <= 1024; ++code) {
            check(std::strcmp(upstream::get_status_message(code), candidate::get_status_message(code)) == 0, "status differential"); ++cases;
        }
        for (int code : {INT_MIN, INT_MAX}) {
            check(std::strcmp(upstream::get_status_message(code), candidate::get_status_message(code)) == 0, "extreme status differential"); ++cases;
        }
        for (int id = -10; id < 40; ++id) {
            auto before = upstream::get_method_string(id), after = candidate::get_method_string(id);
            check((before == nullptr && after == nullptr) || (before && after && std::strcmp(before, after) == 0), "method string differential");
            if (before) {
                std::string lower(before); for (auto &c : lower) c = char(std::tolower(static_cast<unsigned char>(c)));
                check(upstream::get_method(lower.data(), lower.size()) == candidate::get_method(lower.data(), lower.size()), "lowercase method differential");
                lower += ' '; check(upstream::get_method(lower.data(), lower.size()) == candidate::get_method(lower.data(), lower.size()), "method exactness differential");
            }
            ++cases;
        }
        uint32_t random = 8293;
        auto next = [&]() { random ^= random << 13; random ^= random >> 17; random ^= random << 5; return random; };
        for (size_t n = 0; n < 4096; ++n) {
            // A leading unreserved byte leaves reference space for its terminator.
            std::string input("A"); for (size_t i = 0; i < n % 257; ++i) input += char(next());
            auto before = upstream::url_encode(input.data(), input.size());
            allocations = 0; auto after = candidate::url_encode(input.data(), input.size());
            check(allocations == 1 && std::strcmp(before, after) == 0, "encoded bytes/single allocation");
            std::vector<char> a(before, before + std::strlen(before) + 1), b(after, after + std::strlen(after) + 1);
            auto a_length = upstream::url_decode(a.data(), a.size() - 1), b_length = candidate::url_decode(b.data(), b.size() - 1);
            check(a_length == b_length && b_length == input.size() && std::memcmp(a.data(), b.data(), a_length + 1) == 0 && std::memcmp(b.data(), input.data(), input.size()) == 0, "binary URL roundtrip");
            sw_free(before); sw_free(after);
            std::string raw; for (size_t i = 0; i < n % 83; ++i) raw += "%+0aGZ19"[next() % 8];
            a.assign(raw.begin(), raw.end()); a.push_back(0); b = a;
            a_length = upstream::url_decode(a.data(), raw.size()); b_length = candidate::url_decode(b.data(), raw.size());
            check(a_length == b_length && std::memcmp(a.data(), b.data(), a_length + 1) == 0, "malformed URL differential");
            cases += 3;
        }
        const char *parameters[] = {"boundary=x", "BOUNDARY=x", "x=y; boundary=abc;next=z", "boundary=\"abc\"", "boundary=\"\"", "boundary=", "boundary = x", "boundary=x ", "boundary=x\0ignored", ";;; boundary=x", "boundary=x;", "x=boundary=q", "boundary=;", "boundary=\"x;y\""};
        for (auto text : parameters) {
            std::string input(text);
            for (size_t length = 0; length <= input.size(); ++length) for (size_t offset = 0; offset <= length + 1; ++offset) {
                char *a = const_cast<char *>("sentinel"), *b = a; int al = 3, bl = 3;
                bool found_a = upstream::parse_multipart_boundary(input.data(), length, offset, &a, &al);
                bool found_b = candidate::parse_multipart_boundary(input.data(), length, offset, &b, &bl);
                check(found_a == found_b && al == bl && (found_a ? std::string(a, al) == std::string(b, bl) : a == b), "boundary incremental/output differential"); ++cases;
            }
        }
        for (std::string input : {std::string(), std::string("!"), std::string("\0\xff", 2)}) {
            auto encoded = candidate::url_encode(input.data(), input.size()); std::vector<char> data(encoded, encoded + std::strlen(encoded) + 1);
            auto size = candidate::url_decode(data.data(), data.size() - 1);
            check(size == input.size() && std::memcmp(data.data(), input.data(), size) == 0, "corrected exact encoded allocation"); sw_free(encoded);
        }
        allocation_failure = true; bool allocation_failed = false;
        try { candidate::url_encode("A!", 2); } catch (const std::bad_alloc &) { allocation_failed = true; }
        allocation_failure = false; check(allocation_failed, "native allocation failure translation");
        if (setjmp(bailout) == 0) {
            bailout_next = true; candidate::url_encode("A!", 2); throw std::runtime_error("native allocator bailout missing");
        }
        bailout_next = false;
        std::cout << "{\"original_tests_per_engine\":5,\"differential_cases\":" << cases << ",\"corrected_boundary_groups\":3,\"native_allocator_failures\":1,\"native_allocator_bailouts\":1,\"errors\":0}\n";
    } catch (const std::exception &error) { std::cerr << error.what() << '\n'; return 1; }
}
