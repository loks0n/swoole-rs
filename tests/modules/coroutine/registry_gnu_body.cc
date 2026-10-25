// Captured GNU policy bodies in inert helpers, compared with the actual Rust
// registry functions with a captured-source GNU policy capsule on Mac.
// Not installed GNU/Linux, allocator, Coroutine, PHP or lifetime qualification.
#include "swoole_rs_coroutine_registry.h"
#include "actual-gnu.inc"
#include <cassert>
#include <climits>
#include <cstdio>
#include <vector>
struct Value { uintptr_t token; };
// Source-only GNU consumer uses real exports. The actual Native facade keeps
// its compiler-derived Apple capsule and refuses unknown/Linux ON unchanged.
class Selected {
    void *owner=nullptr;
    static constexpr swr_v1_coroutine_registry_policy candidate() { return {2,120200,1}; }
  public:
    using iterator=swoole::RustCoroutineRegistry<Value>::iterator;
    class slot {
        Selected &registry; long cid;
      public:
        slot(Selected &value,long key):registry(value),cid(key) {
            if(!swr_v1_coroutine_registry_find(registry.owner,cid))
                assert(swr_v1_coroutine_registry_selected_insert(&registry.owner,cid,0,candidate())==0);
        }
        slot &operator=(Value *value) {
            assert(swr_v1_coroutine_registry_selected_insert(&registry.owner,cid,reinterpret_cast<uintptr_t>(value),candidate())==0); return *this;
        }
        operator Value *() const {
            return reinterpret_cast<Value *>(swr_v1_coroutine_registry_lookup(registry.owner,cid));
        }
    };
    ~Selected(){ swr_v1_coroutine_registry_drop(&owner); }
    slot operator[](long cid){ return slot(*this,cid); }
    iterator begin() const {return iterator(swr_v1_coroutine_registry_first(owner));}
    iterator end() const {return iterator();}
    iterator find(long cid)const{return iterator(swr_v1_coroutine_registry_find(owner,cid));}
    size_t size()const{return swr_v1_coroutine_registry_count(owner);}
    size_t erase(long cid){return swr_v1_coroutine_registry_erase(owner,cid);}
    void clear(){swr_v1_coroutine_registry_clear(owner);}
};
static size_t scenarios=0, steps=0, checks=0;
static uint64_t checksum=0;
static void compare(const GnuSource<long> &source, const Selected &selected) {
    assert(source.size()==selected.size()); ++checks;
    auto actual=selected.begin();
    for(const auto &value:source.values()) {
        assert(actual!=selected.end());
        assert(actual->first==value.first);
        assert(reinterpret_cast<uintptr_t>(actual->second)==value.second);
        auto found=selected.find(value.first);
        assert(found!=selected.end() && reinterpret_cast<uintptr_t>(found->second)==value.second);
        checksum=checksum*131+static_cast<uint64_t>(value.first);
        ++actual; checks+=4;
    }
    assert(actual==selected.end()); ++checks; ++steps;
}
static void scenario(const std::vector<long> &keys) {
    GnuSource<long> source;
    Selected selected;
    std::vector<Value> values(keys.size());
    for(size_t i=0;i<keys.size();++i) {
        values[i].token=i;
        source.put(keys[i],reinterpret_cast<uintptr_t>(&values[i])); selected[keys[i]]=&values[i]; compare(source,selected);
        if(i%7==0) {
            source.put(keys[i],0); selected[keys[i]]=nullptr; compare(source,selected);
            source.put(keys[i],reinterpret_cast<uintptr_t>(&values[i])); selected[keys[i]]=&values[i]; compare(source,selected);
        }
    }
    for(size_t i=0;i<keys.size();i+=3) {
        const size_t before=source.size(); source.erase(keys[i]);
        assert(before-source.size()==selected.erase(keys[i])); ++checks; compare(source,selected);
    }
    for(size_t i=0;i<keys.size();i+=3) {
        source.put(keys[i],reinterpret_cast<uintptr_t>(&values[i])); selected[keys[i]]=&values[i]; compare(source,selected);
    }
    const size_t buckets=source.buckets(), threshold=source.threshold();
    source.clear(); selected.clear(); compare(source,selected);
    assert(source.buckets()==buckets && source.threshold()==threshold); ++checks;
    for(auto key:keys) {
        assert(source.get(key)==0); (void)selected[key]; compare(source,selected);
        Value *actual=selected[key]; assert(actual==nullptr); ++checks;
    }
    source.clear(); selected.clear(); compare(source,selected);
    for(auto it=keys.rbegin();it!=keys.rend();++it) {
        source.put(*it,0); selected[*it]=nullptr; compare(source,selected);
    }
    const size_t before=source.size(); source.erase(LONG_MIN+17);
    assert(before-source.size()==selected.erase(LONG_MIN+17)); ++checks;
    compare(source,selected); ++scenarios;
}
int main() {
    // Arithmetic-only actual source bodies; no giant bucket allocation.
    GnuSourcePrime initial, big, saturated;
    assert(initial._M_next_bkt(0)==1 && initial.next_resize()==0); ++checks;
    assert(big._M_next_bkt(9223372036854775783ULL)==9223372036854775783ULL); ++checks;
    assert(big.next_resize()==9223372036854775808ULL); ++checks;
    assert(saturated._M_next_bkt(SIZE_MAX)==18446744073709551557ULL); ++checks;
    assert(saturated.next_resize()==SIZE_MAX); ++checks;
    for(size_t n:{size_t(0),size_t(1),size_t(2),size_t(3),size_t(5),size_t(11),size_t(23),size_t(97),size_t(257),size_t(1024)}) {
        std::vector<long> keys;
        for(size_t i=0;i<n;++i)keys.push_back(static_cast<long>(i)); scenario(keys);
        for(auto &key:keys)key=-key-1; scenario(keys);
        for(size_t i=0;i<n;++i)keys[i]=static_cast<long>(i)*1155-577; scenario(keys);
    }
    scenario({LONG_MIN,LONG_MAX,0,-1,1,LONG_MIN+1,LONG_MAX-1,2,-2,97,-97});
    printf("{\"scenarios\":%zu,\"steps\":%zu,\"checks\":%zu,\"checksum\":%llu}\n",scenarios,steps,checks,(unsigned long long)checksum);
}
