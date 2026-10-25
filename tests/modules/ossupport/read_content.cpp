// SPDX-License-Identifier: Apache-2.0
// Exact File bodies + exact pinned String::grow, with scalar IO/reserve adapters.
#include "swoole_rs_ossupport.h"
#include <algorithm>
#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <memory>
#include <sstream>
#include <string>
#include <vector>
#include <sys/types.h>
static_assert(sizeof(ssize_t)==8 && sizeof(swr_v1_os_read_content_state)==4,"LP64/action ABI");
struct Step {ssize_t result;int error;};
static size_t initial_capacity,position_,index_,generation_;
static std::string payload;
static std::vector<Step> plan;
static std::vector<std::string> trace;
struct String;
static String *live;
struct String {
    size_t length=0,size;
    char *str;
    std::vector<char> memory;
    explicit String(size_t capacity):size(capacity),memory(capacity,char(0xa5)) {
        str=memory.data();live=this;generation_=0;
        trace.push_back("allocate:"+std::to_string(size));
    }
    void reserve(size_t capacity) {
        memory.resize(capacity,char(0xa5));str=memory.data();size=capacity;++generation_;
        trace.push_back("reserve:"+std::to_string(size));
    }
    void grow(size_t n);
    void observed_grow(size_t n) {
        trace.push_back("grow:"+std::to_string(n)+":length="+std::to_string(length));
        grow(n);
    }
};
#include "grow.inc"
static ssize_t model_read(void *buf,size_t amount) {
    if(++index_>128 || buf!=live->str+live->length || amount!=live->size-live->length || amount==0)std::abort();
    Step step=index_<=plan.size()?plan[index_-1]:Step{ssize_t(amount),EDOM};
    ssize_t n=step.result>0?std::min<ssize_t>(step.result,std::min(amount,payload.size()-position_)):step.result;
    if(n>0)std::memcpy(buf,payload.data()+position_,size_t(n));
    std::ostringstream row;row<<"read:"<<position_<<':'<<amount<<':'<<generation_<<':'<<n<<':'<<step.error;
    trace.push_back(row.str());if(n>0)position_+=size_t(n);errno=step.error;return n;
}
#define SW_BUFFER_SIZE_STD initial_capacity
#define grow observed_grow
namespace original {
struct File {ssize_t read(void*b,size_t n)const{return model_read(b,n);}std::shared_ptr<String> read_content()const;};
#include "original.inc"
}
namespace selected {
struct File {ssize_t read(void*b,size_t n)const{return model_read(b,n);}std::shared_ptr<String> read_content()const;};
#include "selected.inc"
}
#undef grow
struct Observation {
    size_t length,capacity,offset;int error;std::string bytes;std::vector<std::string> calls;
    bool operator==(const Observation&o)const{return length==o.length&&capacity==o.capacity&&offset==o.offset&&error==o.error&&bytes==o.bytes&&calls==o.calls;}
};
static Observation run(bool rust) {
    position_=index_=0;trace.clear();errno=E2BIG;
    auto data=rust?selected::File().read_content():original::File().read_content();
    int error=errno;
    if(!data || data->length!=position_ || data->length>data->size ||
       std::string(data->str,data->length)!=payload.substr(0,position_))std::abort();
    // Entire initialized model capacity compares guard bytes too: no final NUL.
    return {data->length,data->size,position_,error,std::string(data->str,data->size),trace};
}
int main() {
    Step events[]={{-1,EINTR},{-1,EAGAIN},{-1,EIO},{0,EIO},{1,EDOM},{3,E2BIG},{127,0}};
    size_t cases=0;
    for(size_t capacity:{size_t(1),size_t(2),size_t(8),size_t(64)})
    for(size_t length:{size_t(0),size_t(1),size_t(2),size_t(7),size_t(8),size_t(9),size_t(31),size_t(63)})
    for(size_t a=0;a<7;++a)for(size_t b=0;b<7;++b) {
        initial_capacity=capacity;payload.resize(length);
        for(size_t i=0;i<length;++i)payload[i]=char((i*31)%256);
        plan={events[a],events[b]};auto native=run(false),rust=run(true);
        if(!(native==rust)){std::cerr<<"mismatch "<<cases<<'\n';return 1;}
        std::cout<<cases++<<'\t'<<capacity<<'\t'<<length<<'\t'<<a<<','<<b<<'\t'<<native.length<<'\t'<<native.capacity<<'\t'<<native.error;
        for(auto &call:native.calls)std::cout<<'\t'<<call;
        std::cout<<'\n';
    }
    std::cout<<"PASS\t"<<cases<<'\n';
}
