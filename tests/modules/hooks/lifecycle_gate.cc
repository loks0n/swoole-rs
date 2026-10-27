#include <cassert>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <functional>
#include <string>
#include <stdexcept>
#include <vector>
#include <sys/socket.h>
#include "swoole_rs_hooks.h"
static std::vector<std::string> trace;
static void record(std::string value){trace.push_back(value);}
static std::function<int(int,int)> shutdown_syscall;
static std::function<int(int)> connect_syscall;
static int fixture_shutdown(int fd,int how){record("shutdown:"+std::to_string(fd)+":"+std::to_string(how));return shutdown_syscall(fd,how);}
static int fixture_connect(int fd,const sockaddr*,socklen_t length){record("connect:"+std::to_string(fd)+":"+std::to_string(length));return connect_syscall(fd);}
#define shutdown fixture_shutdown
#define connect fixture_connect
#define SW_BAD_SOCKET -1
#define SW_EVENT_NULL 0u
#define SW_EVENT_READ 512u
#define SW_EVENT_WRITE 1024u
#define SW_EVENT_RDWR (SW_EVENT_READ|SW_EVENT_WRITE)
#define SW_ERROR_CO_SOCKET_CLOSE_WAIT 1777
#define sw_unlikely(value) (value)
#define ACTUAL_INLINE "original-lifecycle-inline.inc"
#define ACTUAL_BODIES "original-lifecycle.inc"
namespace original {
#include "lifecycle_fixture.h"
}
#undef ACTUAL_INLINE
#undef ACTUAL_BODIES
#define ACTUAL_INLINE "selected-lifecycle-inline.inc"
#define ACTUAL_BODIES "selected-lifecycle.inc"
#define SELECTED_STATE
namespace selected {
#include "lifecycle_fixture.h"
}
#undef SELECTED_STATE
#define CASES(NS) \
static std::vector<std::string> run_##NS(int scenario){using namespace NS;trace.clear();errno=0;last_error=0;ssl_error=0;shutdown_result=0;shutdown_error=-1;option_mode=0;probe_error=0;timer_ok=wake_ok=probe_ok=true;close_on_wait=throw_wait=false;connect_results={0};connect_index=0;Coroutine reader{0,{}},writer{7,{}},alternate{11,{}};Socket *socket=new Socket;bool alive=true; \
 shutdown_syscall=[](int,int){if(shutdown_error>=0)errno=shutdown_error;return shutdown_result;};connect_syscall=[](int){int value=connect_results.at(connect_index++);if(value<0){errno=-value;return -1;}return value;}; \
 if(scenario<512){int k=scenario;int hows[]={SHUT_RD,SHUT_WR,SHUT_RDWR,77};set_state(socket,(k/4)%2,(k/16)%2,(k/32)%2);socket->sock_fd=(k/8)%2?SW_BAD_SOCKET:77;socket->native.ssl=(k/64)%2?(void*)1:nullptr;ssl_error=EIO;int mode=k/128;shutdown_result=mode==1||mode==2?-1:0;shutdown_error=mode==1||mode==3?ENOTCONN:mode==2?EINVAL:-1;record("result:"+std::to_string(socket->shutdown(hows[k%4])));} \
 else if(scenario<608){int k=scenario-512;uint32_t events[]={0,SW_EVENT_READ,SW_EVENT_WRITE,SW_EVENT_RDWR,SW_EVENT_READ|(1u<<11),SW_EVENT_WRITE|(1u<<11),1u<<31,UINT32_MAX};int bindings=(k/8)%4;socket->read_co=bindings&1?&reader:nullptr;socket->write_co=bindings&2?&writer:nullptr;int mode=k/32;reader.callback=[&](){if(mode==1)socket->read_co=nullptr;if(mode==2){delete socket;alive=false;}};writer.callback=[&](){if(mode==1)socket->write_co=nullptr;if(mode==2){delete socket;alive=false;}};record("result:"+std::to_string(socket->cancel(events[k%8])));} \
 else if(scenario<752){int k=scenario-608;socket->sock_fd=k&1?SW_BAD_SOCKET:77;set_state(socket,k&2,false,false);int bindings=(k/4)%4;socket->read_co=bindings&1?&reader:nullptr;socket->write_co=bindings&2?&writer:nullptr;int mode=(k/16)%3,dtor=k/48;reader.callback=[&](){if(mode)socket->read_co=nullptr;};alternate.callback=[&](){socket->read_co=nullptr;};writer.callback=[&](){if(mode==1)socket->write_co=nullptr;if(mode==2){socket->write_co=nullptr;socket->read_co=&alternate;}};socket->dtor_=[&](Socket *owner){record("dtor:"+std::to_string(owner->sock_fd)+":"+std::to_string(owner->dtor_!=nullptr));if(dtor==1)record("reenter:"+std::to_string(owner->close()));if(dtor==2){delete owner;alive=false;}};record("result:"+std::to_string(socket->close()));if(alive && mode && !socket->has_bound() && socket->sock_fd!=SW_BAD_SOCKET)record("close-again:"+std::to_string(socket->close()));} \
 else if(scenario<1232){int k=scenario-752;std::vector<std::vector<int>> results={{0},{-EINTR,0},{-EINPROGRESS},{-EINVAL},{-EINTR,-EINPROGRESS}};connect_results=results[k%5];timer_ok=(k/5)%2;wake_ok=(k/10)%2;close_on_wait=(k/20)%2;option_mode=(k/40)%4;int admission=k/160;if(admission==1)socket->sock_fd=SW_BAD_SOCKET;if(admission==2)socket->native.close_wait=true;sockaddr address{};record("result:"+std::to_string(socket->connect(&address,sizeof(address))));} \
 else if(scenario<1244){int k=scenario-1232;socket->sock_fd=k&1?SW_BAD_SOCKET:77;probe_ok=k&2;int errors[]={0,EIO,ECONNRESET};probe_error=errors[k/4];record("result:"+std::to_string(socket->check_liveness()));} \
 if(scenario>=1244){int k=scenario-1244;try{if(k==0){socket->dtor_=[](Socket*){record("dtor:throw");throw std::runtime_error("native-dtor");};socket->close();}else if(k<=3){socket->read_co=&reader;socket->write_co=&writer;reader.callback=[](){throw std::runtime_error("native-resume");};writer.callback=reader.callback;if(k==3)socket->close();else socket->cancel(k==1?SW_EVENT_READ:SW_EVENT_WRITE);}else{connect_results={-EINPROGRESS};throw_wait=true;sockaddr address{};socket->connect(&address,sizeof(address));}record("unexpected:no-exception");}catch(const std::runtime_error &){record("native:exception");}} \
 record("alive:"+std::to_string(alive));record("errno:"+std::to_string(errno));record("last:"+std::to_string(last_error));if(alive){record("state:"+std::to_string(socket->sock_fd)+":"+std::to_string(state_of(socket).connected)+":"+std::to_string(state_of(socket).read)+":"+std::to_string(state_of(socket).write)+":"+std::to_string(socket->errCode)+":"+std::to_string(socket->native.close_wait));record("bound:"+std::to_string(socket->read_co==&reader?1:socket->read_co==&alternate?2:0)+":"+std::to_string(socket->write_co==&writer));delete socket;}return trace;}
CASES(original)
CASES(selected)
int main(){try{throw std::runtime_error("exception-runtime-setup");}catch(const std::runtime_error &){}for(int scenario=0;scenario<1249;++scenario){auto a=run_original(scenario),b=run_selected(scenario);if(a!=b){std::fprintf(stderr,"lifecycle mismatch %d\n",scenario);for(auto &line:a)std::fprintf(stderr,"original %s\n",line.c_str());for(auto &line:b)std::fprintf(stderr,"selected %s\n",line.c_str());return 1;}}std::puts("1249 actual pinned/selected Socket lifecycle/connection native-facade scenarios passed");}
