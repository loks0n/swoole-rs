#include <cstdint>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include <fstream>
#include <iostream>
#include <sstream>
#include "swoole_rs_clients.h"
#define SW_API
#define SW_DNS_SERVER_PORT 53
static unsigned warnings;
#define swoole_sys_warning(...) (++warnings)
struct {std::string dns_resolvconf_path;struct {std::string host;int port=0;}dns_server;} SwooleG;
// NATIVE_INTEGER
// DECLARATIONS
namespace BODY_NAMESPACE {
struct Address {static bool verify_port(int port,bool for_connect=false);};
// ACTUAL_PORT
void swoole_set_dns_server(const std::string&);
// ACTUAL_BODY
static std::string snapshot(bool result){std::ostringstream out;out<<result<<":"<<errno<<":"<<warnings<<":"<<SwooleG.dns_server.port<<":"<<SwooleG.dns_server.host;return out.str();}
static std::string endpoint(const std::string&text){SwooleG.dns_server.host="initial";SwooleG.dns_server.port=42;errno=17;warnings=0;swoole_set_dns_server(text);return snapshot(true);}
static std::string config(const std::string&text,const std::string&path,bool present){
    if(present){std::ofstream file(path,std::ios::binary);file.write(text.data(),text.size());}
    SwooleG.dns_resolvconf_path=present?path:path+".missing";SwooleG.dns_server.host="initial";SwooleG.dns_server.port=42;errno=17;warnings=0;
    bool result=swoole_load_resolv_conf();return snapshot(result);
}
} // BODY_NAMESPACE
// DRIVER
