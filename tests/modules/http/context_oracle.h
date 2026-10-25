#pragma once
#include "swoole_static_handler.h"
#include "swoole_rs_http_context.h"
#include "index_buffer.h"
#include <dirent.h>
#include <regex>
#include <iostream>
#include <unordered_map>
#define CONTEXT_EFFECTS(ns) namespace ns { \
using String=IndexBuffer;using RewriteRule=swoole::http_server::RewriteRule; \
inline std::vector<std::string> names,trace;inline std::string mime="text/plain"; \
inline size_t file_size=100;inline time_t file_time=1700000000;inline std::string directory_name,link_name,canonical_name; \
struct DIR {size_t next=0;struct dirent entry{};}; \
inline DIR *opendir(const char *filename){trace.emplace_back(std::string("open:")+filename);return new DIR();} \
inline struct dirent *readdir(DIR *dir){if(dir->next==names.size()){trace.emplace_back("end");return nullptr;}auto &name=names[dir->next++];trace.emplace_back("read:"+name);memcpy(dir->entry.d_name,name.data(),name.size());dir->entry.d_name[name.size()]=0;return &dir->entry;} \
inline int closedir(DIR *dir){trace.emplace_back("close");delete dir;return 0;} \
inline int lstat(const char *path,struct stat *value){trace.emplace_back(std::string("stat:")+path);memset(value,0,sizeof(*value));value->st_size=file_size;value->st_mode=link_name==path?S_IFLNK:directory_name==path?S_IFDIR:S_IFREG;set_mtime(value,file_time);return 0;} \
inline char *realpath(const char *input,char *output){trace.emplace_back(std::string("canonical:")+input);strcpy(output,canonical_name.empty()?input:canonical_name.c_str());return output;} \
inline void swoole_random_string(std::string &value,size_t count){trace.emplace_back("random:"+std::to_string(count));value.append(count,'x');} \
inline void swoole_random_string(char *value,size_t count){trace.emplace_back("random:"+std::to_string(count));memset(value,'x',count);value[count]=0;} \
namespace mime_type {inline bool exists(const std::string &path){trace.emplace_back("mime-exists:"+path);return true;} \
inline const std::string &get(const std::string &path){trace.emplace_back("mime:"+path);return mime;}} \
}
inline void set_mtime(struct stat *value,time_t mtime){
#ifdef __MACH__
 value->st_mtimespec.tv_sec=mtime;
#else
 value->st_mtim.tv_sec=mtime;
#endif
}
CONTEXT_EFFECTS(upstream_context)
CONTEXT_EFFECTS(candidate_context)
#undef CONTEXT_EFFECTS
