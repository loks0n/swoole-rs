#include <cassert>
#include <cerrno>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <functional>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#include <sys/time.h>
#include "swoole_rs_hooks.h"
static std::vector<std::string> trace;
static void record(std::string value) { trace.push_back(value); }
#define SW_EVENT_NULL 0u
#define SW_EVENT_READ (1u<<9)
#define SW_EVENT_WRITE (1u<<10)
#define SW_EVENT_RDWR (SW_EVENT_READ|SW_EVENT_WRITE)
#define SW_ERROR_CO_SOCKET_CLOSE_WAIT 1777
#define SW_TIMER_MIN_SEC .001
#define sw_unlikely(value) (value)
#define SW_ASSERT_1BYTE(value) record("assert-byte:"+std::to_string(value))
#define INLINE_FILE "original-inline.inc"
#define METHODS_FILE "original-methods.inc"
namespace original {
#include "socket_policy_fixture.h"
}
#undef INLINE_FILE
#undef METHODS_FILE
#define INLINE_FILE "selected-inline.inc"
#define METHODS_FILE "selected-methods.inc"
namespace selected {
#include "socket_policy_fixture.h"
}
#define CASES(NS) \
static std::vector<std::string> run_##NS(int scenario) { \
 using namespace NS;trace.clear();closed=false;now=1;diagnostic=nullptr;last_error=0;errno=0;Socket socket;Coroutine reader{5},writer{7};uint32_t masks[]={0,SW_EVENT_READ,SW_EVENT_WRITE,SW_EVENT_READ|SW_EVENT_WRITE,1u<<11,UINT32_MAX}; \
 if(scenario<72){int k=scenario;int bound=(k/6)%4;reader.cid=(k/24)==0?0:(k/24)==1?5:-5;writer.cid=(k/24)==0?0:(k/24)==1?7:-7;socket.read_co=bound&1?&reader:nullptr;socket.write_co=bound&2?&writer:nullptr;auto event=masks[k%6];auto *result=socket.get_bound_co(event);record("bound:"+std::to_string(result==&reader?1:result==&writer?2:0));record("bound-cid:"+std::to_string(socket.get_bound_cid(event)));record(std::string("event:")+socket.get_event_str(event));socket.check_bound_co(event);} \
 if(scenario>=72 && scenario<288){int k=scenario-72;int bound=(k/6)%4;int state=(k/24)%3;int mode=k/72;socket.read_co=bound&1?&reader:nullptr;socket.write_co=bound&2?&writer:nullptr;closed=state==1;socket.socket=closed?nullptr:&socket.native;socket.native.close_wait=state==2;if(mode==1)diagnostic=[&](){closed=true;socket.socket=nullptr;record("diagnostic:close");};if(mode==2)diagnostic=[](){throw std::runtime_error("native-diagnostic");};try{record("available:"+std::to_string(socket.is_available(masks[k%6])));}catch(const std::runtime_error &){record("diagnostic:exception");}record("error:"+std::to_string(socket.errCode));record("errno:"+std::to_string(errno));record("last:"+std::to_string(last_error));} \
 if(scenario>=288 && scenario<324){int k=scenario-288;int64_t values[]={INT64_MIN,-1,0,INT64_MAX};int errors[]={0,9,-9};int system_errors[]={0,EINVAL,EAGAIN};socket.errCode=errors[(k/4)%3];errno=system_errors[k/12];socket.check_return_value(values[k%4]);record("error:"+std::to_string(socket.errCode));record("errno:"+std::to_string(errno));record("last:"+std::to_string(last_error));record(std::string("message:")+socket.errMsg);} \
 if(scenario>=324 && scenario<348){int k=scenario-324;time_t seconds[]={-1,0,1,9007199254740993LL};suseconds_t micros[]={-1,0,1,999999,1000000,std::numeric_limits<suseconds_t>::max()};timeval timeout{seconds[k%4],micros[k/4]};socket.set_timeout(&timeout,SW_TIMEOUT_READ);} \
 if(scenario>=348 && scenario<420){int k=scenario-348;double timeouts[]={-1,0,.001,1,std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity()};double starts[]={0,-0.0,1,2};now=1+(k/24)*2;Socket::TimeoutController timer{&socket,timeouts[k%6],starts[(k/6)%4]};for(int step=0;step<3;++step){record("expired:"+std::to_string(timer.has_timedout(SW_TIMEOUT_READ)));record("startup:"+number(timer.startup_time));now+=.5;}} \
 return trace;}
CASES(original)
CASES(selected)
int main() {
 // Initialize the native C++ exception runtime before comparing either variant.
 try { throw std::runtime_error("exception-runtime-setup"); } catch (const std::runtime_error &) {}
 for(int scenario=0;scenario<420;++scenario) {
    auto a=run_original(scenario),b=run_selected(scenario);
    if(a!=b) { std::fprintf(stderr,"socket inline mismatch %d\n",scenario);for(auto &line:a)std::fprintf(stderr,"original %s\n",line.c_str());for(auto &line:b)std::fprintf(stderr,"selected %s\n",line.c_str());return 1; }
 }
 std::puts("420 actual pinned/selected Socket inline and timeout native-facade scenarios passed");
}
