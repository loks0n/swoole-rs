// Exact pinned/selected binding statements with inert slots; never call callbacks.
#include "swoole_rs_ports.h"
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <limits>
#include <sstream>
#include <string>
#include <vector>
#include "events.inc"
using Hook=void(*)();
static void existing() {}
static void php_swoole_server_onConnect() {}
static void php_swoole_server_onPacket() {}
static void php_swoole_server_onClose() {}
static void php_swoole_server_onBufferFull() {}
static void php_swoole_server_onBufferEmpty() {}
static std::ostringstream trace;
struct Slot {
    const char *name;
    Hook value;
    bool operator!()const {trace<<"read:"<<name<<';';return !value;}
    Slot &operator=(Hook next){trace<<"write:"<<name<<';';value=next;return *this;}
};
struct Server {
    Slot onConnect{"connect",nullptr},onPacket{"packet",nullptr},onClose{"close",nullptr},onBufferFull{"full",nullptr},onBufferEmpty{"empty",nullptr};
};
namespace Original {
#include "original.inc"
}
namespace Selected {
#include "selected.inc"
}
static std::string run(bool selected,int index,unsigned mask) {
    trace.str("");trace.clear();Server server;
    Slot *slots[]={&server.onConnect,&server.onPacket,&server.onClose,&server.onBufferFull,&server.onBufferEmpty};
    Hook functions[]={php_swoole_server_onConnect,php_swoole_server_onPacket,php_swoole_server_onClose,php_swoole_server_onBufferFull,php_swoole_server_onBufferEmpty};
    for(unsigned n=0;n<5;n++)slots[n]->value=mask&(1u<<n)?existing:nullptr;
    if(selected)Selected::apply(&server,index);else Original::apply(&server,index);
    for(unsigned n=0;n<5;n++){auto value=slots[n]->value;assert(!value||value==existing||value==functions[n]);trace<<"final:"<<n<<':'<<(value==existing?1:value==functions[n]?2:0)<<';';}
    return trace.str();
}
int main() {
    size_t cases=0;std::vector<int>indices;
    for(int i=-2;i<15;i++)indices.push_back(i);
    indices.push_back(std::numeric_limits<int32_t>::min());indices.push_back(std::numeric_limits<int32_t>::max());
    for(int index:indices)for(unsigned mask=0;mask<32;mask++) {
        auto expected=run(false,index,mask),actual=run(true,index,mask);
        if(expected!=actual){fprintf(stderr,"hook trace mismatch index=%d mask=%u\n",index,mask);return 1;}cases++;
    }
    printf("%zu exact callback binding comparisons passed; no callback execution\n",cases);
}
