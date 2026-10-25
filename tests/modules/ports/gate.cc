#include "swoole_rs_ports.h"
#include <algorithm>
#include <climits>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <limits>
#include <strings.h>
#include <string>
#include <unordered_map>
#include "reference.inc"

static uint64_t checks;
static void check(bool ok) { if(!ok){std::cerr<<"failed check "<<checks<<"\n";std::abort();}checks++; }
static uint64_t random_state=71234;
static uint64_t random_word() { random_state^=random_state<<13;random_state^=random_state>>7;return random_state^=random_state<<17; }
static void event(const std::string &name,bool folded) {
    int expected=-1;std::string property;
    for(const auto &entry: server_port_event_map) {
        if(folded ? swoole_strcaseeq(name.data(),name.size(),entry.first.data(),entry.first.size()) : name==entry.first) {
            expected=entry.second.type;property="on"+entry.second.name;break;
        }
    }
    auto value=swr_v1_ports_event(reinterpret_cast<const uint8_t *>(name.data()),name.size(),folded);
    check(value.index==expected);
    if(expected>=0)check(std::string(reinterpret_cast<const char *>(value.property.data),value.property.len)==property);
    else check(value.property.data==nullptr&&value.property.len==0);
}
int main() {
    static_assert(sizeof(SwrPortsSpan)==16&&sizeof(SwrPortsEvent)==24,"ports 64-bit span ABI");
    static_assert(sizeof(SwrPortsProtocolInput)==28&&sizeof(SwrPortsProtocolAction)==8&&sizeof(SwrPortsProtocolPlan)==52,"protocol plan C ABI");
    static_assert(offsetof(SwrPortsProtocolPlan,actions)==4,"protocol action alignment");
    for(uint32_t flags=0;flags<512;flags++)for(uint32_t type:{0u,1u,255u})for(uint32_t eof:{0u,1u,8u,9u,255u}) {
        auto plan=swr_v1_ports_protocol_plan({flags,type,eof,8,9,2,4});
        check(plan.count<=6);
        check((plan.count==0)==bool((flags&SWR_PORTS_DGRAM)&&!(flags&SWR_PORTS_DTLS)));
        for(uint32_t n=0;n<6;n++) {
            auto action=plan.actions[n];
            if(n>=plan.count){check(action.kind==0&&action.value==0);continue;}
            check(action.kind>=SWR_PORTS_SET_EOF_LEN&&action.kind<=SWR_PORTS_SET_BODY_OFFSET);
            if(action.kind==SWR_PORTS_SET_READ)check(action.value>=1&&action.value<=5);
            if(action.kind==SWR_PORTS_SET_PACKAGE)check(action.value>=1&&action.value<=3);
            if(action.kind==SWR_PORTS_SET_LENGTH_FN)check(action.value>=1&&action.value<=5);
            if(action.kind==SWR_PORTS_SET_LENGTH_SIZE_FN)check(action.value==0);
        }
    }
    for(uint64_t n=0;n<50000;n++) {
        int64_t value;auto raw=random_word();memcpy(&value,&raw,8);
        if(n<10)value=std::initializer_list<int64_t>{INT64_MIN,INT64_MAX,INT32_MIN,INT32_MAX,-1,0,1,255,65535,UINT32_MAX}.begin()[n];
        check(swr_v1_ports_number(SWR_PORTS_U16,value)==SW_MAX(0,SW_MIN(value,UINT16_MAX)));
        check(swr_v1_ports_number(SWR_PORTS_U32,value)==SW_MAX(0,SW_MIN(value,UINT32_MAX)));
        check(swr_v1_ports_number(SWR_PORTS_I32,value)==SW_MAX(INT_MIN,SW_MIN(value,INT_MAX)));
        check(swr_v1_ports_number(SWR_PORTS_U8,value)==SW_MAX(0,SW_MIN(value,UINT8_MAX)));
        int64_t buffer=SW_MAX(INT_MIN,SW_MIN(value,INT_MAX));if(buffer<=0)buffer=INT_MAX;
        check(swr_v1_ports_number(SWR_PORTS_BUFFER,value)==buffer);

    }
    for(const auto &entry:server_port_event_map) {
        event(entry.first,false);event(entry.first,true);
        auto upper=entry.first;for(char &c:upper)c=char(c>='a'&&c<='z'?c-32:c);
        event(upper,true);event(upper,false);
        for(size_t n=0;n<entry.first.size();n++)for(unsigned c=0;c<256;c++) {
            auto changed=entry.first;changed[n]=char(c);event(changed,true);event(changed,false);
        }
    }
    event("",true);event("unknown",false);event(std::string("connect\0",8),true);
    auto missing=swr_v1_ports_event(nullptr,0,1);check(missing.index==-1);
    std::cout<<"{\"checks\":"<<checks<<",\"errors\":0}"<<std::endl;
}
