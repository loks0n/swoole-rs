#include <cassert>
#include <cstdint>
#include <cstdio>
#include <unordered_map>
#include <map>
#include <vector>
#include "swoole_rs_coroutine_registry.h"
#define SW_THREAD_LOCAL
#define sw_likely(x) (x)
namespace swoole {
class Coroutine {
public:
    long cid=0;
#ifdef SWOOLE_RS_COROUTINE_REGISTRY_V2
    static RustCoroutineRegistry<Coroutine> coroutines;
#else
    static std::unordered_map<long,Coroutine*> coroutines;
#endif
    long get_cid() const { return cid; }
};
#ifdef SWOOLE_RS_COROUTINE_REGISTRY_V2
RustCoroutineRegistry<Coroutine> Coroutine::coroutines;
#else
std::unordered_map<long,Coroutine*> Coroutine::coroutines;
#endif
}
#include "registry-callers.inc"
int main() {
    using C=swoole::Coroutine;
    std::vector<C> values(1024);
    std::map<long,C*> expected;
    uint64_t observations=0, sum=0, order=0;
    for(long i=0;i<1024;i++) values[i].cid=i+1;
    uint64_t random=391;
    for(size_t round=0;round<20000;round++) {
        random=random*6364136223846793005ULL+1442695040888963407ULL;
        long id=long((random>>32)%1024)+1;
        if((random&7)<5) { C::coroutines[id]=&values[id-1];expected[id]=&values[id-1]; }
        else { assert(C::coroutines.erase(id)==expected.erase(id)); }
        assert(swoole_coroutine_count()==expected.size());++observations;
        C *want=expected.count(id)?expected[id]:nullptr;
        assert(swoole_coroutine_get(id)==want);++observations;
        assert(swoole_coroutine_get(2049)==nullptr);++observations;
        sum+=uint64_t(swoole_coroutine_count())+uint64_t(want?want->cid:0);
        if(round%97==0) {
            std::map<long,C*> seen;
            swoole_coroutine_iterator_reset();
            while(C *value=swoole_coroutine_iterator_each()) { assert(seen.emplace(value->cid,value).second); }
            assert(seen==expected);++observations;
            assert(swoole_coroutine_iterator_each()==nullptr);++observations;
            seen.clear();
            for(auto &entry:C::coroutines) assert(seen.emplace(entry.first,entry.second).second);
            assert(seen==expected);++observations;
        }
    }
    if(!expected.empty()) {
        auto held=C::coroutines.begin();long id=held->first;C *before=held->second;
        C::coroutines[id]=nullptr;assert(held->second==nullptr);++observations;
        C::coroutines[id]=before;assert(held->second==before);++observations;
    }
    // Preserve actual traversal identities independently: unordered membership
    // equality does NOT establish identical externally observable PHP order.
    swoole_coroutine_iterator_reset();
    while(C *value=swoole_coroutine_iterator_each()) order=order*131+uint64_t(value->cid);
    for(auto &entry:expected) assert(C::coroutines.erase(entry.first)==1);
    assert(swoole_coroutine_count()==0);++observations;
    swoole_coroutine_iterator_reset();assert(swoole_coroutine_iterator_each()==nullptr);++observations;
    printf("{\"observations\":%llu,\"checksum\":%llu,\"iteration_checksum\":%llu}\n",(unsigned long long)observations,(unsigned long long)sum,(unsigned long long)order);
}
