// Ordinary inert metadata only. No Coroutine, PHP, VM, context or callbacks.
#include "swoole_rs_coroutine_registry.h"
#include <cassert>
#include <climits>
#include <cstdio>
#include <functional>
#include <unordered_map>
#include <vector>

#ifdef SWR_REGISTRY_FFI_ARCHIVE
extern "C" uint32_t swr_v1_abi_version();
extern "C" uint64_t swr_v1_feature_bits();
#endif
struct Value { uintptr_t token; };
using Native = std::unordered_map<long, Value *>;
using Selected = swoole::RustCoroutineRegistry<Value>;
static size_t checks = 0, steps = 0, scenarios = 0;
static uint64_t checksum = 0;
static void compare(const Native &native, const Selected &selected) {
    assert(native.size() == selected.size()); ++checks;
    auto actual = selected.begin();
    for (const auto &entry : native) {
        assert(actual != selected.end());
        assert(actual->first == entry.first && actual->second == entry.second);
        assert(std::hash<long>{}(entry.first) == static_cast<size_t>(entry.first));
        auto found = selected.find(entry.first);
        assert(found != selected.end() && found->second == entry.second);
        checksum = checksum * 131 + static_cast<uint64_t>(entry.first);
        ++actual; checks += 4;
    }
    assert(actual == selected.end()); ++checks; ++steps;
}
static void scenario(const std::vector<long> &keys) {
    Native native;
    Selected selected;
    std::vector<Value> values(keys.size());
    assert(native.max_load_factor() == 1.0f); ++checks;
    for (size_t i=0; i<keys.size(); ++i) {
        values[i].token = i;
        native[keys[i]] = &values[i]; selected[keys[i]] = &values[i]; compare(native,selected);
        if (i % 7 == 0) {
            native[keys[i]] = nullptr; selected[keys[i]] = nullptr; compare(native,selected);
            native[keys[i]] = &values[i]; selected[keys[i]] = &values[i]; compare(native,selected);
        }
    }
    // Replacement must not change live order; erase must retain bucket count.
    for (size_t i=0; i<keys.size(); i+=3) {
        assert(native.erase(keys[i]) == selected.erase(keys[i])); ++checks; compare(native,selected);
    }
    for (size_t i=0; i<keys.size(); i+=3) {
        native[keys[i]] = &values[i]; selected[keys[i]] = &values[i]; compare(native,selected);
    }
    const size_t buckets = native.bucket_count();
    native.clear(); selected.clear(); compare(native,selected);
    assert(native.bucket_count() == buckets); ++checks;
    // A discarded proxy is still Native operator[]: publish null immediately.
    for (auto key : keys) {
        (void)native[key]; (void)selected[key]; compare(native,selected);
        Value *a=native[key], *b=selected[key]; assert(a==b && a==nullptr); ++checks;
    }
    native.clear(); selected.clear(); compare(native,selected);
    for (auto it=keys.rbegin(); it!=keys.rend(); ++it) {
        native[*it]=nullptr; selected[*it]=nullptr; compare(native,selected);
    }
    assert(native.erase(LONG_MIN+17) == selected.erase(LONG_MIN+17)); ++checks;
    compare(native,selected); ++scenarios;
}
int main() {
    uint32_t ffi_abi = 0;
    uint64_t ffi_features = 0;
#ifdef SWR_REGISTRY_FFI_ARCHIVE
    ffi_abi = swr_v1_abi_version();
    ffi_features = swr_v1_feature_bits();
    assert(ffi_abi == 1);
    assert((ffi_features & (uint64_t(1) << 15)) != 0);
#endif
    for (size_t size : {size_t(0),size_t(1),size_t(2),size_t(3),size_t(5),size_t(11),size_t(23),size_t(97),size_t(257),size_t(1024)}) {
        std::vector<long> keys;
        for(size_t i=0;i<size;++i)keys.push_back(static_cast<long>(i)); scenario(keys);
        for(auto &key:keys)key=-key-1; scenario(keys);
        for(size_t i=0;i<size;++i)keys[i]=static_cast<long>(i)*1155-577; scenario(keys);
    }
    scenario({LONG_MIN,LONG_MAX,0,-1,1,LONG_MIN+1,LONG_MAX-1,2,-2,97,-97});
    printf("{\"scenarios\":%zu,\"steps\":%zu,\"checks\":%zu,\"checksum\":%llu,\"libcpp\":%d,\"abi\":%d,\"long_bytes\":%zu,\"ffi_abi\":%u,\"ffi_features\":%llu}\n",scenarios,steps,checks,(unsigned long long)checksum,_LIBCPP_VERSION,_LIBCPP_ABI_VERSION,sizeof(long),ffi_abi,(unsigned long long)ffi_features);
}
