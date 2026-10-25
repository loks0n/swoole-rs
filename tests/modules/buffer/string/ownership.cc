// Ordinary positive ownership effects. Observe only live metadata BEFORE free;
// never dereference released bytes or execute zero-owner/unsafe baseline probes.
#include "test_core.h"
#include <iostream>
#include <unordered_set>
using swoole::String;
namespace {
unsigned checks=0, frees=0;
std::unordered_set<void *> live;
String *observed=nullptr;
struct Snapshot { char *data; size_t length,capacity; off_t offset; const swoole::Allocator *allocator; } expected;
bool observed_free=false, metadata_equal=true;
void check(bool value,const char *message) {
    if(!value)throw std::runtime_error(message);
    ++checks;
}
void *allocate(size_t size) { void *value=std::malloc(size);if(value)live.insert(value);return value; }
void *resize(void *value,size_t size) {
    void *next=std::realloc(value,size);
    if(next){live.erase(value);live.insert(next);}
    return next;
}
void release(void *value) {
    if(observed && value==expected.data) {
        observed_free=true;
        metadata_equal=observed->str==expected.data && observed->length==expected.length &&
            observed->size==expected.capacity && observed->offset==expected.offset && observed->allocator==expected.allocator;
    }
    live.erase(value);++frees;std::free(value);
}
const swoole::Allocator allocator{allocate,std::calloc,resize,release};
void watch(String &value) {
    observed=&value;expected={value.str,value.length,value.size,value.offset,value.allocator};
    observed_free=false;metadata_equal=true;
}
void stop_watch() { observed=nullptr; }
}
int main() {
    SwooleG.std_allocator={std::malloc,std::calloc,std::realloc,std::free};SwooleG.pagesize=4096;
    unsigned origin_checks=0;
    try {
        {
            String source(16,&allocator),target(32,&allocator);source.append("new",3);source.offset=1;
            target.append("old",3);target.offset=2;watch(target);target=source;stop_watch();
            check(observed_free,"copy assignment frees prior owner");
            check(metadata_equal,"copy free callback sees original live metadata");
            check(target.length==3 && target.offset==1 && !std::memcmp(target.str,"new",3),"copy publishes source value");
            check(source.length==3 && source.offset==1,"copy retains source");
            watch(target);unsigned before=frees;const String *same=&target;target=*same;stop_watch();
            check(!observed_free && frees==before,"self copy has no disposal");
        }
        {
            String source(16,&allocator),target(32,&allocator);source.append("new",3);source.offset=1;
            target.append("old",3);target.offset=2;char *owner=source.str;watch(target);target=std::move(source);stop_watch();
            check(observed_free,"move assignment frees prior owner");
            check(metadata_equal,"move free callback sees original live metadata");
            check(target.str==owner && target.length==3 && target.offset==1,"move transfers exact owner");
            check(!source.str && !source.length && !source.size && !source.offset && source.allocator==&allocator,"moved source metadata");
            watch(target);unsigned before=frees;String *same=&target;target=std::move(*same);stop_watch();
            check(!observed_free && frees==before,"self move has no disposal");
        }
        {
            String target(16,&allocator);target.append("old",3);target.offset=2;watch(target);
        }
        stop_watch();check(observed_free,"destructor frees owner");check(metadata_equal,"destructor free callback sees original live metadata");
        check(live.empty(),"all custom owners reclaimed");
#ifdef SWR_STRING_RUST_GATE
        struct Guarded { uint64_t before; swr_v1_string_ownership_plan_result plan; uint64_t after; } guard{0x12345678,{},0x87654321};
        auto *owner=static_cast<uint8_t *>(std::malloc(8));
        if(!owner)throw std::bad_alloc();
        const auto status=swr_v1_string_ownership_plan(SWR_STRING_OWNER_COPY,0,1,owner,&guard.plan);
        const bool layout=status==0 && guard.plan.owner==owner && guard.plan.actions==0x0201 && guard.before==0x12345678 && guard.after==0x87654321;
        const bool same=swr_v1_string_ownership_plan(SWR_STRING_OWNER_MOVE,1,1,owner,&guard.plan)==0 && !guard.plan.owner && !guard.plan.actions;
        const bool invalid=swr_v1_string_ownership_plan(99,0,1,owner,&guard.plan)<0 && !guard.plan.owner && !guard.plan.actions;
        std::free(owner);
        if(!layout || !same || !invalid)throw std::runtime_error("Rust ownership ABI/model guards");
        origin_checks=3;
#endif
        std::cout<<"{\"checks\":"<<checks<<",\"selected_origin_checks\":"<<origin_checks<<"}"<<std::endl;
    } catch(const std::exception &error) {
        stop_watch();std::cerr<<error.what()<<std::endl;return 1;
    }
}
