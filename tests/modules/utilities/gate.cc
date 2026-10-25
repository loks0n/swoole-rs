#include <algorithm>
#include <cstdarg>
#include <cstdio>
#include <cerrno>
#include <cassert>
#include <climits>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <random>
#include <string>
#include <thread>
#include <vector>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>
#include "swoole_rs_utilities.h"
namespace reference {
using ulong_t = unsigned long;
#include "oracle.inc"
}
int main() {
    std::mt19937 random(982341);
    size_t hashes=0, pretty=0, logging=0, lines=0;
    std::vector<int> levels={INT_MIN,INT_MAX,-1,0,1,2,3,4,5,6,7};
    for(int i=0;i<20000;i++) levels.push_back(static_cast<int>(random()));
    for(int value:levels) {
        assert(swr_v1_utils_log_level(value)==reference::log_level(value));
        assert(std::strcmp(swr_v1_utils_log_label(value),reference::log_label(value))==0);
        assert(std::strcmp(swr_v1_utils_log_rotation(value),reference::log_rotation(value))==0);
        logging+=3;
    }
    for (size_t size=0;size<1024;size++) {
        std::string bytes(size,'x');
        for (auto &byte:bytes) byte=static_cast<char>(random());
        const auto *data=reinterpret_cast<const uint8_t*>(bytes.data());
        assert(swr_v1_utils_hash(data,size,0,CHAR_MIN<0)==reference::swoole_hash_php(bytes.data(),size));hashes++;
        assert(swr_v1_utils_hash(data,size,1,CHAR_MIN<0)==reference::swoole_hash_jenkins(bytes.data(),size));hashes++;
        for(auto &byte:bytes)byte&=127;
        assert(swr_v1_utils_hash(data,size,2,CHAR_MIN<0)==reference::swoole_hash_austin(bytes.data(),size));hashes++;
    }
    std::vector<std::string> names={"void ns::Class::method(int)","int x()","::f()","aa::bb()","no bracket","()","a::::b()"};
    for(size_t colons=0;colons<65;colons++)for(size_t prefix=0;prefix<8;prefix++) {
        names.push_back(std::string(prefix,'a')+std::string(colons,':')+"f()");
        names.push_back("void "+std::string(prefix,'a')+std::string(colons,':')+"f(int)");
    }
    for(size_t i=0;i<20000;i++) {
        std::string name;
        for(size_t n=random()%80;n>0;n--)name+="ab :()_"[random()%8];
        names.push_back(name);
    }
    for(const auto &name:names)for(uint8_t strip=0;strip<2;strip++) {
        size_t begin=0,count=0;
        assert(swr_v1_utils_pretty_range(reinterpret_cast<const uint8_t*>(name.data()),name.size(),strip,&begin,&count)==0);
        assert(name.substr(begin,count)==reference::pretty(name,strip));pretty++;
    }
    for(size_t i=0;i<30000;i++) {
        std::string date(i%128,'x'),content(i%1025,'z');
        for(auto &v:date)v=static_cast<char>(random());
        for(auto &v:content)v=static_cast<char>(random());
        const int dp=i%3==0?-1:static_cast<int>(date.size());
        const int cp=i%4==0?-1:static_cast<int>(content.size());
        const int pid=i%7==0?INT_MIN:static_cast<int>(random());
        const int worker=i%11==0?INT_MAX:static_cast<int>(random());
        const int level=static_cast<int>(i%10)-1;
        const auto symbol=static_cast<uint8_t>(random());
        const size_t capacity=i%257;
        std::vector<char> expected(capacity+16,42),actual(capacity+16,42);
        errno=EINTR;
        auto n=reference::log_line(capacity?expected.data():nullptr,capacity,date.c_str(),dp,
                                   static_cast<char>(symbol),pid,worker,level,content.c_str(),cp);
        const int original_errno=errno;errno=EINTR;
        auto got=swr_v1_utils_log_line(capacity?reinterpret_cast<uint8_t*>(actual.data()):nullptr,
                     capacity,reinterpret_cast<const uint8_t*>(date.c_str()),dp,symbol,pid,worker,
                     level,reinterpret_cast<const uint8_t*>(content.c_str()),cp);
        assert(errno==original_errno);assert(got==n);assert(actual==expected);lines++;
    }
    for (size_t i=0;i<30000;i++) {
        const int64_t micros=i==0?INT64_MIN:i==1?INT64_MAX:
            static_cast<int64_t>((uint64_t(random())<<32)|random());
        const size_t capacity=i%32;
        std::vector<char> expected(capacity+16,42),actual(capacity+16,42);
        errno=EINTR;
        auto n=reference::log_micros(capacity?expected.data():nullptr,capacity,micros);
        const int original_errno=errno;errno=EINTR;
        auto got=swr_v1_utils_log_micros(capacity?reinterpret_cast<uint8_t*>(actual.data()):nullptr,capacity,micros);
        assert(got==n);assert(errno==original_errno);assert(actual==expected);
    }
    auto *shared=static_cast<uint32_t*>(mmap(nullptr,4096,PROT_READ|PROT_WRITE,MAP_SHARED|MAP_ANON,-1,0));assert(shared!=MAP_FAILED);
    auto work=[&](uint32_t cpus) {for(int i=0;i<5000;i++) {
        swr_v1_utils_spinlock(shared,cpus,1024);shared[1]++;__atomic_store_n(shared,0,__ATOMIC_SEQ_CST);
    }};
    std::vector<std::thread> threads;for(int i=0;i<4;i++)threads.emplace_back(work,i%2?1:4);for(auto &thread:threads)thread.join();assert(shared[1]==20000);
    pid_t pid=fork();assert(pid>=0);if(pid==0){work(4);_exit(0);}work(4);int status=0;assert(waitpid(pid,&status,0)==pid&&WIFEXITED(status)&&WEXITSTATUS(status)==0);assert(shared[1]==30000);munmap(shared,4096);
    std::cout<<"{\"hash_cases\":"<<hashes<<",\"pretty_cases\":"<<pretty<<",\"logging_cases\":"<<logging<<",\"microsecond_suffixes\":30000,\"log_lines\":"<<lines<<",\"atomic_increments\":30000,\"fork\":true,\"errors\":0}\n";
}
