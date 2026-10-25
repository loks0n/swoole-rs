#pragma once
#include "swoole_server.h"
#include "swoole_websocket.h"
#include "swoole_http2.h"
#include "swoole_rs_http.h"
#include <set>
#include <stdexcept>
#define DISPATCH_ORACLE(ns) namespace ns { \
struct HttpProxy { std::string host, username, password; int port = 0; \
    static inline HttpProxy *last_created = nullptr; HttpProxy() { last_created=this; } \
    static HttpProxy *create(const std::string &,int,const std::string &,const std::string &); }; \
struct Protocol {}; struct PacketLength { int seen=0; }; struct RecvData {}; \
struct Connection { uint8_t websocket_status=0,http2_stream=0; }; \
struct Socket { void *object; }; inline unsigned ws_calls=0,h2_calls=0,error_calls=0,dispatch_calls=0; \
inline const Protocol *seen_proto=nullptr; inline Socket *seen_socket=nullptr; inline const RecvData *seen_data=nullptr; \
inline void reset() { ws_calls=h2_calls=error_calls=dispatch_calls=0;seen_proto=nullptr;seen_socket=nullptr;seen_data=nullptr; } \
namespace websocket { constexpr int STATUS_HANDSHAKE=2; \
inline ssize_t get_package_length(const Protocol *p,Socket *s,PacketLength *pl){++ws_calls;seen_proto=p;seen_socket=s;pl->seen=11;return -11;} \
inline int dispatch_frame(const Protocol *p,Socket *s,const RecvData *d){++ws_calls;seen_proto=p;seen_socket=s;seen_data=d;return -22;} } \
namespace http2 { inline ssize_t get_frame_length(const Protocol *p,Socket *s,PacketLength *pl){++h2_calls;seen_proto=p;seen_socket=s;pl->seen=33;return 44;} } \
inline void protocol_status_error(Socket *s,const Connection *) { ++error_calls;seen_socket=s; } \
struct Server { std::shared_ptr<std::vector<std::string>> http_index_files; bool http_autoindex=false; \
static int dispatch_task(const Protocol *p,Socket *s,const RecvData *d){++dispatch_calls;seen_proto=p;seen_socket=s;seen_data=d;return 55;} }; \
struct StaticHandler { Server *serv;std::set<std::string> dir_files;std::string index_file="previous-index"; \
bool directory=false,scan_ok=false,filename_ok=false;unsigned scan_calls=0,filename_calls=0;char selected[512]={};size_t selected_length=0; \
explicit StaticHandler(Server *s):serv(s){} bool is_dir()const{return directory;} \
bool get_dir_files(){++scan_calls;return scan_ok;} bool has_index_file()const{return !index_file.empty();} bool is_enabled_auto_index()const{return serv->http_autoindex;} \
bool set_filename(const std::string &name){++filename_calls;selected_length=name.size();std::memcpy(selected,name.data(),name.size());return filename_ok;} \
bool try_serve_index_file(); }; \
std::string intersection(const std::vector<std::string>&,std::set<std::string>&); \
const char *get_status_message(int);ssize_t get_package_length(const Protocol *,Socket *,PacketLength *);uint8_t get_package_length_size(Socket *);int dispatch_frame(const Protocol *,Socket *,const RecvData *); \
}
DISPATCH_ORACLE(upstream_dispatch)
DISPATCH_ORACLE(candidate_dispatch)
#undef DISPATCH_ORACLE
