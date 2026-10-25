// SPDX-License-Identifier: Apache-2.0
// Exact bodies, scalar native read/seek adapter only; no actual fault or host fixture.
#include "swoole_rs_ossupport.h"
#include <algorithm>
#include <cerrno>
#include <climits>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
#include <sys/types.h>
static_assert(sizeof(ssize_t)==8 && sizeof(off_t)==8, "LP64 fixture");
static_assert(sizeof(swr_v1_os_file_line_result_t)==16, "result ABI");
static_assert(offsetof(swr_v1_os_file_line_result_t,action)==8 && offsetof(swr_v1_os_file_line_result_t,extra)==12,"field ABI");
static std::vector<std::string> calls;
static off_t initial, final_offset;
static ssize_t observed;
static int seek_errno;
static std::string payload;
static char *base;
static off_t model_get_offset() {
    calls.push_back("get_offset"); errno=EBUSY; return initial;
}
static ssize_t model_read(void *buf,size_t n) {
    if(buf!=base || (observed>0 && size_t(observed)>n)) std::abort();
    std::ostringstream text; text<<"read:"<<n<<':'<<observed;
    calls.push_back(text.str()); errno=EDOM;
    if(observed>0) std::memcpy(buf,payload.data(),observed);
    return observed;
}
static void model_set_offset(off_t n) {
    std::ostringstream text; text<<"set_offset:"<<n<<":bytes=";
    // Observe entire buffer here: verifies NUL publication happened BEFORE seek.
    for(int i=0;i<64;++i) text<<std::hex<<int(static_cast<unsigned char>(base[i]))<<',';
    calls.push_back(text.str()); final_offset=n; errno=seek_errno;
}
namespace original {
struct File {
    off_t get_offset() const {return model_get_offset();}
    ssize_t read(void *buf,size_t n) const {return model_read(buf,n);}
    void set_offset(off_t n) const {model_set_offset(n);}
    ssize_t read_line(void *,size_t) const;
};
#include "original.inc"
}
namespace selected {
struct File {
    off_t get_offset() const {return model_get_offset();}
    ssize_t read(void *buf,size_t n) const {return model_read(buf,n);}
    void set_offset(off_t n) const {model_set_offset(n);}
    ssize_t read_line(void *,size_t) const;
};
#include "selected.inc"
}
struct Observation {
    ssize_t result; off_t offset; int error;
    std::vector<std::string> trace; std::string bytes;
    bool operator==(const Observation&o)const {
        return result==o.result&&offset==o.offset&&error==o.error&&trace==o.trace&&bytes==o.bytes;
    }
};
static Observation run(bool rust,size_t size) {
    char buffer[64];std::memset(buffer,'X',sizeof(buffer));base=buffer;
    calls.clear();final_offset=initial;errno=E2BIG;
    ssize_t n=rust?selected::File().read_line(buffer,size):original::File().read_line(buffer,size);
    int error=errno;
    return {n,final_offset,error,calls,std::string(buffer,sizeof(buffer))};
}
int main() {
    size_t cases=0;
    for(size_t size:{size_t(1),size_t(2),size_t(3),size_t(8),size_t(32)})
    for(ssize_t raw:{ssize_t(-2),ssize_t(-1),ssize_t(0),ssize_t(1),ssize_t(3),ssize_t(31)}) {
        observed=raw>0?std::min<ssize_t>(raw,size-1):raw;
        std::vector<std::string> variants={std::string(size_t(std::max<ssize_t>(0,observed)),'\xff')};
        for(ssize_t i=0;i<observed;++i) for(char terminator:{'\0','\n'}) {
            auto s=variants.front();s[i]=terminator;variants.push_back(s);
        }
        if(observed>1){auto s=variants.front();s[0]='\n';s[1]='\0';variants.push_back(s);s[0]='\0';s[1]='\n';variants.push_back(s);}
        for(auto &bytes:variants) for(off_t offset:{off_t(-64),off_t(-1),off_t(0),off_t(17),off_t(LLONG_MAX-64)})
        for(int error:{0,EACCES}) {
            payload=bytes;initial=offset;seek_errno=error;
            auto native=run(false,size),rust=run(true,size);
            if(!(native==rust)) {std::cerr<<"mismatch "<<cases<<'\n';return 1;}
            ssize_t end=observed;
            if(observed>0){for(ssize_t i=0;i<observed;++i) if(bytes[i]=='\0'||bytes[i]=='\n'){end=i+1;break;}}
            bool found=observed>0 && (bytes[size_t(end-1)]=='\0'||bytes[size_t(end-1)]=='\n');
            if(native.result!=end || native.trace.size()!=(observed>0?3u:2u) ||
               native.error!=(observed>0?error:EDOM) ||
               native.offset!=(observed>0?initial+end+(found?0:1):initial) ||
               (observed>0&&native.bytes[size_t(end)]!='\0')) std::abort();
            std::cout<<cases++<<'\t'<<size<<'\t'<<observed<<'\t'<<initial<<'\t'<<end<<'\t'<<native.offset<<'\t'<<native.error;
            for(auto &call:native.trace)std::cout<<'\t'<<call;
            std::cout<<'\n';
        }
    }
    std::cout<<"PASS\t"<<cases<<'\n';
}
