// Positive allocation observations only. No ceiling, injected failure or clock.
#include "swoole_mime_type.h"
#ifdef CANDIDATE
#include "swoole_rs_framing.h"
#endif
#include <cassert>
#include <cstdlib>
#include <new>
#include <string>
#include <vector>
#include <iostream>
static bool tracking=false;
static size_t calls=0,largest=0;
void *operator new(size_t n) {
    if(tracking) { ++calls; if(n>largest)largest=n; }
    if(void *p=std::malloc(n?n:1))return p;
    throw std::bad_alloc();
}
void *operator new[](size_t n) {return ::operator new(n);}
void operator delete(void *p) noexcept {std::free(p);}
void operator delete[](void *p) noexcept {std::free(p);}
void operator delete(void *p,size_t) noexcept {std::free(p);}
void operator delete[](void *p,size_t) noexcept {std::free(p);}
struct Case {std::string filename;const char *expected;bool short_suffix_long_prefix;};
int main() {
    std::vector<Case> cases={{"file.JSON","application/json",false},
        {std::string(2048,'x')+".json","application/json",true},
        {std::string(2048,'x'),"application/octet-stream",false},
        {"file."+std::string(2048,'x'),"application/octet-stream",false},
        {"file.","application/octet-stream",false},{"","application/octet-stream",false},
        {std::string(4096,'x')+".HTML","text/html",true}};
    for(size_t i=0;i<cases.size();++i) {
        const auto &test=cases[i];calls=largest=0;tracking=true;
        const auto *value=&swoole::mime_type::get(test.filename);
        tracking=false;assert(*value==test.expected);assert(value==&swoole::mime_type::get(test.filename));
#ifdef CANDIDATE
        if(test.short_suffix_long_prefix)assert(calls==0&&largest==0);
#endif
        std::cout<<"{\"case\":"<<i<<",\"filename_bytes\":"<<test.filename.size()<<",\"CXX_new_calls\":"<<calls<<",\"largest_CXX_new\":"<<largest<<",\"value_and_reference_match\":true}\n";
    }
#ifdef CANDIDATE
    uint64_t seed=0x737566666978;
    auto next=[&](){seed^=seed<<13;seed^=seed>>7;seed^=seed<<17;return seed;};
    for(unsigned i=0;i<8192;i++) {
        std::string input(next()%256,'x');for(char &c:input)c=char(next()%128);
        auto dot=input.find_last_of('.');auto expected=dot==input.npos?0:dot+1;
        assert(swr_v1_framing_mime_suffix_offset(reinterpret_cast<const uint8_t*>(input.data()),input.size())==expected);
    }
    assert(swr_v1_framing_mime_suffix_offset(nullptr,0)==0);
    std::cout<<"{\"ordinary_offset_cases\":8193,\"passed\":true}\n";
#endif
}
