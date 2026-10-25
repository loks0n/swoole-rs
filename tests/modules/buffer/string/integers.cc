// Defined integer append with exact storage/allocation prefixes; no unsafe probes.
#include "test_core.h"
#include <array>
#include <iostream>
#include <limits>
using swoole::String;
namespace {
unsigned checks=0, allocations=0, reallocations=0, frees=0, failures=0;
bool fail_next=false;
void check(bool ok,const char *label) { if(!ok) throw std::runtime_error(label); ++checks; }
void *allocate(size_t n) { void *p=std::malloc(n); if(p) ++allocations; return p; }
void *resize(void *p,size_t n) { ++reallocations; if(fail_next) { fail_next=false; ++failures; return nullptr; } return std::realloc(p,n); }
void dispose(void *p) { ++frees; std::free(p); }
const swoole::Allocator allocator{allocate,std::calloc,resize,dispose};
}
int main() {
    SwooleG.std_allocator={std::malloc,std::calloc,std::realloc,std::free}; SwooleG.pagesize=4096;
    try {
        for(const auto *policy:{sw_std_allocator(),&allocator}) {
            for(int value:{std::numeric_limits<int>::min(),-123456789,-1,0,1,std::numeric_limits<int>::max()}) {
                for(size_t spare:{size_t(0),size_t(2),size_t(11),size_t(16)}) {
                    String text(32,policy); std::string prefix(text.size-spare,'a'); text.append(prefix); text.offset=1;
                    std::string expected=prefix+std::to_string(value); size_t old_capacity=text.size;
                    unsigned before=reallocations; text.append(value);
                    check(text.to_std_string()==expected,"decimal bytes and prefix");
                    check(text.length==expected.size() && text.offset==1,"length/offset publication");
                    size_t expected_capacity=expected.size()>old_capacity ? SW_MEM_ALIGNED_SIZE(expected.size()):old_capacity;
                    check(text.size==expected_capacity,"exact aligned append capacity");
                    check(text.allocator==policy,"allocator provenance");
                    check(reallocations==before+unsigned(policy==&allocator && expected.size()>old_capacity),"exact custom realloc count");
                }
            }
        }
        {
            String text(8,&allocator); text.append("prefix",6); text.offset=2;
            char *owner=text.str; auto capacity=text.size; unsigned before=reallocations;
            fail_next=true; bool caught=false;
            try { text.append(std::numeric_limits<int>::min()); } catch(const std::bad_alloc &) { caught=true; }
            check(caught && failures==1 && reallocations==before+1,"caught integer append realloc failure");
            check(text.str==owner && text.size==capacity && text.length==6 && text.offset==2 && text.to_std_string()=="prefix","failed append preserves owner/metadata/bytes");
            text.append(-7); check(text.to_std_string()=="prefix-7","append after caught failure");
        }
        check(allocations==frees,"native owners freed exactly once");
        std::cout<<"{\"positive_integer_checks\":"<<checks<<",\"native_allocations\":"<<allocations<<",\"native_frees\":"<<frees<<",\"native_reallocations\":"<<reallocations<<",\"caught_realloc_failures\":"<<failures<<",\"errors\":0}\n";
    } catch(const std::exception &error) { std::cerr<<error.what()<<'\n'; return 1; }
}
