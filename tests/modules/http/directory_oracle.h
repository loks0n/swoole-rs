#pragma once
#include "swoole_server.h"
#include "swoole_static_handler.h"
#include "swoole_rs_http.h"
#include <dirent.h>
#include <iostream>
#include "index_buffer.h"
#define DIRECTORY_ORACLE(ns) namespace ns { \
using String=IndexBuffer; \
inline std::vector<std::string> names,trace;inline bool record_trace=true; \
struct DIR {size_t next=0;struct dirent entry{};}; \
inline DIR *opendir(const char *filename){if(record_trace)trace.emplace_back(std::string("open:")+filename);return new DIR();} \
inline struct dirent *readdir(DIR *dir){if(dir->next==names.size()){if(record_trace)trace.emplace_back("end");return nullptr;}auto &name=names[dir->next++];if(record_trace)trace.emplace_back("read:"+name);memcpy(dir->entry.d_name,name.data(),name.size());dir->entry.d_name[name.size()]=0;return &dir->entry;} \
inline int closedir(DIR *dir){if(record_trace)trace.emplace_back("close");delete dir;return 0;} \
struct Server {std::shared_ptr<std::vector<std::string>> http_index_files;bool http_autoindex=false;}; \
struct StaticHandler { \
 Server *serv;std::string request_url,original_url,dir_path,index_file;std::set<std::string> dir_files;int status_code=200;char filename[128]="/private/normal-directory"; \
 std::vector<int> tasks;std::string text="normal"; \
 StaticHandler(Server *s,const char *url,size_t length):serv(s),request_url(url,length),original_url(url,length),dir_path(url,length){} \
 bool get_dir_files();bool try_serve_index_file();size_t make_index_page(String *); \
 bool is_dir()const{return true;}bool has_index_file()const{return !index_file.empty();}bool is_enabled_auto_index()const{return serv->http_autoindex;} \
 const char *get_filename()const{return filename;}bool set_filename(const std::string &name){if(record_trace)trace.emplace_back("select:"+name);return true;} \
 bool try_serve(){return true;}static std::string get_date(){return "date";}std::string get_date_last_modified()const{return "modified";}bool is_modified(const std::string &)const{return false;} \
 void parse_range(const char *,const char *){}auto &get_tasks(){return tasks;}size_t get_content_length()const{return 123;}size_t get_filesize()const{return 123;} \
 const std::string &get_mimetype()const{return text;}const std::string &get_content_type(){return text;}const std::string &get_end_part(){return text;} \
}; \
std::string intersection(const std::vector<std::string> &,std::set<std::string> &); \
}
DIRECTORY_ORACLE(upstream_directory)
DIRECTORY_ORACLE(candidate_directory)
#undef DIRECTORY_ORACLE
