// Normal initialized success model only; wrapper allocation/free effects use
// static backing. No Swoole allocator, shared mapping, IPC or failure is run.
#include "swoole_rs_memory.h"
#include "swoole_rs.h"
#include <array>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <new>
#include <stdexcept>
#include <type_traits>

namespace fixture {
alignas(16) std::array<unsigned char,32768> storage;
size_t allocations=0,releases=0,requested=0;
bool use_shared=false;
void *allocate(size_t size,bool shared){
    assert(size+16<storage.size()&&shared==use_shared);
    ++allocations;requested=size;return storage.data();
}
void release(void *ptr,bool shared){assert(ptr==storage.data()&&shared==use_shared);++releases;}
struct Exception:std::runtime_error{explicit Exception(int):std::runtime_error("Unexpected normal model exception") {}};
constexpr int SW_ERROR_INVALID_PARAMS=1,SW_ERROR_MALLOC_FAIL=2;
void swoole_set_last_error(int){throw std::runtime_error("Unexpected normal model exhaustion");}
}
// These are fixture-owned Swoole effect names, not libc interposition.
void *sw_malloc(size_t n){return fixture::allocate(n,false);}
void *sw_shm_malloc(size_t n){return fixture::allocate(n,true);}
void sw_free(void *p){fixture::release(p,false);}
void sw_shm_free(void *p){fixture::release(p,true);}
#include "fixed_native_construction_selected.inc"

static void check_padding(uint32_t count,uint32_t width){
    const auto *base=fixture::storage.data();
    for(size_t i=offsetof(swr_v1_memory_fixed,allocated)+1;i<sizeof(swr_v1_memory_fixed);++i)assert(base[i]==0);
    for(size_t i=0;i<count;++i){
        const auto *node=base+48+i*(24+width);
        for(size_t j=1;j<offsetof(swr_v1_memory_fixed_slice,next);++j)assert(node[j]==0);
    }
}
static void check_pool(fixture::FixedPool &pool,uint32_t count,uint32_t width){
    check_padding(count,width);
    assert(pool.get_number_of_total_slice()==count&&pool.get_number_of_spare_slice()==count);
    assert(pool.get_slice_size()==width);
    assert(pool.sizeof_struct_impl()==48&&pool.sizeof_struct_slice()==24);
    auto *first=static_cast<unsigned char *>(pool.alloc(width));
    auto *second=static_cast<unsigned char *>(pool.alloc(width));
    assert(first==fixture::storage.data()+48+(count-1)*(24+width)+24);
    assert(second==fixture::storage.data()+48+(count-2)*(24+width)+24);
    assert(pool.get_number_of_spare_slice()==count-2);
    check_padding(count,width);
    if(width){first[0]=0x37;second[width-1]=0x59;assert(first[0]==0x37&&second[width-1]==0x59);}
    pool.free(second);pool.free(first);
    assert(pool.get_number_of_spare_slice()==count);
    check_padding(count,width);
}
int main(){
    assert(swr_v1_abi_version()==1&&(swr_v1_feature_bits()&64)==64);
    static_assert(std::is_trivially_default_constructible<fixture::FixedPoolImpl>::value,"explicit trivial native lifetime");
    static_assert(std::is_trivially_destructible<fixture::FixedPoolImpl>::value,"no missing resource destructor");
    size_t owned=0,borrowed=0;
    for(uint32_t count:{2u,3u,9u})for(uint32_t width:{1u,8u,17u,64u})for(bool shared:{false,true}){
        fixture::storage.fill(0xa5);fixture::use_shared=shared;fixture::allocations=fixture::releases=0;
        {
            fixture::FixedPool pool(count,width,shared);
            uint32_t aligned=(width+7)&~7u;
            check_pool(pool,count,aligned);
            assert(fixture::allocations==1&&fixture::releases==0);
            assert(fixture::requested==48+count*(24+aligned));
        }
        assert(fixture::releases==1);
        for(size_t i=fixture::requested;i<fixture::storage.size();++i)assert(fixture::storage[i]==0xa5);
        ++owned;
    }
    for(uint32_t count:{2u,4u,9u})for(uint32_t width:{1u,3u,8u,17u,64u})for(bool shared:{false,true})for(size_t tail:{0u,3u}){
        fixture::storage.fill(0xa5);fixture::use_shared=shared;fixture::allocations=fixture::releases=0;
        const size_t length=48+count*(24+width)+tail;
        {
            fixture::FixedPool pool(width,fixture::storage.data(),length,shared);
            check_pool(pool,count,width);
            assert(fixture::allocations==0&&fixture::releases==0);
        }
        assert(fixture::allocations==0&&fixture::releases==0);
        for(size_t i=length;i<fixture::storage.size();++i)assert(fixture::storage[i]==0xa5);
        ++borrowed;
    }
    std::printf("{\"passed\":true,\"abi\":1,\"owned_cases\":%zu,\"borrowed_cases\":%zu,\"explicit_os_calls\":0}\n",owned,borrowed);
}
