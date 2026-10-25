#include <cassert>
#include <csetjmp>
#include <cerrno>
#include <cstdarg>
#include <cstdio>
#include <cstdint>
#include <functional>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#include <sys/uio.h>
#include <algorithm>
#include "swoole_rs_reactor.h"
constexpr int SW_OK=0,SW_ERR=-1,SW_WAIT=1,SW_LOG_WARNING=1;
constexpr int SW_ERROR_PACKAGE_LENGTH_TOO_LARGE=2,SW_ERROR_OUTPUT_BUFFER_OVERFLOW=3,SW_ERROR_OPERATION_NOT_SUPPORT=4;
struct NativeFailure {int kind;};
struct Execution {
    std::vector<std::string> trace;
    int failure=0,catch_result=0,catch_errno=EIO,send_index=0,last_error=0;
    bool add_fail=false;
    ssize_t send_limit=0;
    std::string kernel;
} *active;
struct Buffer {
    std::vector<int> queue_;
    uint32_t bytes=0;
    std::string payload;
    explicit Buffer(uint32_t n) {
        active->trace.push_back("allocate:"+std::to_string(n));
        if(active->failure==1) throw NativeFailure{1};
    }
    void append(const char *data,size_t n) {active->trace.push_back("bytes-append");payload.append(data,n);bytes+=n;queue_.push_back(1);}
    void append(const iovec *iov,size_t count,ssize_t offset) {
        for(size_t i=0;i<count;i++) {
            if(static_cast<size_t>(offset)>=iov[i].iov_len){offset-=iov[i].iov_len;continue;}
            append(static_cast<const char*>(iov[i].iov_base)+offset,iov[i].iov_len-offset);offset=0;
        }
    }
    uint32_t length() const {return bytes;}
#include "empty.inc"
};
struct Socket {
    Buffer *out_buffer=nullptr;
    uint32_t buffer_size=64,chunk_size=16;
    int nonblock=1,events=0;
    bool ssl_send_=false;
    void *ssl=nullptr;
    static constexpr uint32_t default_buffer_size=64;
    void set_memory_buffer_size(uint32_t n) {active->trace.push_back("capacity");buffer_size=n;}
    void set_fd_option(int n,int) {active->trace.push_back("nonblock");nonblock=n;}
    ssize_t send(const void *data,size_t length,int) {
        active->trace.push_back("native-send");
        if(active->send_limit<0){errno=EAGAIN;return -1;}
        size_t n=std::min(length,static_cast<size_t>(active->send_limit));active->kernel.append(static_cast<const char*>(data),n);return n;
    }
    ssize_t writev(const iovec *iov,size_t count) {
        active->trace.push_back("native-writev");
        if(active->send_limit<0){errno=EAGAIN;return -1;}
        size_t remaining=active->send_limit,written=0;
        for(size_t i=0;i<count && remaining;i++){size_t n=std::min(remaining,iov[i].iov_len);active->kernel.append(static_cast<const char*>(iov[i].iov_base),n);written+=n;remaining-=n;}
        return written;
    }
    int get_fd() const {return 17;}
    bool isset_writable_event() const {return events&1024;}
    int catch_write_error(int error) {
        active->trace.push_back("catch:"+std::to_string(error));errno=active->catch_errno;return active->catch_result;
    }
};
struct Reactor {
    int add_write_event(Socket *s) const {
        active->trace.push_back("add-write");
        s->events|=1024;
        if(active->add_fail){errno=EBADF;return -1;}return 0;
    }
};
static void error_log(int,int code,const char *format,...) {
    char text[256];va_list args;va_start(args,format);vsnprintf(text,sizeof(text),format,args);va_end(args);
    active->trace.push_back(std::to_string(code)+":"+text);errno=ERANGE;
}
static void swoole_set_last_error(int error) {active->trace.push_back("last-error:"+std::to_string(error));active->last_error=error;}
#define swoole_error_log(...) error_log(__VA_ARGS__)
#define SW_LOOP_N(n) for(size_t i=0;i<(n);i++)
#include "write.inc"
struct Outcome {
    std::vector<std::string> trace;
    ssize_t result=0;
    int error=0,last_error=0,events=0,nonblock=0;
    uint32_t bytes=0,capacity=0;
    bool has_buffer=false;
    bool operator==(const Outcome &o) const {return trace==o.trace && result==o.result && error==o.error && last_error==o.last_error && events==o.events && nonblock==o.nonblock && bytes==o.bytes && capacity==o.capacity && has_buffer==o.has_buffer;}
};
template<class T> Outcome run(int kind,size_t length,int send_mode,int wait,int post,int bits,int failure) {
    Execution e;active=&e;e.catch_result=wait?SW_WAIT:0;e.catch_errno=post;e.add_fail=bits&4;
    Reactor reactor;Socket socket;
    if(bits&1)socket.buffer_size=0;
    if(bits&2)socket.nonblock=0;
    if(bits&8)socket.events=1024;
    if(kind==4)socket.ssl_send_=true;
    if(kind==1 || kind==2 || kind==3) {
        socket.out_buffer=new Buffer(16);
        if(kind==2 ||kind==3)socket.out_buffer->queue_.push_back(1);
        if(kind==3)socket.out_buffer->bytes=60;
    }
    e.failure=failure;e.trace.clear();errno=EDOM;
    auto send=[&]() -> ssize_t {
        e.trace.push_back("send");
        if(failure==3)throw NativeFailure{3};
        if(send_mode==0)return length;
        if(send_mode==1)return length?length/2:0;
        if(send_mode==2 && e.send_index++>0)return length;
        errno=send_mode==2?EINTR:EIO;return -1;
    };
    auto append=[&](Buffer *b) {
        e.trace.push_back("append");assert(b);
        if(failure==2)throw NativeFailure{2};
        b->queue_.push_back(1);b->bytes+=static_cast<uint32_t>(length);
    };
    Outcome out;
    try {out.result=T::write_func(&reactor,&socket,length,send,append);}catch(const NativeFailure &error){e.trace.push_back("exception:"+std::to_string(error.kind));out.result=-99;}
    out.trace=e.trace;out.error=errno;out.last_error=e.last_error;out.events=socket.events;out.nonblock=socket.nonblock;out.capacity=socket.buffer_size;
    out.has_buffer=socket.out_buffer;out.bytes=socket.out_buffer?socket.out_buffer->bytes:0;
    delete socket.out_buffer;return out;
}
template<class T> std::string actual_writes(ssize_t limit,bool vector,bool tls) {
    Execution e;active=&e;e.send_limit=limit;e.catch_result=SW_WAIT;e.catch_errno=EAGAIN;
    Reactor reactor;Socket socket;socket.ssl_send_=tls;
    const std::string bytes="abcde0123456789ABCDEFGHIJKLMNOPQ";
    iovec iov[5]={{const_cast<char*>(bytes.data()),0},{const_cast<char*>(bytes.data()),5},{const_cast<char*>(bytes.data()+5),0},{const_cast<char*>(bytes.data()+5),10},{const_cast<char*>(bytes.data()+15),17}};
    ssize_t result=vector?T::_writev(&reactor,&socket,iov,5):T::_write(&reactor,&socket,bytes.data(),bytes.size());
    assert(result==static_cast<ssize_t>(bytes.size()));
    std::string combined=e.kernel+(socket.out_buffer?socket.out_buffer->payload:"");assert(combined==bytes);
    delete socket.out_buffer;return combined;
}
static std::jmp_buf write_jump;
struct BailoutOwner {
    Execution execution;
    Reactor reactor;
    Socket socket;
    std::function<ssize_t()> send;
    std::function<void(Buffer*)> append;
    explicit BailoutOwner(int mode):send([this,mode]() -> ssize_t {
        execution.trace.push_back("send");
        if(mode==1)std::longjmp(write_jump,1);
        errno=EAGAIN;return -1;
    }),append([this](Buffer*) {execution.trace.push_back("append");std::longjmp(write_jump,1);}) {
        execution.catch_result=SW_WAIT;execution.catch_errno=EAGAIN;
    }
};
template<class T> void native_bailout(int mode) {
    auto *owner=new BailoutOwner(mode);active=&owner->execution;
    if(setjmp(write_jump)==0) {
        T::write_func(&owner->reactor,&owner->socket,16,owner->send,owner->append);assert(false);
    }
    assert(owner->execution.trace.front()=="send");
    assert((owner->socket.out_buffer!=nullptr)==(mode==2));
    delete owner->socket.out_buffer;delete owner;
}
int main() {
    try {throw NativeFailure{0};}catch(const NativeFailure &){}
    const size_t lengths[]={0,1,16,64,65,static_cast<size_t>(UINT32_MAX)+2,SIZE_MAX};
    unsigned count=0;
    for(int kind=0;kind<5;kind++)for(size_t length:lengths)for(int send=0;send<4;send++)for(int wait=0;wait<2;wait++)for(int post:{EIO,EINTR})for(int bits=0;bits<16;bits++)for(int failure=0;failure<4;failure++) {
        // A perpetual EINTR catch is an original infinite retry, not a finite case.
        if((kind==0 || kind==1) && wait==0 && post==EINTR && failure!=3 && (send==3 || length==0 || (send==1 && length<2)))continue;
        auto original=run<Write0>(kind,length,send,wait,post,bits,failure);
        auto candidate=run<Write1>(kind,length,send,wait,post,bits,failure);
        if(!(original==candidate)) {
            std::cerr<<"mismatch kind="<<kind<<" length="<<length<<" send="<<send<<" wait="<<wait<<" post="<<post<<" bits="<<bits<<" failure="<<failure<<"\n";
            for(const auto &line:original.trace)std::cerr<<"original "<<line<<"\n";
            for(const auto &line:candidate.trace)std::cerr<<"candidate "<<line<<"\n";
            std::cerr<<"results "<<original.result<<","<<candidate.result<<" errno "<<original.error<<","<<candidate.error<<"\n";
            assert(false);
        }++count;
    }
    for(int mode=1;mode<=2;mode++){native_bailout<Write0>(mode);native_bailout<Write1>(mode);}
    unsigned tails=0;
    for(ssize_t limit:{-1,0,1,5,6,15,16,31,32})for(bool vector:{false,true})for(bool tls:{false,true}) {
        assert(actual_writes<Write0>(limit,vector,tls)==actual_writes<Write1>(limit,vector,tls));++tails;
    }
    std::cout<<"write_admission="<<count<<" actual_write_tails="<<tails<<" native_bailout=4 errors=0\n";
}
