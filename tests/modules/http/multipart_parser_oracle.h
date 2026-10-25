#pragma once
#include "swoole_http.h"
#include "swoole_rs_http.h"
#include "thirdparty/multipart_parser.h"
#include <cerrno>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <unistd.h>
#include <vector>
#define PARSER_FIXTURE(ns) namespace ns { \
struct String {std::vector<char> bytes;char *str;size_t size,length=0,offset=0;String():bytes(65536,'?'),str(bytes.data()),size(bytes.size()){} \
void reserve(size_t n){bytes.resize(n,'?');str=bytes.data();size=n;} \
void append(const char *p,size_t n){std::string copy(p,n);if(length+n+1>size)reserve((length+n+1)*2);if(n)memcpy(str+length,copy.data(),n);length+=n;str[length]=0;}void clear(){length=offset=0;} }; \
struct FormData {String *multipart_buffer_,*upload_tmpfile;const char *current_header_name=nullptr;size_t current_header_name_len=0;std::string upload_tmpfile_fmt_;size_t upload_filesize=0,upload_max_filesize=0;multipart_parser *multipart_parser_;}; \
struct Request {FormData *form_data_;uint32_t max_length_=0,header_length_=0;size_t content_length_=0;unsigned excepted=0,unavailable=0,too_large=0,multipart_header_parsed=0,tried_to_dispatch=0;bool parse_multipart_data(String *);}; \
using ParseCookieCallback=std::function<bool(char *,size_t,char *,size_t)>; \
extern std::vector<std::string> files;extern std::vector<std::string> logs; \
inline String *sw_tg_buffer(){static String value;return &value;} \
inline int swoole_tmpfile(char *path){int fd=mkstemp(path);if(fd>=0)files.emplace_back(path);return fd;} \
inline void log(){logs.push_back("log");} }
PARSER_FIXTURE(upstream_multipart_parser)
PARSER_FIXTURE(candidate_multipart_parser)
#undef PARSER_FIXTURE
