#pragma once
#include "swoole_static_handler.h"
#include "swoole_rs_http.h"
#include <iostream>
#include <stdexcept>
#define TASKS_ORACLE(ns) namespace ns { \
using String=swoole::String; \
inline std::vector<std::string> trace;inline bool record_trace=true; \
struct Server {std::shared_ptr<std::vector<std::string>> http_index_files;bool http_autoindex=false;}; \
struct StaticHandler { \
 struct task_t {off_t offset;size_t length;char part_header[SW_HTTP_SERVER_PART_HEADER];}; \
 inline static StaticHandler *last_core=nullptr; \
 Server *serv;std::vector<task_t> tasks;std::string end_part,content_type,request_url,original_url,dir_path,index_file; \
 std::set<std::string> dir_files;int status_code=200;std::string boundary="fixed-boundary",mime="text/plain";size_t content_length=0,filesize=100; \
 StaticHandler(Server *s,const char *url,size_t length):serv(s),request_url(url,length),original_url(url,length){last_core=this;} \
 bool get_dir_files(){return false;}bool try_serve_index_file(){return true;}size_t make_index_page(String *){return 0;} \
 bool is_dir()const{return false;}bool has_index_file()const{return false;}bool is_enabled_auto_index()const{return false;} \
 const char *get_filename()const{return "/virtual/normal-file";}bool set_filename(const std::string &){return true;} \
 bool try_serve(){return true;}static std::string get_date(){return "date";}std::string get_date_last_modified()const{return "modified";}bool is_modified(const std::string &)const{return false;} \
 size_t get_content_length()const{return content_length;}size_t get_filesize()const{return filesize;} \
 const std::string &get_mimetype()const{if(record_trace)trace.emplace_back("mime");return mime;} \
 const std::string &get_boundary(){if(record_trace)trace.emplace_back("boundary");return boundary;} \
 const std::string &get_content_type();const std::string &get_end_part(){return end_part;} \
 bool is_modified_range(const std::string &value){if(record_trace)trace.emplace_back("date:"+value);return value=="modified";} \
 void parse_range(const char *,const char *); \
}; \
}
TASKS_ORACLE(upstream_tasks)
TASKS_ORACLE(candidate_tasks)
#undef TASKS_ORACLE
