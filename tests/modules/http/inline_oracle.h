#pragma once
#include "swoole_server.h"
#include "swoole_static_handler.h"
#include "swoole_rs_http.h"
#include <stdexcept>
#define INLINE_ORACLE(ns) namespace ns { \
struct Server { std::string root; const std::string &get_document_root() const { return root; } }; \
inline unsigned random_calls = 0; inline size_t random_length = 0; inline bool random_throws = false; \
inline void swoole_random_string(std::string &text, size_t count) { ++random_calls; random_length = count; if (random_throws) throw std::runtime_error("rng failed"); text.append(count, 'r'); } \
struct StaticHandler { \
    Server *serv; std::string boundary, content_type, mime = "text/plain"; std::vector<int> tasks; \
    char filename[PATH_MAX] = {}; size_t l_filename = 0; bool last = false; int status_code = 299; \
    explicit StaticHandler(Server *server): serv(server) {} \
    const std::string &get_mimetype() const { return mime; } \
    bool catch_error(); bool is_absolute_path(); bool is_located_in_document_root(); \
    const std::string &get_boundary(); const std::string &get_content_type(); \
}; }
INLINE_ORACLE(original_inline)
INLINE_ORACLE(candidate_inline)
#undef INLINE_ORACLE
