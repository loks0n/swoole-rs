#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <type_traits>
#include <vector>
namespace swoole { namespace network { struct Socket { int fd; }; } }
#include "swoole_rs_reactor_sockets.h"
#include "iterator-control.h"
static size_t checks=0;
#define CHECK(x) do { ++checks; assert(x); } while(0)
using Live=swoole::ReactorSocketView::Iterator;
using OldLive=native_iterator_control::ReactorSocketView::Iterator;
using Copy=swoole::ReactorSocketSnapshot::Iterator;
using OldCopy=native_iterator_control::ReactorSocketSnapshot::Iterator;
static_assert(sizeof(Live)==sizeof(OldLive)&&sizeof(Live)==56,"live footprint");
static_assert(alignof(Live)==alignof(OldLive)&&alignof(Live)==8,"live alignment");
static_assert(sizeof(Copy)==sizeof(OldCopy)&&sizeof(Copy)==16,"snapshot footprint");
static_assert(alignof(Copy)==alignof(OldCopy)&&alignof(Copy)==8,"snapshot alignment");
static_assert(std::is_trivially_copyable<Live>::value&&std::is_trivially_copyable<OldLive>::value,"live copy trait");
static_assert(std::is_trivially_copyable<Copy>::value&&std::is_trivially_copyable<OldCopy>::value,"snapshot copy trait");
static_assert(std::is_nothrow_default_constructible<Live>::value&&std::is_nothrow_default_constructible<OldLive>::value,"default trait");
static_assert(sizeof(swr_v1_reactor_socket_live_iterator)==56,"Rust live POD");
static_assert(offsetof(swr_v1_reactor_socket_live_iterator,cursor)==8,"cursor");
static_assert(offsetof(swr_v1_reactor_socket_live_iterator,value)==32,"entry");
static_assert(offsetof(swr_v1_reactor_socket_live_iterator,done)==48,"done");
static_assert(sizeof(swr_v1_reactor_socket_snapshot_iterator)==16,"Rust snapshot POD");
static_assert(offsetof(swr_v1_reactor_socket_snapshot_iterator,index)==8,"index");
template<class Range,class OldRange> void compare(const Range &range,const OldRange &old) {
    auto current=range.begin();auto expected=old.begin();
    CHECK((current==range.end())==(expected==old.end()));
    CHECK((current!=range.end())==(expected!=old.end()));
    unsigned count=0;
    while(expected!=old.end()) {
        CHECK(current!=range.end());CHECK(*current==*expected);
        auto copied=current;auto old_copied=expected;
        CHECK((copied==current)==(old_copied==expected));
        CHECK((copied!=current)==(old_copied!=expected));
        if(count++%2==0) {
            auto previous=current++;auto old_previous=expected++;
            CHECK(*previous==*old_previous);
            CHECK((previous==current)==(old_previous==expected));
            CHECK((previous!=current)==(old_previous!=expected));
        } else { ++current;++expected; }
        CHECK((current==range.end())==(expected==old.end()));
    }
    CHECK(current==range.end());
}
int main() {
    bool yes=true;unsigned char representation=0;
    static_assert(sizeof(yes)==1,"Native bool footprint");std::memcpy(&representation,&yes,1);CHECK(representation==1);
    unsigned schemas=0;
    for(int count:{0,1,3,17,65}) {
        swoole::ReactorSocketRegistry selected;
        native_iterator_control::ReactorSocketRegistry control;
        swoole::network::Socket values[65]{};
        for(int index=0;index<count;++index) {
            values[index].fd=index*3-7;selected.put(values[index].fd,&values[index]);control.put(values[index].fd,&values[index]);
        }
        compare(selected.view(),control.view());
        const auto snapshot=selected.snapshot();const auto old_snapshot=control.snapshot();
        compare(snapshot,old_snapshot);
        Live end;OldLive old_end;CHECK((end==selected.view().end())==(old_end==control.view().end()));
        ++schemas;
    }
    std::cout<<"{\"schemas\":"<<schemas<<",\"checks\":"<<checks<<",\"live_bytes\":"<<sizeof(Live)<<",\"snapshot_bytes\":"<<sizeof(Copy)<<",\"native_effects\":false}\n";
}
