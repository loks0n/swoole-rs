#include <algorithm>
#include <cassert>
#include <cerrno>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <iostream>
#include <limits>
#include <string>
#include <vector>
#include <sys/types.h>
#include <sys/uio.h>
#include <sys/socket.h>
#include <cstring>
#include "swoole_rs_reactor.h"
#define SW_OK 0
#define SW_ERR -1
#define SW_WAIT 2
#define SW_CLOSE 3
#define SW_ERROR 4
#define SW_READY 5
#define SW_CONTINUE 1
#define SW_EVENT_READ 512
#define SW_EVENT_WRITE 1024
#define SW_SOCKET_CORK_MIN_SIZE 8
#define SW_SENDFILE_CHUNK_SIZE 7
#define SW_LOG_WARNING 1
#define SW_ERROR_FILE_EMPTY 1
#define SW_ERROR_INVALID_PARAMS 2
#define SW_TRACE_CLIENT 1
#define O_RDONLY 0
#define swoole_sys_warning(...) std::abort()
#define swoole_error_log(...) std::abort()
#define swoole_set_last_error(...) std::abort()
#define swoole_trace_log(...) ((void)0)
#define usleep(...) std::abort()
namespace swoole {
using ReturnCode=int;
static double clock_value=0;
static unsigned clocks=0;
static double microtime(){++clocks;clock_value+=0.001;return clock_value;}
struct FileStatus{off_t st_size;};
struct File{std::string path;File(const char *p,int):path(p){}const std::string &get_path()const{return path;}bool ready()const{return true;}bool stat(FileStatus *s)const{s->st_size=31;return true;}};
struct Socket{
 bool nonblock=false,ssl_want_write=false,ssl_want_read=false,dont_restart=false,cork_result=true;
 void *ssl=nullptr;double write_timeout=1.0,read_timeout=1.0;size_t send_size=1;unsigned sets=0,clears=0,queries=0,corks=0,uncorks=0,sends=0;std::vector<int>events,timeouts;std::string supplied,input;size_t input_offset=0;
 void set_nonblock(){++sets;nonblock=true;}void ssl_clear_error(){++clears;}bool has_kernel_nobufs(){++queries;return false;}
 int wait_event(int timeout,int event){timeouts.push_back(timeout);events.push_back(event);return SW_OK;}
 int catch_error(int){std::abort();}bool cork(){++corks;return cork_result;}bool uncork(){++uncorks;return true;}
 ssize_t send(const void *data,size_t length,int flags){assert(length>0&&flags==17);++sends;size_t sent=std::min(send_size,length);supplied.append(static_cast<const char*>(data),sent);return sent;}
 ssize_t writev(const iovec *iov,size_t count){++sends;std::string joined;for(size_t i=0;i<count;++i)joined.append(static_cast<const char*>(iov[i].iov_base),iov[i].iov_len);size_t sent=std::min(send_size,joined.size());assert(sent>0);supplied.append(joined.data(),sent);return sent;}
 ssize_t sendfile(const File&,off_t *offset,size_t length){assert(length>0);++sends;size_t sent=std::min(send_size,length);for(size_t i=0;i<sent;++i)supplied+=static_cast<char>(*offset+i);*offset+=sent;return sent;}
 ssize_t recv(void *data,size_t length,int flags){assert(length>0&&flags==0);++sends;size_t n=std::min(send_size,length);assert(input_offset+n<=input.size());std::memcpy(data,input.data()+input_offset,n);supplied.append(input.data()+input_offset,n);input_offset+=n;return n;}
 ssize_t recv_sync(void*,size_t,int);
 int what_event_want(int)const;bool wait_for(const std::function<ReturnCode()>&,int,int=-1);
 int sendfile_sync(const char*,off_t,size_t);ssize_t send_sync(const void*,size_t,int);ssize_t writev_sync(const iovec*,size_t);
};
#include "blocking.inc"
}
int main(){using namespace swoole;unsigned cases=0,checks=0;uint64_t timeout_sum=0;auto check=[&](bool value){assert(value);++checks;};
check(swr_v1_reactor_blocking_layout(0,0)==sizeof(swr_v1_reactor_blocking_wait_state));check(swr_v1_reactor_blocking_layout(0,1)==alignof(swr_v1_reactor_blocking_wait_state));check(swr_v1_reactor_blocking_layout(0,2)==offsetof(swr_v1_reactor_blocking_wait_state,timeout_msec));check(swr_v1_reactor_blocking_layout(0,3)==offsetof(swr_v1_reactor_blocking_wait_state,began_at));
check(swr_v1_reactor_blocking_layout(1,0)==sizeof(swr_v1_reactor_blocking_io_reply));check(swr_v1_reactor_blocking_layout(1,1)==alignof(swr_v1_reactor_blocking_io_reply));check(swr_v1_reactor_blocking_layout(1,2)==offsetof(swr_v1_reactor_blocking_io_reply,length));check(swr_v1_reactor_blocking_layout(1,3)==offsetof(swr_v1_reactor_blocking_io_reply,offset));check(swr_v1_reactor_blocking_layout(1,4)==offsetof(swr_v1_reactor_blocking_io_reply,value));
check(swr_v1_reactor_blocking_layout(2,0)==sizeof(swr_v1_reactor_blocking_file_state));check(swr_v1_reactor_blocking_layout(2,1)==alignof(swr_v1_reactor_blocking_file_state));check(swr_v1_reactor_blocking_layout(2,2)==offsetof(swr_v1_reactor_blocking_file_state,flags));
std::string payload;for(unsigned i=0;i<47;++i)payload+=static_cast<char>(i);
auto finish=[&](const Socket &s){for(auto value:s.timeouts)timeout_sum+=static_cast<uint64_t>(value+1);check(s.nonblock);check(s.sets==1);check(s.clears==0);check(s.events.size()+1==s.sends);check(s.queries==s.events.size());};
for(size_t length:{size_t(1),size_t(7),size_t(31)})for(size_t piece:{size_t(1),size_t(3),size_t(9)}){clock_value=0;clocks=0;Socket s;s.send_size=piece;check(s.send_sync(payload.data(),length,17)==static_cast<ssize_t>(length));check(s.supplied==payload.substr(0,length));finish(s);check(s.corks==0&&s.uncorks==0);++cases;}
for(size_t count:{size_t(1),size_t(2),size_t(3)})for(size_t piece:{size_t(1),size_t(3),size_t(11)}){clock_value=0;clocks=0;Socket s;s.send_size=piece;std::vector<iovec>iov;size_t total=0;for(size_t i=0;i<count;++i){size_t n=2*i+1;iov.push_back({&payload[total],n});total+=n;}size_t expected=std::min(piece,total);check(s.writev_sync(iov.data(),iov.size())==static_cast<ssize_t>(expected));check(s.supplied==payload.substr(0,expected));finish(s);check(s.sends==1);++cases;}
for(off_t offset:{off_t(0),off_t(2)})for(size_t length:{size_t(0),size_t(1),size_t(7),size_t(19)})for(bool accepted:{false,true}){clock_value=0;clocks=0;Socket s;s.send_size=3;s.cork_result=accepted;size_t expected=length?length:31-offset;check(s.sendfile_sync("ordinary-file",offset,length)==SW_OK);check(s.supplied==payload.substr(offset,expected));finish(s);check(s.corks==unsigned(expected>SW_SOCKET_CORK_MIN_SIZE));check(s.uncorks==unsigned(expected>SW_SOCKET_CORK_MIN_SIZE&&accepted));++cases;}
for(bool nonblock:{false,true})for(bool tls:{false,true})for(unsigned wants:{0u,1u,2u,3u})for(int timeout:{-1,100}){clock_value=0;clocks=0;Socket s;s.nonblock=nonblock;s.ssl=tls?&s:nullptr;s.ssl_want_write=wants&1;s.ssl_want_read=wants&2;unsigned callbacks=0;check(s.wait_for([&](){++callbacks;return callbacks==1?SW_CONTINUE:callbacks==2?SW_WAIT:SW_READY;},SW_EVENT_WRITE,timeout));check(callbacks==3);check(s.sets==unsigned(!nonblock));check(s.clears==unsigned(tls));check(s.queries==1);check(s.events.size()==2);int expected=tls&&wants?(wants&1?SW_EVENT_WRITE:SW_EVENT_READ):SW_EVENT_WRITE;check(s.events==std::vector<int>({expected,expected}));check(clocks==unsigned(timeout>0?3:0));for(int value:s.timeouts)timeout_sum+=static_cast<uint64_t>(value+1);++cases;}
for(size_t length:{size_t(1),size_t(7),size_t(31)})for(size_t piece:{size_t(1),size_t(3),size_t(9)})for(int flags:{0,static_cast<int>(MSG_WAITALL)}){clock_value=0;clocks=0;Socket s;s.input=payload;s.send_size=piece;std::string data(length,'x');size_t expected=flags?length:std::min(piece,length);check(s.recv_sync(&data[0],length,flags)==static_cast<ssize_t>(expected));check(data.substr(0,expected)==payload.substr(0,expected));check(s.supplied==payload.substr(0,expected));finish(s);check(s.corks==0&&s.uncorks==0);++cases;}
std::cout<<"{\"cases\":"<<cases<<",\"checks\":"<<checks<<",\"timeout_sum\":"<<timeout_sum<<",\"layout_facts\":12,\"positive_only\":true}\n";
}
