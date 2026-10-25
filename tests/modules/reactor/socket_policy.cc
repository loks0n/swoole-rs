#include <cassert>
#include <cerrno>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <vector>
#include <poll.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include "swoole_rs_reactor.h"
#define SW_OK 0
#define SW_ERR -1
#define SW_WAIT 2
#define SW_CLOSE 3
#define SW_ERROR 4
#define SW_INVALID 6
#define SW_ERROR_SSL_BAD_CLIENT 1015
#define SW_ERROR_SSL_RESET 1017
#define SW_ERROR_SOCKET_POLL_TIMEOUT 6002
#define swoole_sys_warning(...) std::abort()
#define swoole_set_last_error(...) std::abort()
static unsigned polls=0;static int observed_timeout=0,observed_events=0;
extern "C" int poll(pollfd *event,nfds_t count,int timeout){assert(count==1&&event->fd==17);++polls;observed_timeout=timeout;observed_events=event->events;return 1;}
namespace swoole {
static void swoole_signal_dispatch(){std::abort();}
static int16_t translate_events_to_poll(int events){return ((events&512)?POLLIN:0)|((events&1024)?POLLOUT:0);}
struct Socket{
 int fd=17;bool dont_restart=false,kernel_nobufs=false,tcp_nopush=false,tcp_nodelay=false,enable_tcp_nodelay=false;std::vector<int>options,values;
 int set_option(int level,int option,int value){assert(level==IPPROTO_TCP);options.push_back(option);values.push_back(value);return 0;}
 int wait_event(int,int)const;int catch_error(int);int set_tcp_nopush(int);bool set_tcp_nodelay(int);bool cork();bool uncork();
};
#include "socket_policy.inc"
}
int main(){using namespace swoole;unsigned checks=0,cases=0,effects=0;auto check=[&](bool value){assert(value);++checks;};
for(int timeout:{-9,-1,1,83})for(int events:{512,1024,1536})for(bool restart:{false,true}){Socket s;s.dont_restart=restart;polls=0;check(s.wait_event(timeout,events)==SW_OK);check(polls==1);check(observed_timeout==(timeout<0?-1:timeout));check(observed_events==translate_events_to_poll(events));check(s.options.empty()&&s.dont_restart==restart&&!s.kernel_nobufs);effects+=polls;++cases;}
{Socket s;check(s.catch_error(0)==SW_WAIT);check(!s.kernel_nobufs&&s.options.empty());++cases;}
for(int value:{0,1}){Socket s;check(s.set_tcp_nodelay(value));check(s.tcp_nodelay==bool(value));check(s.options==std::vector<int>{TCP_NODELAY}&&s.values==std::vector<int>{value});effects+=s.options.size();++cases;}
for(int value:{0,1}){Socket s;
#ifdef TCP_CORK
 check(s.set_tcp_nopush(value)==0);check(s.tcp_nopush==bool(value));check(s.options==std::vector<int>{TCP_CORK}&&s.values==std::vector<int>{value});
#else
 check(s.set_tcp_nopush(value)==-1);check(!s.tcp_nopush);check(s.options.empty());
#endif
 effects+=s.options.size();++cases;}
for(bool restore:{false,true})for(bool push:{false,true})for(bool nodelay:{false,true})for(bool enable:{false,true}){Socket s;s.tcp_nopush=push;s.tcp_nodelay=nodelay;s.enable_tcp_nodelay=enable;bool result=restore?s.uncork():s.cork();check(result==(restore?push:!push));check(s.enable_tcp_nodelay==enable&&!s.kernel_nobufs&&!s.dont_restart);std::vector<int>options,values;
 if(restore?push:!push){
#ifdef TCP_CORK
 options.push_back(TCP_CORK);values.push_back(restore?0:1);
#endif
 if(restore?(enable&&!nodelay):nodelay){options.push_back(TCP_NODELAY);values.push_back(restore?1:0);}
 }
 check(s.options==options&&s.values==values);
#ifdef TCP_CORK
 check(s.tcp_nopush==(result?!restore:push));
#else
 check(s.tcp_nopush==push);
#endif
 check(s.tcp_nodelay==(result?(restore?(enable||nodelay):false):nodelay));effects+=s.options.size();++cases;}
std::cout<<"{\"cases\":"<<cases<<",\"checks\":"<<checks<<",\"effects\":"<<effects<<",\"positive_only\":true,\"tcp_cork_available\":"
#ifdef TCP_CORK
 <<"true"
#else
 <<"false"
#endif
 <<"}\n";
}
