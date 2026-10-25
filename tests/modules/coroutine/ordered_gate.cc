#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <functional>
#include <list>
#include <map>
#include <new>
#include <queue>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>
#include "swoole_rs_coroutine.h"
static std::vector<std::string> trace;
static int last_error;
static bool throw_on_copy=false;
struct CopyProbe {
    CopyProbe()=default;
    CopyProbe(const CopyProbe &) { if(throw_on_copy) throw std::bad_alloc(); }
    bool operator()(void *) const { return true; }
};
static void record(const std::string &value) { trace.push_back(value); }
#define SW_ASSERT(x) assert(x)
#define sw_likely(x) (x)
#define sw_unlikely(x) (x)
#define CALC_EXECUTE_USEC(a,b) record("time:"+std::to_string(([](Coroutine *p){return p?p->cid:-1;})(a))+":"+std::to_string(([](Coroutine *p){return p?p->cid:-1;})(b)))
#define swoole_trace_log(...) ((void)0)
#define SW_ERROR_CO_CANNOT_CANCEL 100
#define SW_ERROR_CO_TIMEDOUT 101
#define SW_ERROR_CO_CANCELED 102
static void swoole_set_last_error(int value) { last_error=value; record("error:"+std::to_string(value)); }

// Instantiate the same native facade independently around each set of actual
// bodies. Production header/layout compilation is a separate complete-TU gate.
#define FIXTURE(NS, INC) \
namespace NS { \
struct Timer {}; \
struct TimerNode { void *data; std::function<void(Timer *,TimerNode *)> callback; }; \
using TimerCallback=std::function<void(Timer *,TimerNode *)>; \
static TimerNode *pending=nullptr; static bool timer_failure=false; \
static TimerNode *swoole_timer_add(double, bool, const std::function<void(Timer *,TimerNode *)> &cb, void *data) { \
 record("timer:add"); if(timer_failure)return nullptr; assert(!pending); return pending=new TimerNode{data,cb}; } \
static void swoole_timer_del(TimerNode *node) { record("timer:delete"); assert(node==pending); pending=nullptr; delete node; } \
static void expire() { assert(pending); auto *node=pending;pending=nullptr;node->callback(nullptr,node);delete node; } \
struct Context { bool ended=false; std::function<void()> in,out; \
 bool is_end() const{return ended;} \
 void swap_in(){record("swap:in");if(in)in();} void swap_out(){record("swap:out");if(out)out();} }; \
struct Coroutine { \
 enum State { STATE_INIT, STATE_WAITING, STATE_RUNNING, STATE_END }; \
 enum ResumeCode { RC_OK=0, RC_TIMEDOUT=-1, RC_CANCELED=-2 }; \
 using CancelFunc=std::function<bool(Coroutine *)>; \
 static Coroutine *current; static std::unordered_map<long,Coroutine *> coroutines; \
 static std::function<void(void *)> on_yield,on_resume,on_close; static std::function<void()> on_bailout; \
 State state=STATE_INIT; ResumeCode resume_code_=RC_OK; long cid; Context ctx; \
 Coroutine *origin=nullptr; void *task=nullptr; CancelFunc *cancel_fn_=nullptr; \
 explicit Coroutine(long id=1):cid(id){coroutines[id]=this;} \
 ~Coroutine(){record("destroy:"+std::to_string(cid));} \
 long get_cid()const{return cid;} static Coroutine *get_current_safe(){assert(current);return current;} \
 bool is_canceled()const{return resume_code_==RC_CANCELED;} bool is_timedout()const{return resume_code_==RC_TIMEDOUT;} \
 void set_cancel_fn(CancelFunc *p){cancel_fn_=p;} \
 void check_end();long run();void yield();void yield(CancelFunc *);bool yield_ex(double timeout=-1); \
 void resume();bool cancel();void close(); \
}; \
Coroutine *Coroutine::current=nullptr; std::unordered_map<long,Coroutine *> Coroutine::coroutines; \
std::function<void(void *)> Coroutine::on_yield,Coroutine::on_resume,Coroutine::on_close;std::function<void()> Coroutine::on_bailout; \
struct Channel { \
 enum Opcode {PRODUCER=1,CONSUMER=2}; enum ErrorCode {ERROR_OK=0,ERROR_TIMEOUT=-1,ERROR_CLOSED=-2,ERROR_CANCELED=-3}; \
 struct TimeoutMessage {Channel *chan;Opcode type;Coroutine *co;bool error;TimerNode *timer;}; \
 size_t capacity=1; bool closed=false; int error_=0; \
 std::list<Coroutine *> producer_queue,consumer_queue; std::queue<void *> data_queue; \
 bool is_empty()const{return data_queue.empty();} bool is_full()const{return data_queue.size()==capacity;} size_t length()const{return data_queue.size();} \
 void consumer_remove(Coroutine *co){consumer_queue.remove(co);record("consumer:remove");} \
 void producer_remove(Coroutine *co){producer_queue.remove(co);record("producer:remove");} \
 Coroutine *pop_coroutine(Opcode type){ auto &q=type==PRODUCER?producer_queue:consumer_queue;auto *co=q.front();q.pop_front();record(type==PRODUCER?"producer:pop":"consumer:pop");return co;} \
 static void timer_callback(Timer *,TimerNode *);void yield(Opcode);void *pop(double timeout=-1);bool push(void *,double timeout=-1);bool close(); \
}; \
}
FIXTURE(original, original.inc)
FIXTURE(selected, selected.inc)
namespace original {
#include "original.inc"
}
namespace selected {
#include "selected.inc"
}

// Exercise the actual native code twice, using exactly the same scenario body.
#define SCENARIOS(NS) \
static std::vector<std::string> run_##NS(int scenario) { \
 using namespace NS; trace.clear();last_error=0;timer_failure=false;pending=nullptr; \
 Coroutine::coroutines.clear();Coroutine::current=nullptr; \
 Coroutine::on_yield=nullptr;Coroutine::on_resume=nullptr;Coroutine::on_close=nullptr;Coroutine::on_bailout=nullptr; \
 { Coroutine main(90);main.state=Coroutine::STATE_RUNNING;Coroutine::current=&main; \
 if(scenario<12 || scenario==25 || scenario==26){ \
  auto *co=new Coroutine(7);int task=7;co->task=&task; \
  auto callback=[&](void *){record("callback:"+std::to_string(co->state)+":"+std::to_string(co->resume_code_)+":"+std::to_string(Coroutine::current?Coroutine::current->cid:-1)+":"+std::to_string(Coroutine::coroutines.count(7)));}; \
  Coroutine::on_yield=callback;Coroutine::on_resume=callback;Coroutine::on_close=callback; \
  if(scenario==0){co->ctx.in=[&]{co->ctx.ended=true;};assert(co->run()==7);co=nullptr;} \
  if(scenario==1){co->resume();} \
  if(scenario==2){Coroutine::on_bailout=[]{};co->resume();} \
  if(scenario==3){Coroutine::current=co;co->origin=&main;co->yield();} \
  if(scenario==4){assert(!co->cancel());} \
  if(scenario==5){Coroutine::CancelFunc fn=[&](Coroutine *c){assert(!c->cancel_fn_);assert(c->is_canceled());record("cancel:called");return false;};co->set_cancel_fn(&fn);assert(!co->cancel());} \
  if(scenario==6||scenario==7||scenario==8){Coroutine::current=co;co->origin=&main;co->ctx.out=[&]{if(scenario==6)expire();if(scenario==7)co->cancel();};bool ok=co->yield_ex(2);record("yield-result:"+std::to_string(ok));} \
  if(scenario==9){Coroutine::on_close=[&](void *){callback(nullptr);throw std::runtime_error("close");};Coroutine::current=co;try{co->close();assert(false);}catch(const std::runtime_error&){record("throw:close");}} \
  if(scenario==10){Coroutine::on_resume=[&](void *){callback(nullptr);throw std::runtime_error("resume");};try{co->resume();assert(false);}catch(const std::runtime_error&){record("throw:resume");}} \
  if(scenario==11){Coroutine::on_yield=[&](void *){callback(nullptr);throw std::runtime_error("yield");};Coroutine::current=co;co->origin=&main;try{co->yield();assert(false);}catch(const std::runtime_error&){record("throw:yield");}} \
  if(scenario==25){Coroutine::CancelFunc fn=CopyProbe{};co->set_cancel_fn(&fn);throw_on_copy=true;try{co->cancel();assert(false);}catch(const std::bad_alloc&){assert(co->cancel_fn_==&fn);assert(co->resume_code_==Coroutine::RC_OK);record("copy:failure-before-mutation");}throw_on_copy=false;} \
  if(scenario==26){Coroutine::CancelFunc fn=[&](Coroutine *c){c->ctx.in=[c]{c->ctx.ended=true;};c->resume();record("cancel:returned-after-destruction");return true;};co->set_cancel_fn(&fn);assert(co->cancel());co=nullptr;} \
  if(co){Coroutine::coroutines.erase(co->cid);delete co;} \
 } else { \
  Channel ch;int value=17;Coroutine waiter(8);waiter.origin=&main; \
  if(scenario==12){assert(ch.push(&value));assert(ch.pop()==&value);} \
  if(scenario==13){ch.closed=true;ch.data_queue.push(&value);assert(ch.pop()==&value);assert(ch.pop()==nullptr);assert(!ch.push(&value));} \
  if(scenario>=14&&scenario<=19){ \
   bool push=scenario%2; \
   if(push)ch.data_queue.push(&value); \
   main.ctx.out=[&]{if(scenario<16){expire();}else if(scenario<18){main.cancel();}else{if(push)ch.data_queue.pop();else ch.data_queue.push(&value);}}; \
   bool result=push?ch.push(&value,2):(ch.pop(2)!=nullptr);record("channel-result:"+std::to_string(result)+":"+std::to_string(ch.error_)); \
  } \
  if(scenario==20||scenario==21){ \
   if(scenario==20)ch.consumer_queue.push_back(&waiter);else ch.producer_queue.push_back(&waiter); \
   if(scenario==20)ch.data_queue.push(&value); \
   main.ctx.out=[&]{record("fair:yield");if(scenario==20){ch.consumer_queue.clear();}else{ch.producer_queue.clear();}}; \
   if(scenario==20)assert(ch.pop()==&value);else assert(ch.push(&value)); \
  } \
  if(scenario==22){Coroutine consumer(9);consumer.origin=&main;ch.producer_queue.push_back(&waiter);ch.consumer_queue.push_back(&consumer);waiter.ctx.in=[&]{record("close:producer:"+std::to_string(ch.closed));};consumer.ctx.in=[&]{record("close:consumer:"+std::to_string(ch.closed));};assert(ch.close());assert(!ch.close());} \
  if(scenario==23){timer_failure=true;main.ctx.out=[&]{main.cancel();};assert(ch.pop(2)==nullptr);assert(ch.error_==Channel::ERROR_CANCELED);} \
  if(scenario==24){ch.error_=Channel::ERROR_TIMEOUT;assert(ch.push(&value));assert(ch.pop()==&value);assert(ch.error_==Channel::ERROR_TIMEOUT);} \
  record("channel-state:"+std::to_string(ch.closed)+":"+std::to_string(ch.error_)+":"+std::to_string(ch.data_queue.size())+":"+std::to_string(ch.producer_queue.size())+":"+std::to_string(ch.consumer_queue.size())); \
 } \
 Coroutine::coroutines.clear();Coroutine::current=nullptr; } \
 assert(pending==nullptr);return trace; }
SCENARIOS(original)
SCENARIOS(selected)
#define DELETE_SCENARIO(NS) \
static std::vector<std::string> delete_##NS(bool pop) { \
 using namespace NS;trace.clear();Coroutine::coroutines.clear();Coroutine::on_bailout=nullptr; \
 Coroutine::on_yield=nullptr;Coroutine::on_resume=nullptr;Coroutine::on_close=nullptr; \
 Coroutine main(90),waiter(8);Coroutine::current=&main; \
 auto *channel=new Channel;int value=17; \
 if(pop){channel->data_queue.push(&value);channel->producer_queue.push_back(&waiter);}else channel->consumer_queue.push_back(&waiter); \
 waiter.ctx.in=[&]{record("waiter:delete-channel");delete channel;channel=nullptr;Coroutine::current=&main;}; \
 if(pop){assert(channel->pop()==&value);}else{assert(channel->push(&value));} \
 assert(channel==nullptr);record("returned-after-channel-deletion"); \
 Coroutine::current=nullptr;Coroutine::coroutines.clear();return trace; }
DELETE_SCENARIO(original)
DELETE_SCENARIO(selected)
int main(){for(bool pop:{false,true}){auto a=delete_original(pop),b=delete_selected(pop);assert(a==b);}for(int s=0;s<27;s++){auto a=run_original(s),b=run_selected(s);if(a!=b){fprintf(stderr,"scenario%d mismatch\n",s);for(auto &v:a)fprintf(stderr,"original %s\n",v.c_str());for(auto &v:b)fprintf(stderr,"selected %s\n",v.c_str());return 1;}}puts("29 actual-body ordered scheduler/channel scenarios match");}
