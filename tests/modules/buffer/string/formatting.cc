// Whole defined format/append workflows: stable variadic arguments, positive
// storage, offset-only allocator effect, and caught allocation failure.
#include "test_core.h"
#include <iostream>
using swoole::String;
namespace {
unsigned checks=0,allocations=0,frees=0,resizes=0;
bool fail_resize=false,offset_effect=false;
String *observed=nullptr;
void check(bool value,const char *message) {if(!value)throw std::runtime_error(message);++checks;}
void *allocate(size_t size) {auto *p=std::malloc(size);if(p)++allocations;return p;}
void *resize(void *p,size_t size) {++resizes;if(offset_effect && observed)observed->offset=2;if(fail_resize)return nullptr;return std::realloc(p,size);}
void release(void *p) {++frees;std::free(p);}
const swoole::Allocator allocator{allocate,std::calloc,resize,release};
}
int main() {
    SwooleG.std_allocator={std::malloc,std::calloc,std::realloc,std::free};SwooleG.pagesize=4096;
    try {
        for(const auto *policy:{sw_std_allocator(),&allocator}) {
            for(int flags:{0,1,2,3}) {
                for(size_t prefix:{size_t(0),size_t(3),size_t(7)}) {
                    for(size_t width:{size_t(1),size_t(3),size_t(17),size_t(65)}) {
                        String value(8,policy);std::string initial(prefix,'a');value.append(initial);value.offset=1;
                        std::string text(width,'x');const std::string output=text+":-7";
                        std::string expected=(flags&1 ? initial : std::string())+output;
                        size_t capacity=8,needed=expected.size()+1;
                        if(needed>capacity) {if(flags&2){capacity*=2;while(capacity<needed)capacity*=2;}else capacity=(needed+7)&~size_t(7);}
                        auto n=value.format_impl(flags,"%s:%d",text.c_str(),-7);
                        check(n==output.size(),"returned printf count");check(value.to_std_string()==expected,"exact formatted bytes");
                        check(value.length==expected.size(),"exact published length");check(value.size==capacity,"exact capacity policy");
                        check(value.offset==1 && value.allocator==policy,"offset/provenance retained");check(value.str[value.length]==0,"printf terminator");
                    }
                }
                String empty(8,policy);empty.append("old",3);empty.offset=1;auto *owner=empty.str;auto before=resizes;
                check(empty.format_impl(flags,"%s","")==0,"empty sizing return");
                check(empty.str==owner && empty.length==3 && empty.size==8 && empty.offset==1 && empty.to_std_string()=="old" && resizes==before,"empty sizing preserves metadata/value/effects");
                String binary(8,policy);binary.append("a",1);auto n=binary.format_impl(flags,"%c%c",0,'b');
                std::string expected=(flags&1 ? std::string("a") : std::string())+std::string("\0b",2);
                check(n==2 && binary.to_std_string()==expected,"binary printf output");
            }
        }
        {
            String value(8,&allocator);value.append("prefix",6);value.offset=1;auto *owner=value.str;auto before=resizes;
            bool caught=false;fail_resize=true;
            try{value.append_format("%s","a long positive string");}catch(const std::bad_alloc&){caught=true;}
            fail_resize=false;
            check(caught && resizes==before+1,"caught native formatting reserve failure");
            check(value.str==owner && value.length==6 && value.size==8 && value.offset==1 && value.to_std_string()=="prefix","format failure prefix");
            observed=&value;offset_effect=true;value.append_format("%s","a long positive string");offset_effect=false;observed=nullptr;
            check(value.offset==2 && value.to_std_string()=="prefixa long positive string","post-effect offset retained");
        }
        check(allocations==frees,"custom allocation custody");
        std::cout<<"{\"checks\":"<<checks<<"}"<<std::endl;
    } catch(const std::exception &error) {observed=nullptr;std::cerr<<error.what()<<std::endl;return 1;}
}
