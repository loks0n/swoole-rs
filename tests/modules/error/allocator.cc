// SPDX-License-Identifier: Apache-2.0
#include "swoole.h"
#include <cstdlib>
#include <iostream>
#include <new>
char sw_error[1024] = {};
extern "C" void swr_test_fail_allocation(size_t);
extern "C" size_t swr_test_allocation_countdown();
static void require(bool value) { if (!value) std::abort(); }
static void fail_insert(int code, size_t allocation) {
    swr_test_fail_allocation(allocation);
    try { swoole_ignore_error(code); std::abort(); }
    catch (const std::bad_alloc &) {}
    require(swr_test_allocation_countdown() == 0);
    require(!swoole_is_ignored_error(code));
}
int main() {
    // The actual native facade catches neither exception: it raises bad_alloc
    // only after the unchanged Rust implementation returns its NOMEM status.
    fail_insert(1, 1); // Bucket allocation.
    fail_insert(1, 2); // Opaque handle after a successful bucket allocation.
    swoole_ignore_error(1);
    require(swoole_is_ignored_error(1));
    swr_test_fail_allocation(1);
    swoole_ignore_error(1); // Duplicate must not consume an allocation failure.
    require(swr_test_allocation_countdown() == 1);
    int failed = 0;
    for (int code = 2; code < 100; ++code) {
        try { swoole_ignore_error(code); }
        catch (const std::bad_alloc &) { failed = code; break; }
    }
    require(failed > 1 && swr_test_allocation_countdown() == 0);
    require(!swoole_is_ignored_error(failed));
    for (int code = 1; code < failed; ++code) require(swoole_is_ignored_error(code));
    swoole_ignore_error(failed);
    require(swoole_is_ignored_error(failed));
    std::cout << "{\"bucket_failure\":true,\"handle_failure\":true,\"duplicate_no_allocation\":true,"
                 "\"growth_failure_atomic\":true,\"successful_retry\":true,\"native_bad_alloc\":true}\n";
}
