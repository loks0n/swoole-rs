// Complete source entry wrappers on inert metadata effects. No actual event,
// function/callback, Coroutine/Context object or exception is constructed/run.
#include "swoole_rs_coroutine.h"
#include <cassert>
#include <cstdlib>
#include <iostream>
#include <string>
#define sw_likely(x) (x)
#define SW_EVENTLOOP_WAIT_EXIT 17
using CoroutineFunc=void (*)(void *);
struct Facts {int available;long cid;std::string trace;};
static Facts facts;
static bool swoole_event_is_available(){facts.trace+='E';return facts.available;}
static int swoole_event_init(int flags){assert(flags==17);facts.trace+='I';return 0;}
static void swoole_event_wait(){facts.trace+='W';}
namespace swoole {
struct Coroutine {
 static void activate(){facts.trace+='A';}
 static void deactivate(){facts.trace+='D';}
 template<typename Function>static long create(const Function &,void *){facts.trace+='C';return facts.cid;}
};
#include "entry-driver.inc"
namespace coroutine {
#include "entry-run.inc"
}
}
#include "entry-create.inc"
int main(){
 for(int mode=0;mode<2;mode++)for(int available=0;available<2;available++)for(long cid:{0L,1L,7L,91L}){
  facts={available,cid,""};long result=mode==0?swoole::coroutine::run(nullptr,nullptr):swoole_coroutine_create(nullptr,nullptr);
  assert(result==(mode==0?(cid>0):cid));
  assert(facts.trace==(mode==0?"IACWD":available?"EC":"EIACWD"));
  std::cout<<mode<<':'<<available<<':'<<cid<<':'<<result<<':'<<facts.trace<<'\n';
 }
}
