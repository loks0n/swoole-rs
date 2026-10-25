// Defined allocation effects: read initialized scalar metadata only, and mutate
// only offset inside native realloc. No released pointer/byte access or reentry.
#include "test_core.h"
#include <iostream>
using swoole::String;
namespace {
unsigned checks=0,mallocs=0,frees=0;
String *observed=nullptr;
bool initial_metadata=false,change_offset=false,fail_resize=false;
void check(bool value,const char *message) { if(!value)throw std::runtime_error(message);++checks; }
void *allocate(size_t size) {
    ++mallocs;
    if(observed)initial_metadata=observed->length==0 && observed->size==size && observed->offset==0;
    return std::malloc(size);
}
void *resize(void *owner,size_t size) {
    if(change_offset && observed)observed->offset=2;
    if(fail_resize)return nullptr;
    return std::realloc(owner,size);
}
void release(void *owner) {++frees;std::free(owner);}
const swoole::Allocator allocator{allocate,std::calloc,resize,release};
}
int main() {
    SwooleG.std_allocator={std::malloc,std::calloc,std::realloc,std::free};SwooleG.pagesize=4096;
    try {
        {
            String source(16,&allocator),target(32,&allocator);source.append("new",3);source.offset=1;target.append("old",3);target.offset=2;
            observed=&target;target=source;observed=nullptr;
            check(initial_metadata,"copy allocation publishes initial scalar metadata before malloc");
            check(target.to_std_string()=="new" && target.length==3 && target.offset==1,"copy publishes live source after allocation");
            check(target.size==16 && target.allocator==&allocator,"copy allocation capacity/provenance");
            observed=&target;change_offset=true;target.reserve(65);change_offset=false;observed=nullptr;
            check(target.size==72,"aligned reserve capacity");
            check(target.length==3 && target.offset==2,"reserve preserves benign native offset effect");
            check(target.to_std_string()=="new" && target.allocator==&allocator,"reserve value/provenance");
            auto *owner=target.str;auto capacity=target.size;fail_resize=true;bool caught=false;
            try {target.reserve(128);}catch(const std::bad_alloc&){caught=true;}
            fail_resize=false;
            check(caught,"reserve OOM remains native exception");
            check(target.str==owner && target.size==capacity && target.length==3 && target.offset==2,"failed reserve prefix retained");
        }
        check(mallocs==3 && frees==3,"custom allocation custody");
        {String empty;empty.reserve(17);check(empty.size==24 && !empty.length && !empty.offset,"empty reserve initializes aligned metadata");check(empty.str && empty.allocator==sw_std_allocator(),"empty reserve selects standard native allocator");}
        {String value(17);check(value.str && value.size==24 && !value.length && !value.offset,"initial aligned allocation");}
        std::cout<<"{\"checks\":"<<checks<<"}"<<std::endl;
    } catch(const std::exception &error) {observed=nullptr;std::cerr<<error.what()<<std::endl;return 1;}
}
