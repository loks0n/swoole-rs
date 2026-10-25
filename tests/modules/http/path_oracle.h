#pragma once
#include "swoole_server.h"
#include "swoole_static_handler.h"
#include "swoole_rs_http.h"
#include <stdexcept>
#include <sys/stat.h>
struct PathScenario {
    std::string url="/file.txt", root="/root", canonical="/root/file.txt", rewritten;
    std::unordered_set<std::string> locations;
    std::vector<mode_t> modes{S_IFREG|0644};
    std::vector<bool> stat_ok{true};
    bool canonical_ok=true,mime=true,index=false,autoindex=false,initial_last=false;
};
#define PATH_ORACLE(ns) namespace ns { \
inline const PathScenario *active=nullptr; inline unsigned stat_calls=0; inline std::vector<std::string> trace; \
inline int path_lstat(const char *path,struct stat *value) { trace.push_back("stat:"+std::string(path));size_t at=std::min(size_t(stat_calls++),active->stat_ok.size()-1); \
    if(!active->stat_ok[at]) { errno=ENOENT;return -1; } std::memset(value,0,sizeof(*value));value->st_mode=active->modes[std::min(at,active->modes.size()-1)];return 0; } \
inline char *path_realpath(const char *path,char *output) { trace.push_back("realpath:"+std::string(path));if(!active->canonical_ok) { errno=ENOTDIR;return nullptr; } \
    std::memcpy(output,active->canonical.c_str(),active->canonical.size()+1);return output; } \
namespace mime_type { inline bool exists(const char *path) { trace.push_back("mime:"+std::string(path));return active->mime; } } \
struct Server; \
struct StaticHandler { Server *serv;std::string request_url,dir_path="old-directory";size_t l_filename=12;char filename[PATH_MAX];struct stat file_stat;bool last;int status_code=SW_HTTP_OK; \
    StaticHandler(Server *server,const PathScenario &config):serv(server),request_url(config.url),last(config.initial_last) { std::memset(filename,0xa5,sizeof(filename));std::memcpy(filename,"old-filename",13);std::memset(&file_stat,0x4b,sizeof(file_stat)); } \
    bool try_serve();bool get_absolute_path();bool set_filename(const std::string &); \
    bool catch_error(); \
    bool is_link() const { return S_ISLNK(file_stat.st_mode); }bool is_dir() const { return S_ISDIR(file_stat.st_mode); }bool is_file() const { return S_ISREG(file_stat.st_mode); } \
    bool is_absolute_path(); \
    bool is_located_in_document_root(); \
}; \
struct Server { std::string root;std::shared_ptr<std::unordered_set<std::string>> locations;std::shared_ptr<std::vector<std::string>> http_index_files;bool http_autoindex; \
    explicit Server(const PathScenario &config):root(config.root),locations(std::make_shared<std::unordered_set<std::string>>(config.locations)),http_autoindex(config.autoindex) { if(config.index)http_index_files=std::make_shared<std::vector<std::string>>(1,"index.html"); } \
    const std::string &get_document_root() const { return root; } \
    bool apply_rewrite_rules(StaticHandler *handler) { trace.push_back("rewrite");if(!active->rewritten.empty())handler->request_url=active->rewritten;return !active->rewritten.empty(); } \
}; \
size_t url_decode(char *,size_t); \
}
PATH_ORACLE(upstream_path)
PATH_ORACLE(candidate_path)
#undef PATH_ORACLE
// Route native filesystem calls without global struct-stat ADL ambiguity.
#define lstat path_lstat
#define realpath path_realpath
