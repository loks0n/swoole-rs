// Defined positive String copies; no unsafe original zero/overflow/self-private probe.
#include "test_core.h"
#include <array>
#include <iostream>
using swoole::String;
namespace {
unsigned checks=0, allocations=0, frees=0, failed=0, effects=0;
bool fail_next=false;
String *offset_effect=nullptr;
std::array<char,64> effect_log{};
void check(bool ok,const char *label) { if (!ok) throw std::runtime_error(label); ++checks; }
void *allocate(size_t size) {
    effect_log.at(effects++)='M';
    if(offset_effect) { offset_effect->offset=1; offset_effect=nullptr; }
    if (fail_next) { fail_next=false; ++failed; return nullptr; }
    void *p=std::malloc(size); if(p) ++allocations; return p;
}
void dispose(void *p) { effect_log.at(effects++)='F'; ++frees; std::free(p); }
const swoole::Allocator allocator{allocate,std::calloc,std::realloc,dispose};
void snapshot(const String &copy,const String &source,size_t capacity) {
    check(copy.str!=source.str,"copy independent owner");
    check(copy.length==source.length && copy.size==capacity && copy.offset==source.offset,"copy exact metadata");
    check(copy.allocator==source.allocator,"copy allocator provenance");
    check(!std::memcmp(copy.str,source.str,source.length),"copy initialized bytes");
}
}
int main() {
    SwooleG.std_allocator={std::malloc,std::calloc,std::realloc,std::free}; SwooleG.pagesize=4096;
    try {
        for(size_t advertised:{size_t(7),size_t(15),size_t(33)}) {
            String source(64,&allocator); source.append("a\0b",3); source.offset=2; source.size=advertised;
            unsigned before=allocations;
            String copy(source); snapshot(copy,source,SW_MEM_ALIGNED_SIZE(advertised));
            check(allocations==before+1,"one allocation per copy");
            copy.str[0]='z'; check(source.str[0]=='a',"copy writes do not change source");
            String target(8,&allocator); target.append("old",3);
            unsigned prefix=effects; target=source;
            snapshot(target,source,SW_MEM_ALIGNED_SIZE(advertised));
            check(effects==prefix+2 && effect_log[prefix]=='F' && effect_log[prefix+1]=='M',"assignment free before allocation");
            char *owner=target.str; prefix=effects; auto *same=&target; target=*same;
            check(target.str==owner && effects==prefix,"public self-copy does not dispose or allocate");
        }
        {
            String source(8,&allocator); source.append("abc",3); source.offset=1;
            char *owner=source.str; unsigned prefix=effects; fail_next=true; bool caught=false;
            try { String copy(source); } catch(const std::bad_alloc &) { caught=true; }
            check(caught && failed==1 && effects==prefix+1 && effect_log[prefix]=='M',"constructor allocation failure prefix");
            check(source.str==owner && source.length==3 && source.offset==1 && !std::memcmp(source.str,"abc",3),"failed copy preserves source");
        }
        {
            char bytes[8]={'a',0,'b'}; String borrowed;
            borrowed.str=bytes; borrowed.size=sizeof(bytes); borrowed.length=3; borrowed.offset=1;
            String copy(borrowed);
            check(copy.str!=bytes && copy.length==3 && copy.size==8 && copy.offset==1,"borrowed source copied metadata/owner");
            check(copy.allocator==sw_std_allocator() && !std::memcmp(copy.str,bytes,3),"borrowed source adopts standard destination provenance");
            check(borrowed.allocator==nullptr && borrowed.str==bytes,"borrowed source remains borrowed");
        }
        {
            String source(16); source.append("a\0b",3); source.offset=2;
            String copy(source); snapshot(copy,source,16);
        }
        {
            String source(16,&allocator); source.append("abc",3); source.offset=2;
            offset_effect=&source; String copy(source);
            check(offset_effect==nullptr && source.offset==1 && copy.offset==1,"fresh source offset after native allocation effect");
            check(copy.to_std_string()=="abc","offset effect keeps initialized bytes");
        }
        check(allocations==frees,"native allocated owners freed exactly once");
        std::cout<<"{\"positive_copy_checks\":"<<checks<<",\"native_allocations\":"<<allocations<<",\"native_frees\":"<<frees<<",\"caught_constructor_failures\":"<<failed<<",\"errors\":0}\n";
    } catch(const std::exception &error) { std::cerr<<error.what()<<'\n'; return 1; }
}
