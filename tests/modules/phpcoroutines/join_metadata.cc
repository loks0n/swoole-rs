#include "swoole_rs.h"
#include "swoole_rs_phpcoroutines.h"
#include <array>
#include <cassert>
#include <cstdio>
#include <exception>
#include <functional>
#include <memory>
#include <new>
#include <set>
#include <thread>
#include <utility>
#include <vector>
/* join_owner */

// Inert identity records, not PHPContext instances or Native callback payloads.
struct Identity { uintptr_t marker; };
int main() {
    assert(swr_v1_abi_version() == 1);
    assert((swr_v1_feature_bits() & UINT64_C(134217728)) != 0);
    std::array<Identity, 64> stack_records{};
    std::vector<std::unique_ptr<Identity>> heap_records;
    std::vector<Identity *> identities;
    for (size_t i = 0; i < stack_records.size(); ++i) {
        stack_records[i].marker = i;
        identities.push_back(&stack_records[i]);
        heap_records.emplace_back(new Identity{64 + i});
        identities.push_back(heap_records.back().get());
    }
    PHPCoroutineJoinMembership membership;
    PHPCoroutineJoinMetadata metadata;
    membership.bind(metadata);
    std::set<Identity *> native_set;
    std::shared_ptr<bool> native_canceled = std::make_shared<bool>(false);
    assert(metadata.empty());
    assert(metadata.erase_empty(0));
    for (size_t i = 0; i < identities.size(); ++i) {
        auto *identity = identities[(i * 17) % identities.size()];
        const uintptr_t token = reinterpret_cast<uintptr_t>(identity);
        assert(reinterpret_cast<Identity *>(token) == identity);
        native_set.insert(identity); metadata.insert(token);
        if (i % 7 == 0) { native_set.insert(identity); metadata.insert(token); }
    }
    auto check_order = [&]() {
        std::vector<uintptr_t> expected, actual;
        for (auto *identity : native_set) { expected.push_back(reinterpret_cast<uintptr_t>(identity)); }
        size_t cursor = 0; uintptr_t token = 0;
        while (metadata.next(&cursor, &token)) { actual.push_back(token); }
        assert(actual == expected); // original Native pointer order, not just membership
        const size_t saved_cursor = cursor; const uintptr_t saved_token = token;
        assert(!metadata.next(&cursor, &token));
        assert(cursor == saved_cursor && token == saved_token);
        assert(metadata.empty() == native_set.empty()); // iteration never erases
    };
    check_order();
    for (size_t i = 0; i < identities.size(); i += 2) {
        auto *identity = identities[i]; native_set.erase(identity);
        assert(metadata.erase_empty(reinterpret_cast<uintptr_t>(identity)) == native_set.empty());
    }
    check_order();
    assert(!metadata.erase_empty(0));
    // Native capture objects are copied/destroyed, never invoked. No deferred
    // callback, coroutine, context, destructor reentry or Zend effect executes.
    uintptr_t native_identity = 7;
    auto native_capture = [&native_set, native_canceled, native_identity]() { (void) native_set; (void) native_canceled; (void) native_identity; };
    auto selected_capture = [metadata, native_identity]() { (void) metadata; (void) native_identity; };
    {
        std::function<void()> native_function = native_capture;
        std::function<void()> selected_function = selected_capture;
        auto native_copy = native_function; auto selected_copy = selected_function;
        (void) native_copy; (void) selected_copy;
        PHPCoroutineJoinMetadata copy(metadata);
        PHPCoroutineJoinMetadata moved(std::move(copy));
        assert(moved.can_resume());
    }
    // Independent capture reference copies/drops are concurrent; token/flag
    // access is serial and remains on this thread as in the original contract.
    std::vector<std::thread> threads;
    for (unsigned i = 0; i < 8; ++i) {
        threads.emplace_back([copy = metadata]() {
            for (unsigned j = 0; j < 512; ++j) { PHPCoroutineJoinMetadata nested(copy); (void) nested; }
        });
    }
    for (auto &thread : threads) { thread.join(); }
    check_order();
    *native_canceled = true; metadata.cancel();
    assert(metadata.can_resume() == !*native_canceled);
    for (size_t i = 1; i < identities.size(); i += 2) {
        auto *identity = identities[i]; native_set.erase(identity);
        assert(metadata.erase_empty(reinterpret_cast<uintptr_t>(identity)) == native_set.empty());
    }
    check_order();
    for (size_t i = 0; i < stack_records.size(); ++i) {
        assert(stack_records[i].marker == i);
        assert(heap_records[i]->marker == 64 + i);
    }
    // Ordinary metadata scope only: the membership guard drops before the
    // surviving flag-only holder, without invoking a Native callback.
    std::unique_ptr<PHPCoroutineJoinMetadata> flag_holder;
    {
        PHPCoroutineJoinMembership scope;
        PHPCoroutineJoinMetadata inner;
        scope.bind(inner);
        inner.insert(19);
        flag_holder.reset(new PHPCoroutineJoinMetadata(inner));
        inner.cancel();
    }
    assert(!flag_holder->can_resume());
    std::printf("JOIN_METADATA_OK identities=%zu native_capture=%zu selected_capture=%zu threads=8 copies=4096 callbacks=0\n",
                identities.size(), sizeof(native_capture), sizeof(selected_capture));
}
