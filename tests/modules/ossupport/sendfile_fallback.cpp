// SPDX-License-Identifier: Apache-2.0
// Scalar simulated IO only: no kernel fault injection, network, descriptors or IPC.
#include "swoole_rs_ossupport.h"
#include <algorithm>
#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
#include <limits>
#include <sys/types.h>
#define SW_BUFFER_SIZE_BIG 65536
#define SW_ERR -1
static_assert(sizeof(size_t) == 8 && sizeof(off_t) == 8 && sizeof(ssize_t) == 8, "LP64 fixture");
static_assert(sizeof(swr_v1_os_sendfile_fallback_state) == 24, "cursor layout");
struct Plan { ssize_t read; ssize_t write; int read_errno; int write_errno; };
static Plan plan;
static std::vector<std::string> trace;
static const void *buffer;
static size_t read_calls, write_calls;
static ssize_t model_pread(int fd, void *p, size_t count, off_t offset) {
    if (fd != 19 || read_calls++) std::abort();
    buffer = p;
    std::ostringstream t; t << "pread:" << count << ':' << offset; trace.push_back(t.str());
    const ssize_t n = plan.read > 0 ? std::min<ssize_t>(plan.read, count) : plan.read;
    if (n > 0) for (ssize_t i = 0; i < n; ++i) static_cast<unsigned char *>(p)[i] = i % 251;
    errno = plan.read_errno;
    return n;
}
static ssize_t model_write(int fd, const void *p, size_t count) {
    if (fd != 31 || p != buffer || write_calls++) std::abort();
    uint64_t hash = 0;
    for (size_t i = 0; i < count; ++i) {
        if (static_cast<const unsigned char *>(p)[i] != i % 251) std::abort();
        hash = hash * 33 + static_cast<const unsigned char *>(p)[i];
    }
    std::ostringstream t; t << "write:" << count << ':' << hash; trace.push_back(t.str());
    errno = plan.write_errno;
    return plan.write > 0 ? std::min<ssize_t>(plan.write, count) : plan.write;
}
static void model_warning(const char *text) {
    trace.push_back(std::string("warn:") + text + ':' + std::to_string(errno));
    errno = EDOM;
}
#define pread model_pread
#define write model_write
#define swoole_sys_warning model_warning
namespace original {
#include "original.inc"
}
namespace selected {
#include "selected.inc"
}
#undef pread
#undef write
struct Observation {
    ssize_t result;
    off_t offset;
    int error;
    std::vector<std::string> calls;
    bool operator==(const Observation &o) const {
        return result == o.result && offset == o.offset && error == o.error && calls == o.calls;
    }
};
static Observation run(bool rust, size_t count, off_t offset) {
    trace.clear(); read_calls = write_calls = 0; buffer = nullptr; errno = E2BIG;
    ssize_t result = rust ? selected::swoole_sendfile(31, 19, &offset, count)
                          : original::swoole_sendfile(31, 19, &offset, count);
    const int error = errno;
    if (read_calls != 1 || write_calls > 1) std::abort();
    return {result, offset, error, trace};
}
int main() {
    size_t cases = 0;
    for (size_t count : {size_t(0), size_t(1), size_t(7), size_t(65535), size_t(65536), size_t(65537), std::numeric_limits<size_t>::max()})
    for (off_t offset : {off_t(0), off_t(17)})
    for (ssize_t read : {ssize_t(-2), ssize_t(-1), ssize_t(0), ssize_t(1), ssize_t(7), ssize_t(65536)})
    for (ssize_t write : {ssize_t(-2), ssize_t(-1), ssize_t(0), ssize_t(1), ssize_t(4), ssize_t(65536)})
    for (int error : {0, EINTR, EAGAIN, EWOULDBLOCK, EIO}) {
        plan = {read, write, error, error};
        auto native = run(false, count, offset);
        auto rust = run(true, count, offset);
        if (!(native == rust)) { std::cerr << "mismatch " << cases << '\n'; return 1; }
        std::cout << cases++ << '\t' << count << '\t' << offset << '\t' << read << '\t' << write << '\t' << error
                  << '\t' << native.result << '\t' << native.offset << '\t' << native.error;
        for (auto &t : native.calls) std::cout << '\t' << t;
        std::cout << '\n';
    }
    std::cout << "PASS\t" << cases << '\n';
}
