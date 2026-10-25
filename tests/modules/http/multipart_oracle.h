#pragma once
#include "swoole_http.h"
#include "swoole_rs_http.h"
#include <iostream>
#include <random>
#include <stdexcept>
#include <cstdarg>
#define MULTIPART_ORACLE(ns) namespace ns { \
struct Request; inline Request *observed=nullptr; inline std::vector<std::string> events; inline size_t write_count=0;inline bool real_stdio=false,throw_append=false; \
inline std::string snapshot(); \
struct Buffer { size_t length=0,offset=7,size=512;char *str=nullptr;void append(const char *,size_t n){events.push_back("append:"+std::to_string(n)+":"+snapshot());if(throw_append)throw std::bad_alloc();length+=n;}void clear(){events.push_back("clear:"+snapshot());length=offset=0;} }; \
using String=Buffer; \
struct multipart_parser {void *data=nullptr;FILE *fp=nullptr;}; \
struct FormData {Buffer *multipart_buffer_;size_t upload_filesize=0,upload_max_filesize=0;multipart_parser *multipart_parser_;}; \
struct Request {FormData *form_data_;uint32_t max_length_=0;unsigned excepted=0,unavailable=0,too_large=0;bool parse_multipart_data(Buffer *);}; \
inline std::string snapshot(){return std::to_string(observed->excepted)+","+std::to_string(observed->unavailable)+","+std::to_string(observed->too_large)+","+std::to_string(observed->form_data_->upload_filesize);} \
inline size_t multipart_fwrite(const void *data,size_t size,size_t count,FILE *file){events.push_back("write:"+std::to_string(count)+":"+snapshot());if(real_stdio)return ::fwrite(data,size,count,file);errno=EAGAIN;return write_count;} \
inline int multipart_fclose(FILE *file){events.push_back("close:"+snapshot());if(real_stdio)return ::fclose(file);errno=ENOSPC;return 0;} \
inline void multipart_warning(const char *){events.push_back("warning:"+snapshot()+":"+std::to_string(errno));} \
inline ssize_t parser_result=0;inline unsigned parser_excepted=0; \
inline ssize_t multipart_parser_execute(multipart_parser *,const char *,size_t n){events.push_back("parse:"+std::to_string(n)+":"+snapshot());observed->excepted=parser_excepted;errno=EIO;return parser_result;} \
inline int multipart_parser_error_msg(multipart_parser *,char *data,size_t size){events.push_back("error-message:"+snapshot());snprintf(data,size,"ordinary parser error");return 21;} \
inline void multipart_log(int,int,const char *format,...){char text[512];va_list arguments;va_start(arguments,format);vsnprintf(text,sizeof(text),format,arguments);va_end(arguments);events.push_back("log:"+std::string(text)+":"+snapshot());} \
inline Buffer *sw_tg_buffer(){static char data[512];static Buffer buffer;buffer.str=data;buffer.length=0;return &buffer;} \
}
MULTIPART_ORACLE(upstream_multipart)
MULTIPART_ORACLE(candidate_multipart)
#undef MULTIPART_ORACLE
#define fwrite multipart_fwrite
#define fclose multipart_fclose
#undef swoole_sys_warning
#define swoole_sys_warning multipart_warning
#undef swoole_error_log
#define swoole_error_log multipart_log
