// SPDX-License-Identifier: Apache-2.0
// Exact original/patched outer loop; finite scalar IO model, no entropy/fault probe.
#include "swoole_rs_ossupport.h"
#include <algorithm>
#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
#include <sys/types.h>
static_assert(sizeof(size_t) == 8 && sizeof(ssize_t) == 8, "LP64 fixture");
static_assert(sizeof(swr_v1_os_random_bytes_state) == 16, "cursor ABI");
struct Step { ssize_t result; int error; };
static std::vector<Step> plan;
static std::vector<std::string> trace;
static size_t index_;
static char *base;
static ssize_t model_getrandom(void *buffer, size_t size, unsigned flags) {
    if (flags != 0 || ++index_ > 8 || size == 0) std::abort();
    const Step step = index_ <= plan.size() ? plan[index_-1] : Step{static_cast<ssize_t>(size), EDOM};
    const ssize_t n = step.result > 0 ? std::min<ssize_t>(step.result, size) : step.result;
    if (n > 0) for (ssize_t i = 0; i < n; ++i) static_cast<char *>(buffer)[i] = 'A' + ((static_cast<char *>(buffer)-base+i) % 26);
    std::ostringstream text;
    text << "getrandom:" << (static_cast<char *>(buffer)-base) << ':' << size << ':' << flags << ':' << n << ':' << step.error;
    trace.push_back(text.str()); errno = step.error;
    return n;
}
#define getrandom model_getrandom
namespace original {
#include "original.inc"
}
namespace selected {
#include "selected.inc"
}
#undef getrandom
struct Observation {
    size_t result;
    int error;
    std::vector<std::string> calls;
    std::string bytes;
    bool operator==(const Observation &o) const {
        return result==o.result && error==o.error && calls==o.calls && bytes==o.bytes;
    }
};
static Observation run(bool rust, size_t size) {
    char buffer[64]; std::memset(buffer, 'X', sizeof(buffer)); base=buffer;
    index_=0; trace.clear(); errno=E2BIG;
    size_t n = rust ? selected::swoole_random_bytes(buffer,size) : original::swoole_random_bytes(buffer,size);
    const int error=errno;
    return {n,error,trace,std::string(buffer,sizeof(buffer))};
}
int main() {
    const Step events[]={{-1,EINTR},{-1,EAGAIN},{-1,EIO},{0,EINTR},{0,EIO},{1,EDOM},{3,E2BIG}};
    size_t cases=0;
    for(size_t size : {size_t(0),size_t(1),size_t(2),size_t(7),size_t(31)})
    for(size_t a=0;a<7;++a) for(size_t b=0;b<7;++b) for(size_t c=0;c<7;++c) {
        plan={events[a],events[b],events[c]};
        auto native=run(false,size),rust=run(true,size);
        if(!(native==rust)) { std::cerr<<"mismatch "<<cases<<'\n';return 1; }
        std::cout<<cases++<<'\t'<<size<<'\t'<<a<<','<<b<<','<<c<<'\t'<<native.result<<'\t'<<native.error<<'\t'<<native.bytes;
        for(auto &call:native.calls) std::cout<<'\t'<<call;
        std::cout<<'\n';
    }
    std::cout<<"PASS\t"<<cases<<'\n';
}
