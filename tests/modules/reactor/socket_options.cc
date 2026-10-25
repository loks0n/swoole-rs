#include <cassert>
#include <cerrno>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <vector>
#include <sys/socket.h>
#include <sys/time.h>
#include "swoole_rs_reactor.h"
#define SW_TIMEOUT_DNS 1
#define SW_TIMEOUT_CONNECT 2
#define SW_TIMEOUT_READ 4
#define SW_TIMEOUT_WRITE 8
#define SW_ERROR_SOCKET_POLL_TIMEOUT 6002
#define SW_ASSERT_1BYTE(value) assert((value)>=0&&(value)<256)
#define swoole_sys_warning(...) std::abort()
static std::vector<int>writes,reads,options;static unsigned queries=0,syscalls=0;static timeval captured{};static int captured_type=0;
extern "C" int setsockopt(int fd,int level,int type,const void *value,socklen_t length)
#ifdef __linux__
noexcept
#endif
{assert(fd==17&&level==SOL_SOCKET&&length==sizeof(timeval));captured=*static_cast<const timeval*>(value);captured_type=type;++syscalls;return 0;}
namespace swoole {
using TimeoutType=int;
static int swoole_get_last_error(){++queries;return 0;}
struct Field {int id;double value;Field(int i,double v):id(i),value(v){}Field &operator=(double v){writes.push_back(id);value=v;return *this;}operator double()const{reads.push_back(id);return value;}};
struct Socket {
 int fd=17;Field dns_timeout{1,1},connect_timeout{2,2},read_timeout{3,3},write_timeout{4,4};
 int set_option(int level,int type,uint32_t value)const{assert(level==SOL_SOCKET&&value>0);options.push_back(type);return 0;}
 bool set_buffer_size(uint32_t)const;bool set_recv_buffer_size(uint32_t)const;bool set_send_buffer_size(uint32_t)const;
 void set_timeout(double,int);double get_timeout(TimeoutType)const;bool has_timedout()const;bool set_kernel_read_timeout(double);bool set_kernel_write_timeout(double);
};
#include "socket_options.inc"
}
int main(){using namespace swoole;unsigned checks=0,cases=0,effects=0;auto check=[&](bool value){assert(value);++checks;};
check(swr_v1_reactor_socket_timeout_layout(0)==sizeof(swr_v1_reactor_socket_timeout_reply));check(swr_v1_reactor_socket_timeout_layout(1)==alignof(swr_v1_reactor_socket_timeout_reply));check(swr_v1_reactor_socket_timeout_layout(2)==offsetof(swr_v1_reactor_socket_timeout_reply,phase));check(swr_v1_reactor_socket_timeout_layout(3)==offsetof(swr_v1_reactor_socket_timeout_reply,action));check(swr_v1_reactor_socket_timeout_layout(4)==offsetof(swr_v1_reactor_socket_timeout_reply,value));check(swr_v1_reactor_socket_timeout_layout(5)==offsetof(swr_v1_reactor_socket_timeout_reply,seconds));check(swr_v1_reactor_socket_timeout_layout(6)==offsetof(swr_v1_reactor_socket_timeout_reply,microseconds));
for(uint32_t size:{1u,7u,4096u})for(int kind:{0,1,2}){Socket s;options.clear();check(kind==0?s.set_buffer_size(size):kind==1?s.set_recv_buffer_size(size):s.set_send_buffer_size(size));std::vector<int>expected=kind==0?std::vector<int>{SO_SNDBUF,SO_RCVBUF}:std::vector<int>{kind==1?SO_RCVBUF:SO_SNDBUF};check(options==expected);check(s.dns_timeout.value==1&&s.write_timeout.value==4);effects+=options.size();++cases;}
for(double value:{0.0,1.25,-1.0})for(int type=0;type<16;++type){Socket s;writes.clear();reads.clear();s.set_timeout(value,type);std::vector<int>expected;for(int i=0;i<4;++i)if(value!=0&&(type&(1<<i)))expected.push_back(i+1);check(writes==expected);check(reads.empty());check(s.dns_timeout.value==((value!=0&&(type&1))?value:1));check(s.connect_timeout.value==((value!=0&&(type&2))?value:2));check(s.read_timeout.value==((value!=0&&(type&4))?value:3));check(s.write_timeout.value==((value!=0&&(type&8))?value:4));effects+=writes.size();++cases;}
for(int type:{1,2,4,8}){Socket s;writes.clear();reads.clear();double expected=type==1?1:type==2?2:type==4?3:4;check(s.get_timeout(type)==expected);check(reads==std::vector<int>{static_cast<int>(expected)});check(writes.empty());effects+=reads.size();++cases;}
{Socket s;queries=0;errno=0;check(!s.has_timedout());check(queries==1);check(errno==0);effects+=queries;++cases;}
for(double value:{0.125,1.25,7.75})for(int type:{SO_SNDTIMEO,SO_RCVTIMEO}){syscalls=0;check(_set_timeout(17,type,value));check(captured_type==type&&syscalls==1);int seconds=static_cast<int>(value);check(captured.tv_sec==seconds);check(captured.tv_usec==static_cast<int>((value-seconds)*1000*1000));effects+=syscalls;++cases;}
for(double value:{0.125,1.25,7.75})for(bool read:{false,true}){Socket s;syscalls=0;writes.clear();reads.clear();check(read?s.set_kernel_read_timeout(value):s.set_kernel_write_timeout(value));check(captured_type==(read?SO_SNDTIMEO:SO_RCVTIMEO)&&syscalls==1);check(writes==std::vector<int>{read?4:3});check(read?(s.write_timeout.value==value&&s.read_timeout.value==3):(s.read_timeout.value==value&&s.write_timeout.value==4));check(reads.empty());effects+=syscalls+writes.size();++cases;}
std::cout<<"{\"cases\":"<<cases<<",\"checks\":"<<checks<<",\"effects\":"<<effects<<",\"layout_facts\":7,\"positive_only\":true}\n";
}
