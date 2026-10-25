// SPDX-License-Identifier: Apache-2.0
// Deterministic OS fault boundary, executing the actual pinned sendfile.cc body.
#include "swoole_socket.h"
#include <cassert>
#include <vector>
#include <cerrno>
#include <cstdio>
#if defined(__linux__)
#include <sys/sendfile.h>
#endif
struct Step { ssize_t result; int error; off_t moved; };
static std::vector<Step> steps;
static std::vector<off_t> observed_offsets;
static std::vector<size_t> observed_sizes;
static size_t index_;
#if defined(__APPLE__)
extern "C" int sendfile(int in, int out, off_t offset, off_t *length, sf_hdtr *header, int flags) {
    assert(in==19 && out==31 && flags==0);
    assert(header && !header->headers && !header->trailers && header->hdr_cnt==0 && header->trl_cnt==0);
    assert(index_<steps.size());observed_offsets.push_back(offset);observed_sizes.push_back(*length);
    auto step=steps[index_++];*length=step.moved;errno=step.error;return step.result;
}
#elif defined(__linux__)
extern "C" ssize_t sendfile(int out, int in, off_t *offset, size_t size) {
    assert(in==19 && out==31 && index_<steps.size());observed_offsets.push_back(*offset);observed_sizes.push_back(size);
    auto step=steps[index_++];*offset+=step.moved;errno=step.error;return step.result;
}
#endif
static void check(std::vector<Step> plan, ssize_t result, off_t expected, size_t count) {
    steps=plan;index_=0;observed_offsets.clear();observed_sizes.clear();off_t offset=10;
    assert(swoole_sendfile(31,19,&offset,100)==result);assert(offset==expected && index_==count);
}
int main() {
    swoole_init();
#if defined(__APPLE__)
    check({{-1,EINTR,7},{0,0,5}},5,22,2);
    assert(observed_offsets==std::vector<off_t>({10,17}));
    assert(observed_sizes==std::vector<size_t>({100,7})); // Pinned retry reuses mutated size.
    check({{-1,EAGAIN,9}},-1,19,1);
    check({{0,0,0}},0,10,1);
    check({{1,0,3}},SW_ERR,13,1);
#elif defined(__linux__)
    check({{-1,EINTR,7}},-1,17,1); // Linux wrapper never adds a retry.
    check({{-1,EAGAIN,9}},-1,19,1);
    check({{0,0,0}},0,10,1);
    check({{3,0,3}},3,13,1);
#endif
    check({{-1,EIO,0}},-1,10,1);
    swoole_clean();
    puts("actual native sendfile body progress/retry/error conventions passed");
}
