#include <algorithm>
#include <cassert>
#include <cerrno>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <functional>
#include <iostream>
#include <string>
#include <vector>
#include <sys/socket.h>
#include <sys/uio.h>
#include "swoole_rs_reactor.h"
#define SW_READY 5
#define SW_ERROR 4
#define SW_CONTINUE 1
#define SW_WAIT 2
#define SW_EVENT_READ 512
#define SW_EVENT_WRITE 1024
#define SW_TRACE_SOCKET 1
#define swoole_trace_log(...) (++scenario.traces)
#define swoole_set_last_error(...) std::abort()
struct Scenario {
 std::string input,output;size_t piece=1,offset=0;unsigned calls=0,traces=0,updates=0,clocks=0;std::vector<int>flags;
 ssize_t put(const void *data,size_t length,int flag){assert(length>0);++calls;flags.push_back(flag);auto n=std::min(piece,length);output.append(static_cast<const char*>(data),n);return n;}
 ssize_t get(void *data,size_t length,int flag){assert(length>0);++calls;flags.push_back(flag);auto n=std::min(piece,length);assert(offset+n<=input.size());std::memcpy(data,input.data()+offset,n);if(!(flag&MSG_PEEK))offset+=n;return n;}
}scenario;
extern "C" ssize_t send(int,const void *data,size_t length,int flags){return scenario.put(data,length,flags);}
extern "C" ssize_t recv(int,void *data,size_t length,int flags){return scenario.get(data,length,flags);}
extern "C" ssize_t readv(int,const iovec *iov,int count){assert(count==1);return scenario.get(iov[0].iov_base,iov[0].iov_len,0);}
extern "C" ssize_t writev(int,const iovec *iov,int count){assert(count==1);return scenario.put(iov[0].iov_base,iov[0].iov_len,0);}
static int SSL_peek(void*,void *data,int length){return scenario.get(data,length,MSG_PEEK);}
namespace swoole {
using ReturnCode=int;
template<class Unit> static uint64_t time(bool){++scenario.clocks;return 71;}
struct IOVector{ iovec value;explicit IOVector(iovec v):value(v){}iovec *get_iterator(){return &value;}int get_remain_count(){return 1;}void update_iterator(ssize_t n){assert(n>0);++scenario.updates;} };
struct Socket{
 int fd=17;void *ssl=nullptr;bool nonblock=false,dont_restart=false,event_hup=false;void *send_timer=nullptr,*recv_timer=nullptr;uint64_t total_send_bytes=2,total_recv_bytes=3,last_sent_time=5,last_received_time=7;double read_timeout=1,write_timeout=1;
 ssize_t ssl_send(const void *data,size_t length){return scenario.put(data,length,0);}
 ssize_t ssl_recv(void *data,size_t length){return scenario.get(data,length,0);}
 ssize_t ssl_readv(IOVector *v){return scenario.get(v->value.iov_base,v->value.iov_len,0);}
 ssize_t ssl_writev(IOVector *v){return scenario.put(v->value.iov_base,v->value.iov_len,0);}
 ssize_t read(void *data,size_t length){return scenario.get(data,length,0);}ssize_t write(const void *data,size_t length){return scenario.put(data,length,0);}
 int catch_read_error(int){std::abort();}int catch_error(int){std::abort();}
 bool wait_for(const std::function<ReturnCode()>&fn,int,int){return fn()==SW_READY;}
 ssize_t send(const void*,size_t,int);ssize_t recv(void*,size_t,int);ssize_t peek(void*,size_t,int)const;ssize_t readv(IOVector*);ssize_t writev(IOVector*);ssize_t read_sync(void*,size_t);ssize_t write_sync(const void*,size_t);
};
#include "ordinary_io.inc"
}
int main(){using namespace swoole;unsigned cases=0,checks=0;uint64_t effects=0;auto check=[&](bool value){assert(value);++checks;};std::string payload;for(unsigned i=0;i<47;++i)payload+=static_cast<char>(i);
for(size_t length:{size_t(1),size_t(7),size_t(13)})for(size_t piece:{size_t(1),size_t(3),size_t(17)})for(bool tls:{false,true})for(bool timer:{false,true}){
 scenario=Scenario();scenario.piece=piece;Socket s;s.ssl=tls?&s:nullptr;s.send_timer=timer?&s:nullptr;size_t n=std::min(piece,length);
 check(s.send(payload.data(),length,0)==static_cast<ssize_t>(n));check(scenario.output==payload.substr(0,n));check(s.total_send_bytes==2+n&&s.total_recv_bytes==3);check(s.last_sent_time==(timer?71:5)&&s.last_received_time==7);check(scenario.calls==1&&scenario.traces==1&&scenario.clocks==unsigned(timer));effects+=scenario.calls+scenario.clocks;check(!s.nonblock&&!s.dont_restart&&!s.event_hup);++cases;
 for(bool nonblock:{false,true})for(bool waitall:{false,true}){
  scenario=Scenario();scenario.piece=piece;scenario.input=payload;Socket r;r.ssl=tls?&r:nullptr;r.nonblock=nonblock;r.recv_timer=timer?&r:nullptr;std::string bytes(length,'x');size_t expected=tls&&(nonblock||waitall)?length:n;
  check(r.recv(&bytes[0],length,waitall?MSG_WAITALL:0)==static_cast<ssize_t>(expected));check(bytes.substr(0,expected)==payload.substr(0,expected));check(r.total_recv_bytes==3+expected&&r.total_send_bytes==2);check(r.last_received_time==(timer?71:7)&&r.last_sent_time==5);check(scenario.calls==(tls&&(nonblock||waitall)?(length+piece-1)/piece:1));check(scenario.offset==expected);check(scenario.traces==1&&scenario.clocks==unsigned(timer));check(r.nonblock==nonblock&&!r.dont_restart&&!r.event_hup);effects+=scenario.calls+scenario.clocks;++cases;
 }
 scenario=Scenario();scenario.piece=piece;scenario.input=payload;Socket p;p.ssl=tls?&p:nullptr;std::string bytes(length,'x');check(p.peek(&bytes[0],length,0)==static_cast<ssize_t>(n));check(bytes.substr(0,n)==payload.substr(0,n));check(scenario.offset==0&&scenario.calls==1&&scenario.traces==1);check(p.total_send_bytes==2&&p.total_recv_bytes==3&&scenario.clocks==0);check(scenario.flags[0]==MSG_PEEK);effects+=scenario.calls;++cases;
 for(bool writing:{false,true}){scenario=Scenario();scenario.piece=piece;scenario.input=payload;Socket v;v.ssl=tls?&v:nullptr;std::string data=writing?payload.substr(0,length):std::string(length,'x');IOVector iov({&data[0],length});check((writing?v.writev(&iov):v.readv(&iov))==static_cast<ssize_t>(n));check(writing?scenario.output==payload.substr(0,n):data.substr(0,n)==payload.substr(0,n));check(scenario.calls==1&&scenario.updates==unsigned(!tls));check(scenario.traces==0&&scenario.clocks==0);check(v.total_send_bytes==2&&v.total_recv_bytes==3);effects+=scenario.calls;++cases;}
 for(bool writing:{false,true}){scenario=Scenario();scenario.piece=piece;scenario.input=payload;Socket v;std::string data=writing?payload.substr(0,length):std::string(length,'x');check((writing?v.write_sync(data.data(),length):v.read_sync(&data[0],length))==static_cast<ssize_t>(n));check(writing?scenario.output==payload.substr(0,n):data.substr(0,n)==payload.substr(0,n));check(scenario.calls==1&&scenario.updates==0);check(scenario.traces==0&&scenario.clocks==0);check(v.total_send_bytes==2&&v.total_recv_bytes==3);effects+=scenario.calls;++cases;}
}
std::cout<<"{\"cases\":"<<cases<<",\"checks\":"<<checks<<",\"effects\":"<<effects<<",\"positive_only\":true}\n";
}
