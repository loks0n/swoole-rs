#pragma once
#include "swoole_http.h"
#include "swoole_rs_http.h"
#include <cerrno>
#include <stdexcept>
#include <vector>
#define HEADERS_ORACLE(namespace_name) namespace namespace_name { \
struct Request; \
struct Allocation { unsigned known,alive,chunked,nobody,parsed; uint64_t content; int error; }; \
extern Allocation events[32]; extern unsigned attempts; extern int fail_at; extern Request *observed; \
struct FormData { const char *multipart_boundary_buf = nullptr; uint32_t multipart_boundary_len = 0; FormData(); }; \
extern FormData *allocated[32]; extern unsigned owned; \
struct Buffer { char *str; size_t length; }; \
struct Request { unsigned known_length=0,keep_alive=0,chunked=0,nobody_chunked=0,header_parsed=0,excepted=0; \
    uint32_t request_line_length_=14,header_length_=0; uint64_t content_length_=0; Buffer *buffer_; FormData *form_data_=nullptr; void parse_header_info(); }; \
using ParseCookieCallback = std::function<bool(char *,size_t,char *,size_t)>; \
struct Scratch { std::vector<char> storage; char *str; size_t size; Scratch():storage(65536,'?'),str(storage.data()),size(storage.size()) {} \
    void reserve(size_t n) { storage.resize(n,'?');str=storage.data();size=n; } \
}; \
using String=Scratch; Scratch *sw_tg_buffer(); void parse_cookie(const char *,size_t,const ParseCookieCallback &); void reset(); }
HEADERS_ORACLE(upstream_headers)
HEADERS_ORACLE(candidate_headers)
#undef HEADERS_ORACLE
