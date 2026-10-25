// Scratch benchmark: exact native bodies from native.py, modeled native storage.
#include <chrono>
#include <iostream>
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wreturn-type"
#define main protocols_correctness_main
#include "native.cc"
#undef main
#pragma GCC diagnostic pop
volatile uint64_t observed = 0;
struct PoolPlan { uint64_t entries; size_t iterations; std::array<uint64_t,512> ids; };
template<class Bus, class Buffer, class String>
uint64_t pool_work(size_t iterations, const PoolPlan &plan) {
    uint64_t result = 0;
    for (size_t cycle=0; cycle<iterations; ++cycle) {
        Bus bus; Buffer buffer{}; bus.buffer_=&buffer;
        buffer.info.flags=SW_EVENT_DATA_BEGIN;buffer.info.len=64;
        for(uint64_t id=0;id<plan.entries;++id) {buffer.info.msg_id=id;assert(bus.get_packet_buffer());}
        buffer.info.flags=0;
        for(uint64_t id:plan.ids) {buffer.info.msg_id=id;result+=bus.get_packet_buffer()->size;}
        Bus copy(bus);
        for(uint64_t id=0;id<plan.entries;id+=2)bus.packet_pool_.erase(id);
        result+=bus.get_memory_size()+copy.get_memory_size();
    }
    assert(String::live==0);
    return result;
}
uint64_t parse_work(bool candidate_engine,const std::string &wire,size_t iterations) {
    uint64_t result=0;
    for(size_t i=0;i<iterations;++i){
        const auto value=candidate_engine?candidate::redis::parse(wire.data(),wire.size()):reference::redis::parse(wire.data(),wire.size());
        result+=value.size()+value.back().size();
    }
    return result;
}
int main(int argc,char **argv) {
    const bool timed=argc==2 && std::string(argv[1])=="--time";
    struct Work {std::string name,wire;size_t iterations;};
    std::vector<Work> workloads;
    for(size_t size:{size_t(3),size_t(4096),size_t(65536),size_t(1048576)}) {
        workloads.push_back({"resp-"+std::to_string(size),"*2\r\n$3\r\nGET\r\n$"+std::to_string(size)+"\r\n"+std::string(size,'x')+"\r\n",size==3?2000000UL:size==4096?400000UL:size==65536?40000UL:2560UL});
    }
    for(const auto &work:workloads) {
        auto a=reference::redis::parse(work.wire.data(),work.wire.size());
        auto b=candidate::redis::parse(work.wire.data(),work.wire.size());
        assert(a==b && a.size()==2 && a.back().size()+2==parse_work(false,work.wire,1));
    }
    std::vector<PoolPlan> pools;
    for (uint64_t entries : {1u,16u,64u,1024u}) {
        PoolPlan plan{entries, entries==1024?1000UL:20000UL, {}};
        for(size_t i=0;i<plan.ids.size();++i) plan.ids[i]=(i*37)%entries;
        pools.push_back(plan);
        const auto pool_a=pool_work<reference::MessageBus,reference::PipeBuffer,reference::String>(1,plan);
        const auto pool_b=pool_work<candidate::MessageBus,candidate::PipeBuffer,candidate::String>(1,plan);
        assert(pool_a==pool_b);
    }
    if(!timed){std::cout<<"verified "<<workloads.size()<<" parse workloads and packet-index workload\n";return 0;}
    auto measure=[&](int trial,const std::string &name,int engine,size_t iterations,auto operation){
        const auto start=std::chrono::steady_clock::now();
        const auto checksum=operation();
        const auto stop=std::chrono::steady_clock::now();
        observed=checksum;
        const auto ns=std::chrono::duration_cast<std::chrono::nanoseconds>(stop-start).count();
        std::cout<<trial<<","<<name<<","<<engine<<","<<iterations<<","<<ns<<","<<checksum<<"\n";
    };
    for(int trial=0;trial<7;++trial){
        for(const auto &work:workloads) for(int pair=0;pair<2;++pair){const int engine=(trial+pair)%2;
            measure(trial,work.name,engine,work.iterations,[&]{return parse_work(engine,work.wire,work.iterations);});}
        for(const auto &plan:pools) for(int pair=0;pair<2;++pair){const int engine=(trial+pair)%2;
            measure(trial,"pool"+std::to_string(plan.entries)+"-lookup512-copy-erase",engine,plan.iterations,[&]{return engine?
                pool_work<candidate::MessageBus,candidate::PipeBuffer,candidate::String>(plan.iterations,plan):
                pool_work<reference::MessageBus,reference::PipeBuffer,reference::String>(plan.iterations,plan);});}
    }
}
