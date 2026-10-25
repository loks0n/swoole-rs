#include <algorithm>
#include <cassert>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <functional>
#include <iostream>
#include <string>
#include <sys/socket.h>
#include "swoole_rs_reactor.h"
#define SW_READY 5
#define SW_ERROR 4
#define SW_CONTINUE 1
#define SW_WAIT 2
#define SW_EVENT_READ 512
#define SW_EVENT_WRITE 1024
#define SW_SOCKET_RETRY_COUNT 10
#define SW_LOOP_N(n) for (size_t i=0;i<(n);++i)
#define swoole_set_last_error(...) std::abort()
struct Scenario {
 std::string input,output;size_t piece=1;unsigned sends=0,receives=0,waits=0;int expected_event=0,expected_flags=0;
 const sockaddr *address=nullptr;sockaddr *receive_address=nullptr;socklen_t *receive_length=nullptr;
}scenario;
extern "C" ssize_t recvfrom(int fd,void *data,size_t length,int flags,sockaddr *address,socklen_t *address_length){
 assert(fd==17&&length>0&&flags==scenario.expected_flags&&address==scenario.receive_address&&address_length==scenario.receive_length);
 ++scenario.receives;size_t n=std::min(length,scenario.piece);assert(n<=scenario.input.size());std::memcpy(data,scenario.input.data(),n);address->sa_family=AF_UNIX;*address_length=sizeof(sockaddr);return n;
}
namespace swoole {
using ReturnCode=int;
struct Address {union {sockaddr ss;}addr; socklen_t len=sizeof(addr);};
struct Socket {
 int fd=17;double read_timeout=.125,write_timeout=.375;
 int catch_error(int){std::abort();}
 bool wait_for(const std::function<ReturnCode()>&fn,int event,int milliseconds){++scenario.waits;assert(event==scenario.expected_event);assert(milliseconds==(event==SW_EVENT_READ?125:375));int result=fn();assert(result==SW_READY);return true;}
 ssize_t sendto(const Address &address,const void *data,size_t length,int flags){assert(&address.addr.ss==scenario.address&&length>0&&flags==scenario.expected_flags);++scenario.sends;size_t n=std::min(length,scenario.piece);scenario.output.assign(static_cast<const char*>(data),n);return n;}
 ssize_t sendto_sync(const Address&,const void*,size_t,int);
 ssize_t recvfrom(char*,size_t,int,sockaddr*,socklen_t*)const;
 ssize_t recvfrom_sync(char*,size_t,int,Address*);
 ssize_t recvfrom_sync(char*,size_t,int,sockaddr*,socklen_t*);
};
#include "datagram.inc"
}
int main(){using namespace swoole;unsigned cases=0,checks=0;auto check=[&](bool v){assert(v);++checks;};std::string payload;for(unsigned i=0;i<47;++i)payload+=char(i);
 for(size_t length:{size_t(1),size_t(7),size_t(19)})for(size_t piece:{size_t(1),size_t(3),size_t(23)})for(int flags:{0,int(MSG_DONTWAIT)}){
  const size_t expected=std::min(length,piece);
  {scenario=Scenario();Socket socket;Address address;scenario.address=reinterpret_cast<sockaddr*>(&address.addr.ss);scenario.piece=piece;scenario.expected_flags=flags;scenario.expected_event=SW_EVENT_WRITE;
   check(socket.sendto_sync(address,payload.data(),length,flags)==ssize_t(expected));check(scenario.output==payload.substr(0,expected));check(scenario.sends==1&&scenario.receives==0);check(scenario.waits==1);check(socket.fd==17);++cases;}
  for(unsigned kind=0;kind<3;++kind){scenario=Scenario();Socket socket;Address address;char buffer[48]={};scenario.input=payload;scenario.piece=piece;scenario.expected_flags=flags;scenario.expected_event=SW_EVENT_READ;scenario.receive_address=reinterpret_cast<sockaddr*>(&address.addr.ss);scenario.receive_length=&address.len;
   ssize_t result=kind==0?socket.recvfrom(buffer,length,flags,scenario.receive_address,&address.len):kind==1?socket.recvfrom_sync(buffer,length,flags,scenario.receive_address,&address.len):socket.recvfrom_sync(buffer,length,flags,&address);
   check(result==ssize_t(expected));check(std::string(buffer,expected)==payload.substr(0,expected));check(scenario.receives==1&&scenario.sends==0);check(scenario.waits==unsigned(kind!=0));check(address.len==sizeof(sockaddr)&&scenario.receive_address->sa_family==AF_UNIX);check(socket.fd==17);++cases;
  }
 }
 std::cout<<"{\"cases\":"<<cases<<",\"checks\":"<<checks<<",\"positive_only\":true,\"network_effects\":false}\n";
}
