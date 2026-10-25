#include "range_oracle.h"
#include <cstdarg>
#include <cstdio>
#include <iostream>
#include <limits>
#include <cstdlib>
#include <new>
#include <cerrno>
#include "allocation_oracle.h"
void check(bool ok, const char *message) { if (!ok) throw std::runtime_error(message); }
int main() {
    try {
        unsigned cases = 0, faults = 0, formats = 0;
        auto equal = [&](const auto &before, const auto &after) {
            check(before.status_code == after.status_code && before.content_length == after.content_length && before.end_part == after.end_part && before.date_calls == after.date_calls && before.tasks.size() == after.tasks.size(), "range policy/accounting differential");
            for (size_t i = 0; i < before.tasks.size(); ++i) {
                auto &a = before.tasks[i]; auto &b = after.tasks[i];
                check(a.offset == b.offset && a.length == b.length && std::memcmp(a.part_header, b.part_header, sizeof(a.part_header)) == 0, "range task/header differential");
            }
        };
        auto compare = [&](const char *range, const char *date, size_t size, bool prior) {
            upstream_range::StaticHandler before(size); candidate_range::StaticHandler after(size);
            if (prior) {
                before.tasks.push_back({3, 4, "previous"}); after.tasks.push_back({3, 4, "previous"});
                before.content_length = after.content_length = 19; before.status_code = after.status_code = 299;
            }
            before.parse_range(range, date); after.parse_range(range, date);
            equal(before, after);
            ++cases;
        };
        const std::vector<std::string> ranges = {"", "items=0-1", "bytes=", "bytes=0-0", "BYTES=0-1", "bytes=0-", "bytes=-0", "bytes=-1", "bytes=-100", "bytes=0-1,2-3", "bytes=99-100,1-2", "bytes=0-1,bad", "bytes= 0 - 1 , -2", "bytes=0-1,", "bytes=0-1,\r\n", "bytes=0-1\rjunk", "bytes=1--2", "bytes=- 2", "bytes=0-1,,2-3", "bytes=99999999999999999999999999999999-1", "bytes=0-18446744073709551615,0-1"};
        for (size_t size : {size_t(0), size_t(1), size_t(10), size_t(100), std::numeric_limits<size_t>::max()}) {
            for (const char *date : {static_cast<const char *>(nullptr), "", "same", "modified"}) for (bool prior : {false, true}) {
                compare(nullptr, date, size, prior);
                for (auto &range : ranges) for (size_t n = 0; n <= range.size(); ++n) {
                    auto prefix = range.substr(0, n); compare(prefix.c_str(), date, size, prior);
                }
            }
        }
        uint32_t seed = 91231;
        auto next = [&]() { seed ^= seed << 13; seed ^= seed >> 17; seed ^= seed << 5; return seed; };
        for (unsigned step = 0; step < 8192; ++step) {
            std::string range = "bytes="; unsigned parts = 1 + next() % 5;
            for (unsigned i = 0; i < parts; ++i) {
                if (i) range += ',';
                if (next() % 2) range += std::to_string(next() % 150);
                range += '-'; if (next() % 2) range += std::to_string(next() % 150);
                if (next() % 9 == 0) range += 'x';
            }
            compare(range.c_str(), step % 3 ? nullptr : "modified", next() % 150, step % 2);
        }
        // Full pinned methods, large/binary inputs and every allocation failure.
        for (size_t boundary_size : {size_t(0), size_t(14), size_t(23), size_t(24), size_t(31), size_t(100), size_t(500), size_t(1024)}) {
            for (bool binary : {false, true}) for (bool prior : {false, true}) {
                for (const char *range : {"bytes=0-1,3-4", "bytes=0-1", "bytes=", "items=0-1"}) {
                    for (const char *date : {static_cast<const char *>(nullptr), "modified", "a-long-nonmodified-date-with-allocation"}) {
                        size_t total = 0;
                        for (size_t nth = 0; nth <= total; ++nth) {
                            upstream_range::StaticHandler before(100); candidate_range::StaticHandler after(100);
                            before.boundary = after.boundary = std::string(boundary_size, 'b');
                            before.mime = after.mime = std::string(boundary_size, 'm');
                            if (binary && boundary_size) { before.boundary[boundary_size/2] = after.boundary[boundary_size/2] = 0; before.mime[boundary_size/2] = after.mime[boundary_size/2] = 0; }
                            if (prior) { before.tasks.push_back({3, 4, "previous"}); after.tasks.push_back({3, 4, "previous"}); }
                            before.content_length = after.content_length = 19;
                            before.status_code = after.status_code = 299;
                            before.end_part = after.end_part = "previous-ending-boundary";
                            bool old_failed = false, new_failed = false;
                            size_t old_sizes[128] = {}, old_count;
                            allocation::begin(nth);
                            try { before.parse_range(range, date); } catch (const std::bad_alloc &) { old_failed = true; }
                            allocation::end(); old_count = allocation::count;
                            check(old_count <= 128, "allocation trace overflow");
                            std::copy(allocation::sizes, allocation::sizes + old_count, old_sizes);
                            allocation::begin(nth);
                            try { after.parse_range(range, date); } catch (const std::bad_alloc &) { new_failed = true; }
                            allocation::end();
                            check(old_failed == new_failed && old_count == allocation::count && std::equal(old_sizes, old_sizes + old_count, allocation::sizes), "allocation sequence differential");
                            equal(before, after);
                            if (!nth) { total = old_count; ++cases; } else ++faults;
                        }
                    }
                }
            }
        }
        for (const std::string &boundary : {std::string(), std::string("b\0tail", 6), std::string(1024, 'b')}) {
            for (const std::string &mime : {std::string("text/plain"), std::string("m\0tail", 6), std::string(1024, 'm')}) {
                for (bool separator : {false, true}) for (size_t offset : {size_t(0), size_t(17), SIZE_MAX}) {
                    for (size_t length : {size_t(0), size_t(1), SIZE_MAX}) {
                        swr_v1_http_range_format_input input{{reinterpret_cast<const uint8_t *>(boundary.data()), boundary.size()}, {reinterpret_cast<const uint8_t *>(mime.data()), mime.size()}, offset, length, SIZE_MAX, 0, separator};
                        char complete[4096];
                        size_t required = sw_snprintf(complete, sizeof(complete), "%s--%s\r\nContent-Type: %s\r\nContent-Range: bytes %zu-%zu/%zu\r\n\r\n", separator ? "\r\n" : "", boundary.c_str(), mime.c_str(), offset, offset + length - 1, SIZE_MAX);
                        size_t query = 0;
                        check(swr_v1_http_range_format(&input, nullptr, 0, &query) == 0 && query == required, "range format query");
                        for (size_t capacity : {size_t(1), size_t(2), size_t(32), size_t(511), size_t(512), required, required + 1, required + 2}) {
                            std::vector<unsigned char> old(capacity + 2, 0xa5), current = old;
                            size_t n = sw_snprintf(reinterpret_cast<char *>(old.data()), capacity, "%s--%s\r\nContent-Type: %s\r\nContent-Range: bytes %zu-%zu/%zu\r\n\r\n", separator ? "\r\n" : "", boundary.c_str(), mime.c_str(), offset, offset + length - 1, SIZE_MAX);
                            size_t actual = SIZE_MAX;
                            check(swr_v1_http_range_format(&input, current.data(), capacity, &actual) == 0 && actual == n && old == current, "range format capacity/prefix/guard");
                            ++formats;
                        }
                    }
                }
            }
        }
        std::cout << "{\"range_differential_cases\":" << cases << ",\"allocation_failure_cases\":" << faults << ",\"format_capacity_cases\":" << formats << ",\"errors\":0}\n";
    } catch (const std::exception &error) { std::cerr << error.what() << '\n'; return 1; }
}
