// Ordinary opaque metadata only. No PHP/Coroutine objects, resume, yield or cancellation.
#include <cassert>
#include <cstdint>
#include <iostream>
#include <limits>
#include <thread>
#include <unordered_map>
#include "swoole_rs_phpcoroutines.h"
#ifndef SWR_REGISTRY_GLOBAL
#define SWR_REGISTRY_GLOBAL 0
#endif
#ifndef SWOOLE_RS_PHPCOROUTINES
#if SWR_REGISTRY_GLOBAL
static std::unordered_map<long, uintptr_t> user_yield_coros;
#else
static thread_local std::unordered_map<long, uintptr_t> user_yield_coros;
#endif
void put(int64_t cid, uintptr_t token) { user_yield_coros[cid] = token; }
bool take(int64_t cid, uintptr_t *token) {
    auto it = user_yield_coros.find(cid);
    if (it == user_yield_coros.end()) return false;
    *token = it->second;
    user_yield_coros.erase(cid);
    return true;
}
void erase(int64_t cid) { user_yield_coros.erase(cid); }
#else
struct RegistryOwner {
    swr_phpcoroutines_yield_registry *handle = nullptr;
    RegistryOwner() = default;
    ~RegistryOwner() { if (handle) swr_v1_phpcoroutines_yield_registry_drop(handle); }
    RegistryOwner(const RegistryOwner &) = delete;
    RegistryOwner &operator=(const RegistryOwner &) = delete;
};
#if SWR_REGISTRY_GLOBAL
static RegistryOwner registry;
#else
static thread_local RegistryOwner registry;
#endif
void put(int64_t cid, uintptr_t token) { assert(swr_v1_phpcoroutines_yield_registry_try_put(&registry.handle, cid, token)); }
bool take(int64_t cid, uintptr_t *token) { return swr_v1_phpcoroutines_yield_registry_take(registry.handle, cid, token); }
void erase(int64_t cid) { swr_v1_phpcoroutines_yield_registry_erase(registry.handle, cid); }
#endif
int main() {
    for (int64_t i = -2048; i < 2048; ++i) put(i, uintptr_t(i + 2049));
    uintptr_t token = 99999;
    for (int64_t i = -2048; i < 2048; ++i) {
        assert(take(i, &token) && token == uintptr_t(i + 2049));
        assert(!take(i, &token) && token == uintptr_t(i + 2049));
    }
    put(42, 111);
    put(42, 0);
    assert(take(42, &token) && token == 0);
    put(42, 222);
    std::thread worker([] {
        uintptr_t local = 99999;
#if SWR_REGISTRY_GLOBAL
        assert(take(42, &local) && local == 222);
#else
        assert(!take(42, &local) && local == 99999);
#endif
        put(42, 333);
        assert(take(42, &local) && local == 333);
        put(42, 444);
        erase(42);
        assert(!take(42, &local));
#if SWR_REGISTRY_GLOBAL
        put(42, 555);
#endif
    });
    worker.join();
    assert(take(42, &token) && token == (SWR_REGISTRY_GLOBAL ? 555 : 222));
    put(std::numeric_limits<int64_t>::min(), 12);
    put(std::numeric_limits<int64_t>::max(), 13);
    assert(take(std::numeric_limits<int64_t>::min(), &token) && token == 12);
    assert(take(std::numeric_limits<int64_t>::max(), &token) && token == 13);
    std::cout << "4096 opaque records; duplicate/zero/extreme keys; native profile custody\n";
}
