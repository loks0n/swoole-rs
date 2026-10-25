// Matched actual native runtime benchmark. --check performs correctness only;
// --measure is authorized solely inside an acknowledged exclusive host lease.
#include "swoole_coroutine.h"
#include "swoole_coroutine_channel.h"
#include <cassert>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>
using swoole::Coroutine;
using swoole::coroutine::Channel;

int main(int argc,char **argv) {
    if(argc!=4 || (std::strcmp(argv[1],"--check") && std::strcmp(argv[1],"--measure")))return 2;
    bool measure=!std::strcmp(argv[1],"--measure");
    std::string mode=argv[2];
    long count=std::strtol(argv[3],nullptr,10);
    if(count<1)return 2;
    swoole_init();
    long checksum=0;
    std::chrono::steady_clock::time_point start;
    if(measure)start=std::chrono::steady_clock::now();
    if(mode=="create") {
        for(long i=0;i<count;i++)Coroutine::create([&](void *){checksum++;});
    } else if(mode=="yield") {
        long cid=Coroutine::create([&](void *){for(long i=0;i<count;i++){checksum++;Coroutine::get_current()->yield();}});
        auto *co=Coroutine::get_by_cid(cid);
        for(long i=0;i<count;i++)co->resume();
    } else if(mode=="channel") {
        Coroutine::create([&](void *){Channel channel(8);long value=1;for(long i=0;i<count;i++){assert(channel.push(&value));auto *p=static_cast<long *>(channel.pop());assert(p==&value);checksum+=*p;}});
    } else if(mode=="cancel") {
        Coroutine::create([&](void *){for(long i=0;i<count;i++){long cid=Coroutine::create([&](void *){assert(!Coroutine::get_current()->yield_ex(-1));checksum++;});auto *co=Coroutine::get_by_cid(cid);assert(co->cancel());}});
    } else if(mode=="fanin") {
        Coroutine::create([&](void *){Channel channel(1);long value=1;Coroutine::create([&](void *){for(long i=0;i<count;i++)assert(channel.push(&value));});for(long i=0;i<count;i++){auto *p=static_cast<long *>(channel.pop());assert(p==&value);checksum+=*p;}});
    } else return 2;
    long long elapsed=measure?std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-start).count():0;
    assert(checksum==count);
    assert(Coroutine::count()==0);
    Coroutine::deactivate();
    swoole_clean();
    std::cout<<"{\"mode\":\""<<mode<<"\",\"count\":"<<count<<",\"checksum\":"<<checksum;
    if(measure)std::cout<<",\"nanoseconds\":"<<elapsed;
    std::cout<<"}\n";
}
