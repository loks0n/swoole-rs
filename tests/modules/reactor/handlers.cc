#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include "swoole_rs_reactor.h"
#include "handlers.inc"
using namespace swoole;
static unsigned invoked;
static int read_effect(Reactor*,Event*){++invoked;return 1;}
static int write_effect(Reactor*,Event*){++invoked;return 2;}
static int error_effect(Reactor*,Event*){++invoked;return 3;}
static int default_write_effect(Reactor*,Event*){++invoked;return 4;}
static int default_error_effect(Reactor*,Event*){++invoked;return 5;}
int main(){
    unsigned checks=0,cases=0;auto check=[&](bool value){assert(value);++checks;};
    ReactorHandler pointers[]={read_effect,write_effect,error_effect,default_write_effect,default_error_effect};
    for(unsigned present=0;present<32;++present)for(int fd=0;fd<2;++fd){
        Reactor r;ReactorHandler values[5];for(unsigned slot=0;slot<5;++slot)values[slot]=(present&(1u<<slot))?pointers[slot]:nullptr;
        r.read_handler[fd]=values[0];r.write_handler[fd]=values[1];r.error_handler[fd]=values[2];r.default_write_handler=values[3];r.default_error_handler=values[4];
        for(int mask=0;mask<8;++mask)for(int once=0;once<2;++once){
            int event=(mask<<9)|(once?SW_EVENT_ONCE:0);int slot=(event<SW_EVENT_DEAULT||(mask&1))?0:(mask&2)?1:(mask&4)?2:-1;
            check(r.isset_handler(fd,event)==(slot>=0&&values[slot]!=nullptr));++cases;
        }
        for(int slot=0;slot<3;++slot){
            auto result=r.get_handler(fd,static_cast<EventType>(1<<(9+slot)));
            auto expected=values[slot]?values[slot]:slot==1?values[3]:slot==2?values[4]:nullptr;
            check(result==expected);if(result){check(result(&r,nullptr)==(expected==pointers[0]?1:expected==pointers[1]?2:expected==pointers[2]?3:expected==pointers[3]?4:5));}
            ++cases;
        }
        auto expected=values[2]?values[2]:values[4]?values[4]:values[0]?values[0]:values[1]?values[1]:values[3];
        auto result=r.get_error_handler(fd);check(result==expected);if(result)check(result(&r,nullptr)>0);++cases;
    }
    for(int mask=0;mask<8;++mask)for(int once=0;once<2;++once)for(int candidate=0;candidate<6;++candidate)for(int fd=0;fd<2;++fd){
        if(mask==0&&once)continue; // Original invalid set/assert domain excluded.
        Reactor r;for(int i=0;i<2;++i){r.read_handler[i]=read_effect;r.write_handler[i]=write_effect;r.error_handler[i]=error_effect;}
        auto value=candidate?pointers[candidate-1]:nullptr;
        int event=(mask<<9)|(once?SW_EVENT_ONCE:0);
        r.set_handler(fd,event,value);int slot=(event<SW_EVENT_DEAULT||(mask&1))?0:(mask&2)?1:2;
        check(r.read_handler[fd]==(slot==0?value:read_effect));check(r.write_handler[fd]==(slot==1?value:write_effect));check(r.error_handler[fd]==(slot==2?value:error_effect));
        check(r.read_handler[1-fd]==read_effect&&r.write_handler[1-fd]==write_effect&&r.error_handler[1-fd]==error_effect);++cases;
    }
    for(int legacy:{7,255}) {Reactor r;r.set_handler(0,legacy,read_effect);check(r.read_handler[0]==read_effect);check(r.isset_handler(0,legacy));++cases;}
    std::cout<<"{\"cases\":"<<cases<<",\"checks\":"<<checks<<",\"native_invocations\":"<<invoked<<",\"fault_or_lifetime_probes\":false}\n";
}
