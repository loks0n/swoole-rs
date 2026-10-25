#pragma once
#include "swoole_http.h"
#include "swoole_rs_http.h"
#include <iostream>
#include <stdexcept>
#include <vector>
#define REQUEST_LIFECYCLE_ORACLE(ns) namespace ns { \
struct Request;inline Request *observed=nullptr;inline std::vector<std::string> events;inline unsigned next_id=0;inline std::string snapshot(); \
struct String {std::vector<char> storage;char *str=nullptr;size_t length=0,size=0;unsigned id=++next_id; \
 explicit String(size_t capacity):storage(capacity,0),size(capacity){str=storage.data();events.emplace_back("new-buffer:"+std::to_string(id)+":"+snapshot());} \
 explicit String(const std::string &text):storage(text.size()+1,0),length(text.size()),size(storage.size()){str=storage.data();memcpy(str,text.data(),text.size());events.emplace_back("new-upload:"+std::to_string(id)+":"+snapshot());} \
 void append(const char *data,size_t count){events.emplace_back("append:"+std::to_string(count)+":"+snapshot());if(length+count>size){storage.resize(length+count);size=storage.size();str=storage.data();}memcpy(str+length,data,count);length+=count;} \
 ~String(){events.emplace_back("delete-buffer:"+std::to_string(id)+":"+snapshot());} \
}; \
struct multipart_parser {void *data=nullptr;FILE *fp=nullptr;}; \
struct FormData {const char *multipart_boundary_buf=nullptr;size_t multipart_boundary_len=0;multipart_parser *multipart_parser_=nullptr;String *multipart_buffer_=nullptr,*upload_tmpfile=nullptr;std::string upload_tmpfile_fmt_;size_t upload_max_filesize=0;~FormData(){events.emplace_back("delete-form:"+snapshot());}}; \
struct Server {std::string upload_tmp_dir;size_t upload_max_filesize=0;}; \
struct Request {String *buffer_=nullptr;FormData *form_data_=nullptr;size_t header_length_=0;bool init_multipart_parser(const Server *);void destroy_multipart_parser();~Request();}; \
inline std::string snapshot(){if(!observed)return "outside";auto *f=observed->form_data_;return std::string(observed->buffer_?std::to_string(observed->buffer_->id):"-")+":"+(f?(f->multipart_buffer_?std::to_string(f->multipart_buffer_->id):"-")+":"+(f->multipart_parser_?"parser":"-")+":"+(f->upload_tmpfile?std::to_string(f->upload_tmpfile->id):"-"):"no-form");} \
inline bool parse_multipart_boundary(const char *input,size_t length,size_t,char **boundary,int *count){events.emplace_back("boundary:"+std::string(input,length)+":"+snapshot());*boundary=const_cast<char*>(input);*count=static_cast<int>(length);return true;} \
inline int mt_parser_settings=0; \
inline multipart_parser *multipart_parser_init(const char *boundary,int length,const int *){events.emplace_back("parser-init:"+std::string(boundary,length)+":"+snapshot());return new multipart_parser();} \
inline void multipart_parser_free(multipart_parser *parser){events.emplace_back("free-parser:"+snapshot());delete parser;} \
inline int close_file(FILE *file){events.emplace_back("close-file:"+snapshot());return ::fclose(file);} \
inline int unlink_file(const char *file){events.emplace_back("unlink-virtual:"+std::string(file)+":"+snapshot());return 0;} \
inline void warning(const char *message){events.emplace_back("warning:"+std::string(message));} \
}
REQUEST_LIFECYCLE_ORACLE(upstream_request_lifecycle)
REQUEST_LIFECYCLE_ORACLE(candidate_request_lifecycle)
#undef REQUEST_LIFECYCLE_ORACLE
#undef swoole_warning
#define swoole_warning warning
#define fclose close_file
#define unlink unlink_file
