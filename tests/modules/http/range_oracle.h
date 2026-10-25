#pragma once
#include "swoole_server.h"
#include "swoole_static_handler.h"
#include "swoole_rs_http.h"
#include <stdexcept>
#define RANGE_ORACLE(namespace_name) namespace namespace_name { \
class StaticHandler { public: \
    struct task_t { off_t offset; size_t length; char part_header[SW_HTTP_SERVER_PART_HEADER]; }; \
    std::vector<task_t> tasks; std::string end_part; size_t content_length = 0; \
    int status_code = SW_HTTP_OK; size_t filesize; unsigned date_calls = 0; \
    std::string boundary = "fixed-boundary", mime = "text/plain"; \
    explicit StaticHandler(size_t size): filesize(size) {} \
    size_t get_filesize() const { return filesize; } \
    const std::string &get_boundary() { return boundary; } \
    const std::string &get_mimetype() const { return mime; } \
    bool is_modified_range(const std::string &value) { ++date_calls; return value == "modified"; } \
    void parse_range(const char *, const char *); \
}; }
RANGE_ORACLE(upstream_range)
RANGE_ORACLE(candidate_range)
#undef RANGE_ORACLE
