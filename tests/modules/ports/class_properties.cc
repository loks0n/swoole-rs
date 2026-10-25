// Original/selected actual declaration statements with inert Zend sinks only.
#include "swoole_rs_ports.h"
#include <cassert>
#include <cstdint>
#include <limits>
#include <iostream>
#include <string>
#include <vector>
#include <tuple>
#define ZEND_STRL(s) s,sizeof(s)-1
constexpr int ZEND_ACC_PRIVATE=4,ZEND_ACC_PUBLIC=1;
static int entry;
static int *swoole_server_port_ce=&entry;
using Row=std::tuple<std::string,int,int64_t,int>;
static std::vector<Row> declarations;
static void record(int *ce,const char *name,size_t len,int kind,int64_t value,int flags) {
    assert(ce==&entry);declarations.emplace_back(std::string(name,len),kind,value,flags);
}
static void zend_declare_property_null(int *ce,const char *name,size_t len,int flags) {record(ce,name,len,1,0,flags);}
static void zend_declare_property_long(int *ce,const char *name,size_t len,int64_t value,int flags) {record(ce,name,len,2,value,flags);}
static void zend_declare_property_bool(int *ce,const char *name,size_t len,bool value,int flags) {record(ce,name,len,3,value,flags);}
namespace original {
#include "original.inc"
}
namespace selected {
#include "selected.inc"
}
int main() {
    static_assert(sizeof(SwrPortsProperty)==32&&offsetof(SwrPortsProperty,value)==16&&offsetof(SwrPortsProperty,kind)==24,"Port property ABI");
    original::declare_properties();auto expected=declarations;assert(expected.size()==19);
    for(unsigned round=0;round<256;round++) {
        declarations.clear();selected::declare_properties();assert(declarations==expected);
        for(size_t i=0;i<expected.size();i++) {
            auto property=swr_v1_ports_class_property(i);auto[name,kind,value,flags]=expected[i];
            assert(property.name.data&&std::string(reinterpret_cast<const char*>(property.name.data),property.name.len)==name);
            assert(property.kind==unsigned(kind)&&property.value==value);
            assert((property.is_private?ZEND_ACC_PRIVATE:ZEND_ACC_PUBLIC)==flags);
            auto again=swr_v1_ports_class_property(i);assert(again.name.data==property.name.data&&again.name.len==property.name.len);
        }
    }
    for(size_t i:{size_t(19),size_t(20),std::numeric_limits<size_t>::max()}) {
        auto end=swr_v1_ports_class_property(i);assert(end.kind==SWR_PORTS_PROPERTY_END&&!end.name.data&&!end.name.len&&!end.value&&!end.is_private);
    }
    std::cout<<"4864 exact declaration/metadata comparisons plus256 whole ordered declarations PASS\n";
}
