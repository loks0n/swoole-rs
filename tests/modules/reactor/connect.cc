#include <cassert>
#include <cerrno>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>
#include <sys/socket.h>
#include "swoole_rs_reactor.h"
namespace swoole {
enum swReturnCode {SW_WAIT=2,SW_ERROR=4,SW_READY=5};
enum {SW_OK=0,SW_ERR=-1,SW_EVENT_WRITE=1<<10};
struct Address {int id=7;};
static std::vector<std::string> trace;
static void swoole_set_last_error(int) {std::abort();} // no error effect may execute
struct Timeout {
 double value=0;
 operator double()const {trace.push_back("timeout");return value;}
};
struct Socket {
 Timeout connect_timeout;bool nonblock=false;swReturnCode callee=SW_READY;int expected_timeout=0;
 bool set_nonblock(){trace.push_back("nonblock");nonblock=true;return true;}
 bool set_block(){trace.push_back("block");nonblock=false;return true;}
 int connect(const Address &sa){assert(sa.id==7);trace.push_back("connect");return 0;}
 swReturnCode fixture_connect_async(const Address &sa){assert(sa.id==7);trace.push_back("async");return callee;}
 int wait_event(int timeout,int event){assert(timeout==expected_timeout&&event==SW_EVENT_WRITE);trace.push_back("wait");return 0;}
 int get_option(int level,int name,void *error,socklen_t *length){assert(level==SOL_SOCKET&&name==SO_ERROR&&*length==sizeof(socklen_t));trace.push_back("option");*static_cast<int*>(error)=0;return 0;}
 swReturnCode connect_async(const Address&);int connect_sync(const Address&);
};
#include "connect.inc"
}
int main(){using namespace swoole;unsigned checks=0,cases=0;auto check=[&](bool condition){assert(condition);++checks;};Address address;
for(bool initial:{false,true}){Socket socket;socket.nonblock=initial;trace.clear();errno=0;
 check(socket.connect_async(address)==SW_READY);check(trace==std::vector<std::string>{"nonblock","connect"});check(socket.nonblock);check(errno==0);++cases;
}
for(bool initial:{false,true})for(double timeout:{-1.0,0.0,0.25,1.75})for(swReturnCode callee:{SW_READY,SW_WAIT}){Socket socket;socket.nonblock=initial;socket.connect_timeout.value=timeout;socket.callee=callee;socket.expected_timeout=timeout>0?static_cast<long>(timeout*1000):timeout;trace.clear();errno=0;
 check(socket.connect_sync(address)==SW_OK);
 const auto expected=callee==SW_READY?std::vector<std::string>{"async"}:std::vector<std::string>{"async","timeout","wait","option","block"};
 check(trace==expected);check(socket.nonblock==(callee==SW_READY?initial:false));check(socket.connect_timeout.value==timeout);check(errno==0);++cases;
}
std::cout<<"{\"cases\":"<<cases<<",\"checks\":"<<checks<<",\"inert_positive_only\":true,\"sync_callee_adapter\":true,\"native_network_effects\":false,\"native_error_effects\":false}\n";
}
