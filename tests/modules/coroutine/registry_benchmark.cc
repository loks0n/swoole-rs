// Ordinary metadata only: no real Coroutine construction or runtime.
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <unordered_map>
#include <vector>
#include "swoole_rs_coroutine_registry.h"
#define SW_THREAD_LOCAL
#define sw_likely(x) (x)
namespace swoole {
class Coroutine {
public:
    long cid = 0;
#ifdef SWOOLE_RS_COROUTINE_REGISTRY_V2
    static RustCoroutineRegistry<Coroutine> coroutines;
#else
    static std::unordered_map<long, Coroutine *> coroutines;
#endif
    long get_cid() const { return cid; }
};
#ifdef SWOOLE_RS_COROUTINE_REGISTRY_V2
RustCoroutineRegistry<Coroutine> Coroutine::coroutines;
#else
std::unordered_map<long, Coroutine *> Coroutine::coroutines;
#endif
}
#include "registry-callers.inc"
extern "C" uint32_t swr_v1_abi_version();
extern "C" uint64_t swr_v1_feature_bits();
static volatile uint64_t sink;
int main(int argc, char **argv) {
    const bool measure = argc == 4 && std::strcmp(argv[1], "--measure") == 0 && argv[3][0];
    if (!(argc == 2 && std::strcmp(argv[1], "--check") == 0) && !measure) return 2;
    // --measure WORKLOAD LEASE_ID is for a future acknowledged exclusive window.
#ifdef SWOOLE_RS_COROUTINE_REGISTRY_V2
    assert(swr_v1_abi_version() == 1);
    assert((swr_v1_feature_bits() & (uint64_t(1) << 15)) != 0);
#endif
    using C = swoole::Coroutine;
    const char *names[] = {"insert-clear", "replace", "lookup", "erase-reinsert", "live-range", "gdb-traversal"};
    std::vector<C> values(512);
    for (size_t i = 0; i < values.size(); ++i) values[i].cid = long(i + 1);
    bool found = false;
    for (const char *name : names) {
        if (measure && std::strcmp(name, argv[2]) != 0) continue;
        found = true;
        C::coroutines.clear();
        for (auto &v : values) C::coroutines[v.cid] = &v;
        auto operation = [&]() {
            uint64_t checksum = 0;
            if (std::strcmp(name, "insert-clear") == 0) {
                C::coroutines.clear();
                for (auto &v : values) C::coroutines[v.cid] = &v;
                checksum = swoole_coroutine_count();
            } else if (std::strcmp(name, "replace") == 0) {
                for (auto &v : values) C::coroutines[v.cid] = &v;
                checksum = swoole_coroutine_count();
            } else if (std::strcmp(name, "lookup") == 0) {
                for (auto &v : values) {
                    C *actual = swoole_coroutine_get(v.cid);
                    assert(actual == &v);
                    checksum += uint64_t(actual->cid);
                    assert(swoole_coroutine_get(v.cid + 512) == nullptr);
                }
            } else if (std::strcmp(name, "erase-reinsert") == 0) {
                for (auto &v : values) {
                    assert(C::coroutines.erase(v.cid) == 1);
                    C::coroutines[v.cid] = &v;
                }
                checksum = swoole_coroutine_count();
            } else if (std::strcmp(name, "live-range") == 0) {
                for (auto &entry : C::coroutines) checksum = checksum * 131 + uint64_t(entry.second->cid);
            } else {
                swoole_coroutine_iterator_reset();
                while (C *v = swoole_coroutine_iterator_each()) checksum = checksum * 131 + uint64_t(v->cid);
                assert(swoole_coroutine_iterator_each() == nullptr);
            }
            assert(swoole_coroutine_count() == values.size());
            sink = checksum;
            return checksum;
        };
        uint64_t checksum = operation();
        if (!measure) {
            printf("{\"workload\":\"%s\",\"checksum\":%llu,\"members\":%zu}\n", name, (unsigned long long)checksum, swoole_coroutine_count());
        } else {
            // Clock reads occur only in this explicit measurement branch.
            auto begin = std::chrono::steady_clock::now();
            for (size_t n = 0; n < 4096; ++n) checksum = operation();
            auto elapsed = std::chrono::steady_clock::now() - begin;
            printf("{\"workload\":\"%s\",\"iterations\":4096,\"nanoseconds\":%lld,\"checksum\":%llu}\n", name,
                   (long long)std::chrono::duration_cast<std::chrono::nanoseconds>(elapsed).count(), (unsigned long long)checksum);
        }
    }
    return found ? 0 : 2;
}
