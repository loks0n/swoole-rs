#pragma once
#include "swoole_http.h"
#include "swoole_http2.h"
#include "swoole_rs_http.h"
#include <stdexcept>
#define FRAME_ORACLE(namespace_name) namespace namespace_name { \
const char *get_method_string(int); \
struct Buffer { char *str = nullptr; size_t length = 0; off_t offset = 0; std::string storage; \
    void sync() { str = storage.data(); length = storage.size(); } \
    void append(const char *input) { storage += input; sync(); } \
    bool append_random_bytes(size_t count, bool) { storage.append(count, 'A'); sync(); return true; } \
    void clear() { storage.clear(); offset = 0; sync(); } \
}; \
struct Request { \
    uint8_t method = 0, version = 0; \
    unsigned excepted = 0, known_length = 0; \
    uint32_t url_offset_ = 0, url_length_ = 0, request_line_length_ = 0, header_length_ = 0; \
    uint64_t content_length_ = 0; Buffer *buffer_; \
    int get_protocol(); int get_header_length(); int get_chunked_body_length(); \
    bool has_expect_header() const; std::string get_header(const char *) const; \
}; }
FRAME_ORACLE(upstream_frame)
FRAME_ORACLE(candidate_frame)
#undef FRAME_ORACLE
