// Inert native initialization effects; no actual reactor or user callback.
#include "swoole_rs_wrappers.h"
#include <cassert>
#include <climits>
#include <cstdint>
#include <cstdio>
#include <sstream>
#include <string>
#include <vector>
#include "flags.inc"
constexpr int SW_OK=0,SW_ERR=-1,SW_REACTOR_MAXEVENTS=4096;
static std::ostringstream trace;
struct Flag {bool value=false;Flag &operator=(bool next){trace<<"wait:"<<next<<';';value=next;return *this;}};
struct Reactor;
static Reactor *created=nullptr,*anchor=nullptr;
static unsigned mutation=0;
struct Reactor {
    Flag wait_exit;
    explicit Reactor(int events){created=this;trace<<"new:"<<events<<';';}
    bool ready(){trace<<"ready;";return true;}
};
static struct {Reactor *reactor=nullptr;} SwooleTG;
static void initialize(Reactor *reactor,unsigned kind){
    trace<<"init:"<<kind<<":same:"<<(reactor==created)<<":published:"<<(SwooleTG.reactor==reactor)<<":wait:"<<reactor->wait_exit.value<<';';
    if(mutation&1)SwooleTG.reactor=anchor;
    if(mutation&2)reactor->wait_exit.value=kind&1;
}
namespace swoole {
namespace coroutine {
struct Socket {static void init_reactor(Reactor *reactor){initialize(reactor,1);}};
struct System {static void init_reactor(Reactor *reactor){initialize(reactor,2);}};
}
namespace network {struct Client {static void init_reactor(Reactor *reactor){initialize(reactor,3);}};}
}
namespace Original {
#include "original.inc"
}
namespace Selected {
#include "selected.inc"
}
static std::string run(bool selected,int flags,unsigned mode){
    Reactor prior(0);anchor=&prior;created=nullptr;mutation=mode;SwooleTG.reactor=nullptr;trace.str("");trace.clear();
    int result=selected?Selected::swoole_event_init(flags):Original::swoole_event_init(flags);
    assert(created&&result==SW_OK);
    trace<<"return:"<<result<<":published:"<<(SwooleTG.reactor==created)<<":wait:"<<created->wait_exit.value<<';';
    SwooleTG.reactor=nullptr;delete created;created=nullptr;return trace.str();
}
int main(){
    static_assert(sizeof(SwrWrapperEventInit)==20&&offsetof(SwrWrapperEventInit,initializers)==8,"event-init ABI");
    static_assert(sizeof(int)==sizeof(int32_t),"native int flag ABI");
    std::vector<int>flags={0,1,2,3,-1,INT_MIN,INT_MAX};uint32_t seed=0x3193ea;
    for(unsigned n=0;n<4096;n++){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;flags.push_back(static_cast<int32_t>(seed));}
    size_t cases=0;
    for(int value:flags)for(unsigned mode=0;mode<4;mode++){
        auto expected=run(false,value,mode),actual=run(true,value,mode);
        if(expected!=actual){fprintf(stderr,"event-init ordering mismatch flags=%d mode=%u\n",value,mode);return 1;}cases++;
    }
    for(uint32_t mask:{0u,1u,2u,3u})for(uint32_t value:{0u,1u,UINT32_MAX}){
        auto no=swr_v1_wrappers_event_init(value,mask,0);assert(!no.accepted&&!no.wait_exit&&!no.initializers[0]&&!no.initializers[1]&&!no.initializers[2]);cases++;
        auto yes=swr_v1_wrappers_event_init(value,mask,2);assert(yes.accepted==1&&yes.wait_exit==bool(value&mask)&&yes.initializers[0]==SWR_WRAPPER_INIT_SOCKET&&yes.initializers[1]==SWR_WRAPPER_INIT_SYSTEM&&yes.initializers[2]==SWR_WRAPPER_INIT_CLIENT);cases++;
    }
    printf("%zu normal event-init effect ordering and candidate-only plan comparisons passed; no actual reactor\n",cases);
}
