#include "inline_oracle.h"
#include "allocation_oracle.h"
#include <iostream>
void check(bool yes, const char *message) { if (!yes) throw std::runtime_error(message); }
int main() {
    unsigned cases = 0, faults = 0, paths = 0;
    try {
        for (size_t boundary_length : {size_t(0),size_t(1),size_t(14),size_t(23),size_t(24),size_t(40),size_t(1024)}) {
            for (size_t count : {size_t(0),size_t(1),size_t(2),size_t(5)}) for (bool binary : {false,true}) for (bool rng_throws : {false,true}) {
                size_t total = 0;
                for (size_t nth = 0; nth <= total; ++nth) {
                    original_inline::Server old_server; candidate_inline::Server new_server;
                    original_inline::StaticHandler old(&old_server); candidate_inline::StaticHandler current(&new_server);
                    old.boundary = current.boundary = std::string(boundary_length,'b');
                    if (binary && boundary_length) old.boundary[boundary_length/2] = current.boundary[boundary_length/2] = 0;
                    old.content_type = current.content_type = "previous content type that owns allocated storage";
                    old.tasks.resize(count); current.tasks.resize(count);
                    original_inline::random_calls = candidate_inline::random_calls = 0;
                    original_inline::random_length = candidate_inline::random_length = 999;
                    original_inline::random_throws = candidate_inline::random_throws = rng_throws;
                    unsigned old_failed = 0, new_failed = 0;
                    const std::string *old_ref = nullptr, *new_ref = nullptr;
                    size_t old_count = 0, sizes[128] = {};
                    allocation::begin(nth);
                    try { old_ref = &old.get_content_type(); } catch (const std::bad_alloc &) { old_failed = 1; } catch (const std::runtime_error &) { old_failed = 2; }
                    allocation::end(); old_count = allocation::count;
                    check(old_count <= 128, "allocation trace overflow"); std::copy(allocation::sizes,allocation::sizes+old_count,sizes);
                    allocation::begin(nth);
                    try { new_ref = &current.get_content_type(); } catch (const std::bad_alloc &) { new_failed = 1; } catch (const std::runtime_error &) { new_failed = 2; }
                    allocation::end();
                    check(old_failed == new_failed && old_count == allocation::count && std::equal(sizes,sizes+old_count,allocation::sizes), "inline allocation/failure sequence");
                    check(old.boundary == current.boundary && old.content_type == current.content_type && original_inline::random_calls == candidate_inline::random_calls && original_inline::random_length == candidate_inline::random_length, "inline partial publication/random call");
                    if (!old_failed) {
                        check(old_ref && new_ref && *old_ref == *new_ref, "inline content bytes");
                        check((old_ref == &old.mime) == (new_ref == &current.mime) && (new_ref == &current.mime) == (count <= 1), "MIME reference identity");
                        if (!rng_throws) {
                            const auto *before = &current.get_boundary();
                            check(before == &current.boundary && before == &current.get_boundary() && old.get_boundary() == *before, "boundary reference identity/cache");
                        }
                    }
                    if (!nth) { total = old_count; ++cases; } else ++faults;
                }
            }
        }
        const std::vector<std::string> roots = {"", "/", "/root", "/root/", std::string("/r\0oot",6), std::string(100,'r')};
        std::vector<std::string> names = {"", ".", "..", "/root", "/root/a", "/root/../a", "a..b", std::string("a\0..b",5), std::string("/r\0oot/a",8)};
        uint32_t seed = 32;
        for (unsigned n=0;n<4096;++n) { std::string name; for (unsigned j=0;j<n%48;++j) { seed=seed*1664525+1013904223; name.push_back("./root\0"[seed%7]); } names.push_back(name); }
        for (const auto &root : roots) for (const auto &name : names) for (bool last : {false,true}) {
            original_inline::Server a; candidate_inline::Server b; a.root = b.root = root;
            original_inline::StaticHandler old(&a); candidate_inline::StaticHandler current(&b);
            std::memcpy(old.filename,name.data(),name.size()); std::memcpy(current.filename,name.data(),name.size());
            old.l_filename = current.l_filename = name.size(); old.last = current.last = last;
            check(old.is_absolute_path() == current.is_absolute_path() && old.is_located_in_document_root() == current.is_located_in_document_root(), "inline path predicate");
            check(old.catch_error() == current.catch_error() && old.status_code == current.status_code, "inline error publication"); ++paths;
        }
        std::cout << "{\"inline_cases\":" << cases << ",\"allocation_failures\":" << faults << ",\"path_error_cases\":" << paths << ",\"errors\":0}\n";
    } catch (const std::exception &e) { allocation::end(); std::cerr << e.what() << '\n'; return 1; }
}
