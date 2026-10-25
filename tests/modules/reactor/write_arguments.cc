#include <cassert>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <iostream>
#include <string>
#include <vector>
#include <sys/types.h>
#include <sys/uio.h>
#include "swoole_rs_reactor.h"
static_assert(offsetof(swr_v1_reactor_write_arguments,offset)==sizeof(size_t),"reply offset");
static_assert(offsetof(swr_v1_reactor_write_arguments,status)==2*sizeof(size_t),"reply status");
static_assert(sizeof(swr_v1_reactor_write_arguments)==3*sizeof(size_t),"reply extent");
#define SW_ERR -1
#define SW_LOG_WARNING 1
#define SW_ERROR_OPERATION_NOT_SUPPORT 1
#define swoole_error_log(...) std::abort()
#define SW_LOOP_N(n) for (decltype(n) i = 0; i < n; i++)
namespace swoole {
struct Buffer {
    std::string bytes;
    void append(const char *data,uint32_t size){bytes.append(data,size);}
    void append(const iovec *iov,size_t count,off_t offset){
        size_t skip=static_cast<size_t>(offset);
        for(size_t i=0;i<count;++i){auto size=iov[i].iov_len;if(skip>=size){skip-=size;continue;}bytes.append(static_cast<const char*>(iov[i].iov_base)+skip,size-skip);skip=0;}
    }
};
struct Socket {
    bool ssl=false;size_t sent=1;unsigned calls=0;std::string supplied;
    ssize_t send(const void *data,size_t n,int){++calls;supplied.assign(static_cast<const char*>(data),n);return static_cast<ssize_t>(sent);}
    ssize_t writev(const iovec *iov,size_t count){++calls;supplied.clear();for(size_t i=0;i<count;++i)supplied.append(static_cast<const char*>(iov[i].iov_base),iov[i].iov_len);return static_cast<ssize_t>(sent);}
};
#include "write_arguments.inc"
}
int main(){
    using namespace swoole;unsigned cases=0,checks=0;auto check=[&](bool value){assert(value);++checks;};
    check(swr_v1_reactor_iovec_layout(0)==sizeof(iovec));check(swr_v1_reactor_iovec_layout(1)==alignof(iovec));check(swr_v1_reactor_iovec_layout(2)==offsetof(iovec,iov_base));check(swr_v1_reactor_iovec_layout(3)==offsetof(iovec,iov_len));
    std::string input("abc\0defgh",9);
    for(size_t sent:{size_t(1),size_t(3),input.size()}){
        Reactor r;Socket socket;socket.sent=sent;check(Reactor::_write(&r,&socket,input.data(),input.size())==static_cast<ssize_t>(input.size()));check(socket.supplied==input);check(socket.calls==1);check(r.buffer.bytes==input.substr(sent));++cases;
    }
    std::vector<std::string> values={"ab",std::string("c\0d",3),"efgh"};
    for(size_t count:{size_t(1),size_t(2),size_t(3)}){
        std::vector<iovec> vectors;std::string joined;for(size_t i=0;i<count;++i){vectors.push_back({const_cast<char*>(values[i].data()),values[i].size()});joined+=values[i];}
        for(size_t sent=1;sent<=joined.size();++sent){
            Reactor r;Socket socket;socket.sent=sent;check(Reactor::_writev(&r,&socket,vectors.data(),vectors.size())==static_cast<ssize_t>(joined.size()));check(socket.supplied==joined);check(socket.calls==1);check(r.buffer.bytes==joined.substr(sent));++cases;
        }
    }
    std::cout<<"{\"cases\":"<<cases<<",\"checks\":"<<checks<<",\"layout_facts\":4,\"positive_lengths_and_sends_only\":true}\n";
}
