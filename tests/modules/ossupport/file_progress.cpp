// SPDX-License-Identifier: Apache-2.0
// Exact extracted native methods, controlled syscall returns, then real private IO.
#include "swoole_rs_ossupport.h"
#include <algorithm>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#include <unistd.h>
#include <sys/stat.h>
static_assert(sizeof(swr_v1_os_file_io_state) == (sizeof(size_t) == 8 ? 16 : 8), "cursor ABI");
struct Result { ssize_t n; int error; };
static std::vector<Result> script;
static std::vector<std::string> trace;
static size_t at;
static char *base;
static bool real_io;
static ssize_t effect(const char *op, int fd, void *p, size_t n, off_t offset) {
    std::ostringstream t;
    t << op << ':' << (static_cast<char *>(p) - base) << ':' << n << ':' << offset;
    trace.push_back(t.str());
    if (real_io) {
        if (!std::strcmp(op, "pread")) return ::pread(fd, p, n, offset);
        if (!std::strcmp(op, "pwrite")) return ::pwrite(fd, p, n, offset);
        return ::write(fd, p, n);
    }
    const auto r = at < script.size() ? script[at++] : Result{0, EIO};
    errno = r.error;
    const ssize_t result = r.n > 0 ? std::min<ssize_t>(r.n, n) : r.n;
    if (result > 0 && !std::strcmp(op, "pread")) std::memset(p, 'R', result);
    return result;
}
static void warning(const char *format, int, const void *p, size_t remaining, size_t offset) {
    std::ostringstream t;
    t << (std::strncmp(format, "pread", 5) == 0 ? "warn-read:" : "warn-write:")
      << (static_cast<const char *>(p) - base) << ':' << remaining << ':' << offset << ':' << errno;
    trace.push_back(t.str());
    errno = EDOM; // A native logging effect may change errno; do not restore it.
}
#define swoole_sys_warning(...) warning(__VA_ARGS__)
#define DECLARE_FILE \
class File { \
public: \
    int fd_; int flags_; \
    enum { APPEND = O_APPEND }; \
    File(int fd, int flags) : fd_(fd), flags_(flags) {} \
    ssize_t write(const void *p, size_t n) const { return effect("write", fd_, const_cast<void *>(p), n, -1); } \
    ssize_t pwrite(const void *p, size_t n, off_t o) const { return effect("pwrite", fd_, const_cast<void *>(p), n, o); } \
    ssize_t pread(void *p, size_t n, off_t o) const { return effect("pread", fd_, p, n, o); } \
    size_t write_all(const void *, size_t) const; \
    size_t read_all(void *, size_t) const; \
};
namespace original {
#include "return-code.inc"
DECLARE_FILE
// Generated from exact pinned src/os/file.cc; no rewriting within the bodies.
#include "original.inc"
}
namespace selected {
DECLARE_FILE
#include "selected.inc"
}
struct Observation {
    size_t total;
    int error;
    std::vector<std::string> calls;
    std::string bytes;
    bool operator==(const Observation &o) const {
        return total == o.total && error == o.error && calls == o.calls && bytes == o.bytes;
    }
};
template<class F> static Observation run(int mode, size_t length) {
    char bytes[16]; std::memset(bytes, 'X', sizeof(bytes)); base = bytes;
    trace.clear(); at = 0; errno = E2BIG;
    F f(-1, mode == 2 ? O_APPEND : 0);
    const size_t n = mode == 0 ? f.read_all(bytes, length) : f.write_all(bytes, length);
    const int error = errno;
    return {n, error, trace, std::string(bytes, sizeof(bytes))};
}
template<class F> static std::string real_case(const std::string &path) {
    int fd = ::open(path.c_str(), O_RDWR | O_CREAT | O_TRUNC, 0600);
    if (fd < 0) throw std::runtime_error("private open");
    char data[] = "abcdef"; base = data; trace.clear();
    F normal(fd, 0);
    if (normal.write_all(data, 6) != 6 || ::lseek(fd, 0, SEEK_CUR) != 0) throw std::runtime_error("pwrite offset");
    char bytes[16] = {}; base = bytes;
    if (normal.read_all(bytes, 9) != 6 || std::string(bytes, 6) != "abcdef" || ::lseek(fd, 0, SEEK_CUR) != 0) throw std::runtime_error("partial EOF");
    ::close(fd);
    fd = ::open(path.c_str(), O_WRONLY | O_APPEND);
    if (fd < 0) throw std::runtime_error("append open");
    F append(fd, O_APPEND); base = data;
    if (append.write_all(data, 2) != 2 || ::lseek(fd, 0, SEEK_CUR) != 8) throw std::runtime_error("append offset");
    ::close(fd);
    fd = ::open(path.c_str(), O_RDONLY); std::memset(bytes, 0, sizeof(bytes));
    const auto n = ::read(fd, bytes, sizeof(bytes)); ::close(fd); ::unlink(path.c_str());
    if (n != 8 || std::string(bytes, 8) != "abcdefab") throw std::runtime_error("real bytes");
    F invalid(-1, 0); base = bytes; trace.clear(); errno = 0;
    if (invalid.read_all(bytes, 1) != 0 || trace.size() != 2 || trace[1] != "warn-read:0:1:0:" + std::to_string(EBADF)) throw std::runtime_error("EBADF read");
    trace.clear(); errno = 0;
    if (invalid.write_all(bytes, 1) != 0 || trace.size() != 2 || trace[1] != "warn-write:0:1:0:" + std::to_string(EBADF)) throw std::runtime_error("EBADF write");
    return "pwrite-offset/partial-EOF/append-write/exact-bytes/EBADF-read-write";
}
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    const Result events[] = {{1, EIO}, {2, EDOM}, {0, EINTR}, {0, EIO}, {-1, EINTR}, {-1, EAGAIN}, {-1, EWOULDBLOCK}, {-1, EIO}};
    size_t cases = 0;
    for (int mode = 0; mode < 3; ++mode) for (size_t len : {size_t(0), size_t(1), size_t(2), size_t(5), size_t(7)}) {
        for (const auto a : events) for (const auto b : events) for (const auto c : events) {
            script = {a,b,c};
            const auto native = run<original::File>(mode, len);
            const auto rust = run<selected::File>(mode, len);
            if (!(native == rust)) { std::cerr << "mismatch " << cases << '\n'; return 1; }
            std::cout << cases++ << '\t' << mode << '\t' << len << '\t' << native.total << '\t' << native.error;
            for (const auto &t : native.calls) std::cout << '\t' << t;
            std::cout << '\n';
        }
    }
    real_io = true;
    const auto native = real_case<original::File>(std::string(argv[1]) + "/original-file");
    const auto rust = real_case<selected::File>(std::string(argv[1]) + "/selected-file");
    if (native != rust) return 1;
    std::cout << "real-private-io\t" << native << "\nPASS\t" << cases << "\n";
}
