#pragma once
#include "swoole_http.h"
#include "swoole_rs_http.h"
#include <cerrno>
#include <iostream>
#include <stdexcept>
#include <vector>
#define MULTIPART_HEADERS(ns) namespace ns { \
struct Request; struct multipart_parser; \
extern Request *observed; extern multipart_parser *parser; extern std::vector<std::string> events; \
extern int append_attempt,fail_append,file_failure; \
std::string snapshot(); inline void (*append_hook)() = nullptr; \
struct Buffer { std::string bytes; size_t length = 0; char *str = nullptr; void append(const char *p,size_t n) {events.push_back("append:"+std::string(p,n)+":"+snapshot());if(append_attempt++==fail_append)throw std::bad_alloc();bytes.append(p,n);length=bytes.size();str=bytes.data();if(append_hook)append_hook();} }; \
struct String { std::vector<char> bytes; char *str; size_t size; String():bytes(65536,'?'),str(bytes.data()),size(bytes.size()) {} void reserve(size_t n){bytes.resize(n,'?');str=bytes.data();size=n;} }; \
struct FormData {Buffer *multipart_buffer_;const char *current_header_name;size_t current_header_name_len;String *upload_tmpfile;std::string upload_tmpfile_fmt_;size_t upload_filesize;}; \
struct Request {FormData *form_data_;unsigned excepted;size_t header_length_=0,content_length_=0;unsigned multipart_header_parsed=0,tried_to_dispatch=0;}; \
struct multipart_parser {void *data;FILE *fp;const char *boundary=nullptr;size_t boundary_length=0;}; \
using ParseCookieCallback=std::function<bool(char *,size_t,char *,size_t)>; \
String *sw_tg_buffer();void parse_cookie(const char *,size_t,const ParseCookieCallback &); \
int swoole_tmpfile(char *);FILE *multipart_fdopen(int,const char *);void multipart_warning(); }
MULTIPART_HEADERS(upstream_multipart_headers)
MULTIPART_HEADERS(candidate_multipart_headers)
#undef MULTIPART_HEADERS
