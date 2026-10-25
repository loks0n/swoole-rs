#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <string>
#include <unordered_map>
#include <vector>
#include "swoole_rs_phphelpers.h"
using namespace std::string_literals;
struct zval { uint64_t first, second; bool operator==(const zval &other) const { return first==other.first && second==other.second; } };
namespace reference {
#include "aliases.inc"
#include "arguments.inc"
}
namespace selected {
#include "selected-arguments.inc"
}
int main() {
    size_t aliases=0,permutations=0,unknowns=0;
    const std::unordered_map<std::string,std::string> *families[]={&reference::array_methods,&reference::string_methods,&reference::stream_methods};
    for(uint32_t family=0;family<3;++family) {
        for(const auto &item:*families[family]) {
            size_t length=0;
            const char *name=swr_v1_phphelpers_alias(family,reinterpret_cast<const uint8_t *>(item.first.data()),item.first.size(),&length);
            assert(name && length==item.second.size() && std::string(name,length)==item.second && name[length]=='\0');++aliases;
            for(const auto &probe:{item.first+"\0extra"s,"missing-"+item.first}) {
                const auto found=families[family]->find(probe);
                const char *actual=swr_v1_phphelpers_alias(family,reinterpret_cast<const uint8_t *>(probe.data()),probe.size(),&length);
                assert((found==families[family]->end()) == (actual==nullptr));++unknowns;
            }
        }
    }
    assert(aliases==151);
    for(int count=1;count<=64;++count) for(int position=0;position<count;++position) {
        std::vector<zval> input(count),native(count),rust(count);
        for(int i=0;i<count;++i) input[i]={static_cast<uint64_t>(i),static_cast<uint64_t>(i*7)};
        reference::move_first_element(input.data(),native.data(),count,position);
        selected::move_first_element(input.data(),rust.data(),count,position);
        assert(native==rust);++permutations;
    }
    for(int64_t result:{INT64_MIN,int64_t(-1),int64_t(0),int64_t(1),INT64_MAX}) {
        assert(swr_v1_phphelpers_call_success(result,0)==(result==0));
        assert(swr_v1_phphelpers_call_success(result,1)==(result>=0));
    }
    const std::string a="<int,string>",b="<int,int>";
    assert(swr_v1_phphelpers_type_equal(3,5,3,5,reinterpret_cast<const uint8_t *>(a.data()),a.size(),reinterpret_cast<const uint8_t *>(a.data()),a.size()));
    assert(!swr_v1_phphelpers_type_equal(3,5,3,5,reinterpret_cast<const uint8_t *>(a.data()),a.size(),reinterpret_cast<const uint8_t *>(b.data()),b.size()));
    std::cout<<"{\"aliases\":"<<aliases<<",\"unknowns\":"<<unknowns<<",\"actual_permutations\":"<<permutations<<"}\n";
}
