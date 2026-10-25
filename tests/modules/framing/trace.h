#pragma once
// Instrumented native boundary for differential policy traces. Both engines use
// this same fake IO/storage; core.py separately exercises actual native objects.
#include <algorithm>
#include <arpa/inet.h>
#include <cassert>
#include <cerrno>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <functional>
#include <iostream>
#include <string>
#include <vector>
#define sw_inline inline
#define SW_DATA_EOF_MAXLEN 8
#define SW_BUFFER_SIZE_STD 8192
#define SW_OK 0
#define SW_ERR -1
#define SW_CONTINUE 1
#define SW_CLOSE 3
#define SW_ERROR 4
#define SW_LOG_WARNING 1
#define SW_LOG_ERROR 2
#define SW_ERROR_PACKAGE_MALFORMED_DATA 3
#define SW_ERROR_PACKAGE_LENGTH_NOT_FOUND 4
#define SW_ERROR_PACKAGE_LENGTH_TOO_LARGE 5
#define SW_ERROR_INVALID_PARAMS 6
#define swoole_trace_log(...) ((void) 0)
using uchar = unsigned char;
using ulong_t = unsigned long;
extern std::string events;
extern bool allocation_failure;
inline void event(const std::string &s) { events += s + "|"; }
inline void message(const char *fmt, ...) {
    char b[512]; va_list args; va_start(args, fmt); vsnprintf(b, sizeof(b), fmt, args); va_end(args); event(b);
}
#define swoole_debug(...) message(__VA_ARGS__)
#define swoole_sys_warning(...) message(__VA_ARGS__)
#define swoole_error_log(level, code, ...) do { message("log:%d:%d", level, code); message(__VA_ARGS__); } while (0)
inline int swoole_pagesize() { return 4096; }
inline size_t swoole_size_align(size_t n, int p) { return n + (p - n % p); }
inline const char *swoole_strnstr(const char *p, size_t n, const char *d, size_t m) {
    if (!m || n < m) return nullptr;
    for (size_t i = 0; i <= n - m; i++) if (!memcmp(p + i, d, m)) return p + i;
    return nullptr;
}
namespace swoole {
using SessionId = int;
struct DataHead { int fd; uint32_t len; };
using StringExplodeHandler = std::function<int(const char *, size_t)>;
struct String {
    size_t length = 0, size; off_t offset = 0; char *str;
    std::vector<char> storage;
    explicit String(size_t n): size(n), storage(n) { str = storage.data(); }
    void extend(size_t n) { message("extend:%zu", n); if (allocation_failure) throw std::bad_alloc(); storage.resize(n); size = n; str = storage.data(); }
    void reduce(size_t n) { message("reduce:%zu", n); assert(n <= length); memmove(str, str + n, length - n); length -= n; offset = 0; }
    void clear() { event("clear"); length = offset = 0; }
    ssize_t split(const char *, size_t, const StringExplodeHandler &);
};
namespace network {
struct Address { const char *get_addr() { return "stub"; } int get_port() { return 7; } };
struct Socket {
    int fd = 23; bool removed = false, recv_wait = false, skip_recv = false;
    int *ssl = nullptr; Address info;
    std::vector<std::string> chunks; size_t chunk = 0, cursor = 0;
    int error = 0, caught = 0, calls = 0, mutate = 0;
    ssize_t recv(char *out, size_t n, int) {
        message("recv:%zu", n); assert(++calls < 100);
        if (mutate == 1) recv_wait = true;
        if (mutate == 2) removed = true;
        if (chunk == chunks.size()) { errno = EAGAIN; return error ? error : -1; }
        auto &s = chunks[chunk]; size_t got = std::min(n, s.size() - cursor);
        memcpy(out, s.data() + cursor, got); cursor += got;
        if (cursor == s.size()) { chunk++; cursor = 0; }
        return got;
    }
    int catch_read_error(int e) { message("catch:%d", e); return caught; }
    int get_peer_name(Address *) { event("peer"); return -1; }
};
}
}
inline int SSL_pending(int *n) { message("pending:%d", *n); return (*n)--; }
