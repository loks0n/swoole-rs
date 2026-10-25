// Ordinary positive entropy/codec consumer only. No zero encoded or injected
// entropy failure; exact random bytes are not compared between engines.
#include "test_core.h"
#include <openssl/evp.h>
#include <iostream>
using swoole::String;
namespace {
unsigned checks=0,allocations=0,frees=0,array_releases=0;
String *encoded_subject=nullptr;size_t expected_prefix=0;bool scalar_prefix=true;
void check(bool value,const char *message) {if(!value)throw std::runtime_error(message);++checks;}
void *allocate(size_t n) {auto *p=std::malloc(n);if(p)++allocations;return p;}
void release(void *p) {++frees;std::free(p);}
const swoole::Allocator allocator{allocate,std::calloc,std::realloc,release};
struct Observation {
    Observation(String &value,size_t prefix){encoded_subject=&value;expected_prefix=prefix;scalar_prefix=true;}
    ~Observation(){encoded_subject=nullptr;}
};
bool canonical(const std::string &text,size_t count) {
    std::vector<unsigned char> bytes(text.size()+3),encoded(text.size()+1);
    auto n=EVP_DecodeBlock(bytes.data(),reinterpret_cast<const unsigned char *>(text.data()),text.size());
    if(n<0)return false;
    size_t padding=(text.back()=='=')+(text.size()>1 && text[text.size()-2]=='=');
    if(static_cast<size_t>(n)<padding || static_cast<size_t>(n)-padding!=count)return false;
    auto size=EVP_EncodeBlock(encoded.data(),bytes.data(),count);
    return size==static_cast<int>(text.size()) && !std::memcmp(encoded.data(),text.data(),text.size());
}
}
// Ordinary paired native char-array allocator effects. Inspect initialized live
// String length before free; never inspect released allocation bytes or reenter.
void *operator new[](size_t n) {void *p=std::malloc(n?n:1);if(!p)throw std::bad_alloc();return p;}
void operator delete[](void *p) noexcept {
    if(encoded_subject){++array_releases;scalar_prefix=scalar_prefix && encoded_subject->length==expected_prefix;}
    std::free(p);
}
void operator delete[](void *p,size_t) noexcept {operator delete[](p);}
int main() {
    SwooleG.std_allocator={std::malloc,std::calloc,std::realloc,std::free};SwooleG.pagesize=4096;
    try {
        for(const auto *policy:{sw_std_allocator(),&allocator})for(bool encoded:{false,true})
        for(size_t count:{size_t(1),size_t(2),size_t(3),size_t(4),size_t(7),size_t(16),size_t(63),size_t(1024)})
        for(size_t prefix:{size_t(0),size_t(3),size_t(31)}) {
            String value(32,policy);std::string initial(prefix,'a');value.append(initial);value.offset=1;
            const size_t expected=encoded?4*((count+2)/3):count;
            const size_t requested=prefix+count+(encoded?expected+1:0);
            const size_t capacity=requested>32?(requested*2+4095)&~size_t(4095):32;
            const auto before=array_releases;bool success;
            {Observation observation(value,prefix);success=value.append_random_bytes(count,encoded);}
            check(success,"ordinary positive entropy success");
            check(array_releases-before==(encoded?1u:0u) && scalar_prefix,"native encoded-owner release observes original scalar prefix");
            check(value.length==prefix+expected,"exact output length");check(value.size==capacity,"exact native reserve policy");
            check(value.offset==1 && value.allocator==policy,"offset/provenance retained");
            check(!std::memcmp(value.str,initial.data(),prefix),"existing prefix retained");
            check(!encoded || canonical(std::string(value.str+prefix,expected),count),"independent OpenSSL canonical codec witness");
        }
        check(allocations==frees,"custom owner custody");
        std::cout<<"{\"checks\":"<<checks<<"}"<<std::endl;
    }catch(const std::exception &error){encoded_subject=nullptr;std::cerr<<error.what()<<std::endl;return 1;}
}
