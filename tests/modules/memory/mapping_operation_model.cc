#include "mapping_operation_model.h"
#include "swoole_rs.h"
#include <cstdio>
namespace model {
std::vector<Event> events;
std::array<std::array<uint64_t,128>,2> storage;
std::array<size_t,2> lengths{};
std::array<bool,2> active{};
int file_descriptor=3;
void reset(){assert(!active[0]&&!active[1]);events.clear();events.reserve(16);for(auto &slot:storage)slot.fill(UINT64_C(0xa5a5a5a5a5a5a5a5));}
void *mmap(void *hint,size_t size,int protection,int flags,int descriptor,off_t offset){
    assert(!hint && offset==0 && protection==(PROT_READ|PROT_WRITE));
    assert(size<=storage[0].size()*sizeof(uint64_t));
    for(size_t i=0;i<active.size();++i)if(!active[i]){
        active[i]=true;lengths[i]=size;std::memset(storage[i].data(),0,size);
        events.push_back({3,size,flags,descriptor});return storage[i].data();
    }
    throw std::runtime_error("Normal model unexpectedly exhausted two backing slots");
}
int munmap(void *memory,size_t size){
    for(size_t i=0;i<active.size();++i)if(memory==storage[i].data()){
        assert(active[i]&&lengths[i]==size);events.push_back({4,size,0,0});active[i]=false;return 0;
    }
    throw std::runtime_error("Unexpected unmap token");
}
int mprotect(void *memory,size_t size,int flags){
    for(size_t i=0;i<active.size();++i)if(memory==storage[i].data()){
        assert(active[i]&&lengths[i]==size);events.push_back({5,size,flags,0});return 0;
    }
    throw std::runtime_error("Unexpected protection token");
}
}
int main(){
    assert(swr_v1_abi_version()==1 && (swr_v1_feature_bits()&64)==64);
    size_t cases=0;
    for(size_t requested:{8u,24u,63u,128u})for(size_t count:{1u,3u})for(int fd:{0,3}){
        model::reset();model::file_descriptor=fd;
        auto *payload=static_cast<uint8_t *>(count==1?model::sw_shm_malloc(requested):model::sw_shm_calloc(count,requested));
        const size_t bytes=(requested*count+7)/8*8;
        assert(payload==reinterpret_cast<uint8_t *>(model::storage[0].data())+8);
        assert(model::storage[0][0]==bytes+8);
        for(size_t i=0;i<bytes;++i){assert(payload[i]==0);payload[i]=static_cast<uint8_t>(i*37+11);}
        assert(model::sw_shm_protect(payload,PROT_READ|PROT_WRITE)==0);
        const size_t next_size=bytes+64;
        auto *next=static_cast<uint8_t *>(model::sw_shm_realloc(payload,next_size));
        assert(next==reinterpret_cast<uint8_t *>(model::storage[1].data())+8);
        for(size_t i=0;i<next_size;++i)assert(next[i]==(i<bytes?static_cast<uint8_t>(i*37+11):0));
        model::sw_shm_free(next);
        assert(!model::active[0]&&!model::active[1]);
        const auto &trace=model::events;
#ifdef MAP_ANONYMOUS
        assert(trace.size()==5);
        assert(trace[0].action==3&&trace[1].action==5&&trace[2].action==3&&trace[3].action==4&&trace[4].action==4);
        const size_t first_map=0,second_map=2;
        const int flags=MAP_SHARED|MAP_ANONYMOUS,descriptor=-1;
#else
        assert(trace.size()==9);
        assert(trace[0].action==1&&trace[1].action==3&&trace[2].action==2&&trace[3].action==5);
        assert(trace[4].action==1&&trace[5].action==3&&trace[6].action==2&&trace[7].action==4&&trace[8].action==4);
        assert(trace[0].descriptor==fd&&trace[2].descriptor==fd&&trace[4].descriptor==fd&&trace[6].descriptor==fd);
        const size_t first_map=1,second_map=5;
        const int flags=MAP_SHARED,descriptor=fd;
#endif
        assert(trace[first_map].size==bytes+8&&trace[second_map].size==next_size+8);
        assert(trace[first_map].flags==flags&&trace[second_map].flags==flags);
        assert(trace[first_map].descriptor==descriptor&&trace[second_map].descriptor==descriptor);
        assert(trace[trace.size()-2].size==bytes+8&&trace.back().size==next_size+8);
        for(const auto &slot:model::storage)assert(slot[127]==UINT64_C(0xa5a5a5a5a5a5a5a5));
        ++cases;
    }
    std::printf("{\"abi\":1,\"feature_bits\":%llu,\"actual_native_success_cases\":%zu,\"explicit_os_calls\":0,\"passed\":true}\n",static_cast<unsigned long long>(swr_v1_feature_bits()),cases);
}
