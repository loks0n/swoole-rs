#ifndef SWOOLE_RS_PHPHELPERS
#error "Benchmark selected branch requires SWOOLE_RS_PHPHELPERS"
#endif
// Optimized helper subset only; Zend execution/startup costs are outside scope.
#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <iostream>
#include <string>
#include <unordered_map>
#include <vector>
#include "swoole_rs_phphelpers.h"
struct zval { uint64_t first,second; };
namespace reference {
#include "aliases.inc"
#include "arguments.inc"
}
namespace selected {
#include "selected-arguments.inc"
}
struct Lookup { uint32_t family;std::string name; };
static std::vector<Lookup> names;
static const std::unordered_map<std::string,std::string> *families[]={&reference::array_methods,&reference::string_methods,&reference::stream_methods};
// Equally noinline wrappers preserve matched native string construction/copy.
__attribute__((noinline)) static std::string alias(bool rust,const Lookup &lookup) {
    const std::string name(lookup.name.data(),lookup.name.size());
    if(rust) {
        size_t length=0;const char *value=swr_v1_phphelpers_alias(lookup.family,reinterpret_cast<const uint8_t *>(name.data()),name.size(),&length);
        return value ? std::string(value,length) : std::string();
    }
    const auto found=families[lookup.family]->find(name);
    return found==families[lookup.family]->end() ? std::string() : found->second;
}
__attribute__((noinline)) static uint64_t aliases(bool rust,uint64_t seed) {
    uint64_t result=0;
    for(size_t i=0;i<names.size();++i) {
        const auto value=alias(rust,names[(i+seed%names.size())%names.size()]);
        for(unsigned char byte:value)result=result*33+byte;
    }
    return result;
}
__attribute__((noinline)) static uint64_t arguments(bool rust,uint64_t seed,int count,int position) {
    std::array<zval,64> source{},destination{};
    for(int i=0;i<count;++i)source[i]={seed+static_cast<uint64_t>(i),seed^static_cast<uint64_t>(i*7)};
    if(rust)selected::move_first_element(source.data(),destination.data(),count,position);
    else reference::move_first_element(source.data(),destination.data(),count,position);
    uint64_t result=0;
    for(int i=0;i<count;++i)result=result*33+destination[i].first+destination[i].second;
    return result;
}
static uint64_t run(bool rust,const std::string &name,uint64_t seed) {
    if(name=="aliases151")return aliases(rust,seed);
    if(name=="arguments1")return arguments(rust,seed,1,0);
    if(name=="arguments4")return arguments(rust,seed,4,1);
    if(name=="arguments16")return arguments(rust,seed,16,2);
    if(name=="arguments64")return arguments(rust,seed,64,32);
    throw std::runtime_error("unknown workload");
}
int main(int argc,char **argv) {
    for(uint32_t family=0;family<3;++family)for(const auto &item:*families[family])names.push_back({family,item.first});
    std::sort(names.begin(),names.end(),[](const Lookup &a,const Lookup &b){return a.family<b.family || (a.family==b.family && a.name<b.name);});
    if(names.size()!=151)return 1;
    if(argc==2 && std::string(argv[1])=="--check") {
        size_t checks=0;
        for(const char *name:{"aliases151","arguments1","arguments4","arguments16","arguments64"}) {
            for(uint64_t seed:{uint64_t(0),uint64_t(1),UINT64_MAX}) {
                if(run(false,name,seed)!=run(true,name,seed))return 1;
                ++checks;
            }
        }
        // No elapsed clock is read on this branch.
        std::cout<<"{\"passed\":true,\"workloads\":5,\"matched_checks\":"<<checks<<",\"elapsed_ns\":0}\n";return 0;
    }
    if(argc!=6 || std::string(argv[1])!="--measure" || std::string(argv[5]).empty() ||
       (std::string(argv[2])!="native" && std::string(argv[2])!="rust")) {
        std::cerr<<"Use --check, or --measure native|rust WORKLOAD ITERATIONS ACKNOWLEDGED_HOST_LEASE after actual host-wide exclusive acknowledgment.\n";return 2;
    }
    char *end=nullptr;const auto iterations=std::strtoull(argv[4],&end,10);
    if(!iterations || *end || iterations>1000000000ULL)return 2;
    const bool rust=std::string(argv[2])=="rust";const std::string workload=argv[3];
    run(rust,workload,0); // Validate before acquiring a clock.
    uint64_t checksum=0;const auto begin=std::chrono::steady_clock::now();
    for(uint64_t i=0;i<iterations;++i)checksum^=run(rust,workload,i);
    const auto elapsed=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-begin).count();
    std::cout<<"{\"engine\":\""<<argv[2]<<"\",\"workload\":\""<<workload<<"\",\"iterations\":"<<iterations<<",\"checksum\":"<<checksum<<",\"elapsed_ns\":"<<elapsed<<"}\n";
}
