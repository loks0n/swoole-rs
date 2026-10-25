#pragma once
#include "swoole_server.h"
#include "swoole_static_handler.h"
#include "swoole_rs_http.h"
#include <chrono>
#include <iostream>
#include <stdexcept>
#include <unistd.h>
#include <sys/stat.h>
#include <fstream>
struct PathWorkload { std::string root,url;bool index=false,autoindex=false,location_miss=false; };
#define PATH_BENCH(ns) namespace ns { \
namespace mime_type = ::swoole::mime_type; \
struct Server; \
struct StaticHandler { Server *serv;std::string request_url,original_url,dir_path;size_t l_filename=0;char filename[PATH_MAX];struct stat file_stat;bool last=false;int status_code=SW_HTTP_OK; \
 StaticHandler(Server *server,const std::string &url):serv(server),request_url(url),original_url(url){} \
 bool try_serve();bool get_absolute_path();bool catch_error(); \
 bool is_link()const{return S_ISLNK(file_stat.st_mode);}bool is_dir()const{return S_ISDIR(file_stat.st_mode);}bool is_file()const{return S_ISREG(file_stat.st_mode);} \
 bool is_absolute_path();bool is_located_in_document_root(); \
}; \
struct Server { std::string root;std::shared_ptr<std::unordered_set<std::string>> locations;std::shared_ptr<std::vector<std::string>> http_index_files;bool http_autoindex; \
 explicit Server(const PathWorkload &work):root(work.root),locations(std::make_shared<std::unordered_set<std::string>>()),http_autoindex(work.autoindex){if(work.index)http_index_files=std::make_shared<std::vector<std::string>>(1,"index.html");if(work.location_miss)locations->insert("/elsewhere/");} \
 const std::string &get_document_root()const{return root;}bool apply_rewrite_rules(StaticHandler *){return false;} \
}; \
size_t url_decode(char *,size_t); \
}
PATH_BENCH(upstream_path)
PATH_BENCH(candidate_path)
#undef PATH_BENCH
