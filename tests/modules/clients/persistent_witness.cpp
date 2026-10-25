#include <algorithm>
#include <cstdint>
#include <cerrno>
#include <cstdio>
#include <string>
#include <vector>
#include <queue>
#include <unordered_map>
#include <set>
#include <functional>
#include <sstream>
#include <stdexcept>
#include <iostream>
#include "swoole_rs_clients.h"
#include "swoole_rs_clients_pool.h"
#define SW_FLAG_KEEP 256
#define SW_SOCK_SSL 512
#define SW_ERROR_INVALID_PARAMS 900
#define SW_ZEND_STR_TYPE 1
#define SW_ZEND_STR_ID 2
#define IS_NULL 0
#define IS_STRING 1
#define E_WARNING 1
#define E_ERROR 2
#define Z_OBJCE_P(z) 0
#define SW_Z8_OBJ_P(z) (z)
#define SW_ZSTR_KNOWN(n) (n)
#define ZVAL_IS_NULL(z) ((z)->kind==IS_NULL)
#define Z_LVAL_P(z) ((z)->number)
#define Z_TYPE_P(z) ((z)->kind)
#define Z_STRLEN_P(z) ((z)->bytes.size())
#define Z_STRVAL_P(z) ((z)->bytes.data())
#define ZEND_STRL(s) s,sizeof(s)-1
static std::vector<std::string> effects;
static std::function<std::string()> probe;
static std::function<void(const std::string&)> effect_hook;
static bool new_socket_missing,liveness;
static int next_identity,last_error;
static void observe(const std::string&what){effects.push_back(what+":"+(probe?probe():""));}
static void hook(const std::string&name){if(effect_hook)effect_hook(name);}
struct zval {
    int kind=IS_NULL;long number=0;std::string bytes;
    zval *type_value=nullptr,*id_value=nullptr,*socket_value=nullptr;void *client=nullptr;
};
static zval *sw_zend_read_property_ex(int,zval*object,int,int){observe("read-type");hook("read-type");return object->type_value;}
static zval *sw_zend_read_property_not_null_ex(int,zval*object,int,int){observe("read-id");hook("read-id");return object->id_value&&object->id_value->kind!=IS_NULL?object->id_value:nullptr;}
static void zend_update_property_long(int,zval*object,const char*name,size_t length,long value){observe("property:"+std::string(name,length)+":"+std::to_string(value));object->number=value;hook(std::string(name,length));}
static void php_swoole_fatal_error(int,const char*text){observe("fatal:"+std::string(text));hook("fatal");}
static void php_swoole_sys_error(int,const char*text){observe("sys-error:"+std::string(text));errno=91;hook("sys-error");}
static void swoole_set_last_error(int error){observe("last-error:"+std::to_string(error));last_error=error;}
static int php_swoole_client_get_type(long type){observe("get-type");return int(type&255);}
using SocketType=int;
struct Socket {int fd=42;static bool is_tcp(int type){return type==1;}bool check_liveness(){observe("liveness");hook("liveness");return liveness;}};
struct Address {static bool verify_port(int port){observe("verify-port");return port>=0&&port<=65535;}};
struct TimerNode {};
static TimerNode timer_node;
static int callable;
static void swoole_timer_del(TimerNode*){observe("timer-delete");hook("timer-delete");}
static void sw_callable_free(void*){observe("callable-free");hook("callable-free");}
static zval *client_get_zsocket(const zval*object){observe("get-zsocket");hook("get-zsocket");return object->socket_value;}
static void client_set_zsocket(const zval*object,zval*value){observe("set-zsocket");const_cast<zval*>(object)->socket_value=value;hook("set-zsocket");}
static void sw_zval_free(zval*){observe("zval-free");hook("zval-free");}
struct Transfer {char bytes[128]{};char *str=bytes;size_t size=128;};
static Transfer transfer;
static Transfer *sw_tg_buffer(){return &transfer;}
#define sw_snprintf snprintf
// DECLARATIONS
namespace BODY_NAMESPACE {
struct Client;
static std::set<Client*> live_clients;
static Client *subject=nullptr;
struct Client {
    Socket *socket=nullptr;Socket native_socket;
    TimerNode *timer=nullptr;struct {void *private_data_1=nullptr;} protocol;
    bool keep=false;uint32_t reuse_count=0;std::string server_id;int identity;
    Client(int,bool):identity(++next_identity){socket=new_socket_missing?nullptr:&native_socket;native_socket.fd=100+identity;live_clients.insert(this);subject=this;observe("new-client:"+std::to_string(identity));hook("new-client");}
    ~Client(){observe("delete-client:"+std::to_string(identity));hook("destructor");live_clients.erase(this);}
    int close(){observe("close");hook("close");return -1;}
    int enable_ssl_encrypt(){observe("ssl");hook("ssl");return -1;}
};
#ifdef SWR_CLIENTS_WITNESS_RUST_POOL
static SwooleRustClientPool long_connections;
#else
static std::unordered_map<std::string,std::queue<Client*>*> long_connections;
#endif
static std::vector<std::string> known_keys;
static void prepare_pool(const std::string&key,Client*seed,bool nonempty,Client*extra){
    known_keys.push_back(key);
#ifdef SWR_CLIENTS_WITNESS_RUST_POOL
    long_connections.push(key,seed);
    if(!nonempty&&long_connections.take(key)!=seed)throw std::runtime_error("empty setup");
    if(extra)long_connections.push(key,extra);
#else
    auto *queue=new std::queue<Client*>;long_connections.emplace(key,queue);if(nonempty)queue->push(seed);if(extra)queue->push(extra);
#endif
}
static std::vector<std::string> pool_snapshot(){std::vector<std::string> values;
#ifdef SWR_CLIENTS_WITNESS_RUST_POOL
    for(const auto&key:known_keys){auto state=long_connections.state(key);if(state.kind)values.push_back(key+":"+std::to_string(state.length));}
#else
    for(const auto&entry:long_connections)values.push_back(entry.first+":"+std::to_string(entry.second->size()));
#endif
    return values;
}
static void clear_pool(){
#ifdef SWR_CLIENTS_WITNESS_RUST_POOL
    for(const auto&key:known_keys){while(long_connections.take(key)){}long_connections.remove_empty(key);}
#else
    for(auto&entry:long_connections)delete entry.second;long_connections.clear();
#endif
    known_keys.clear();
}
static void php_swoole_client_set_cli(const zval*object,Client*client){observe("detach");const_cast<zval*>(object)->client=client;hook("detach");}
void php_swoole_client_free(const zval*,Client*);
// ACTUAL_BODY
static std::string snapshot(){std::ostringstream out;out<<last_error<<":"<<live_clients.size();
    if(subject&&live_clients.count(subject))out<<":"<<subject->keep<<":"<<subject->reuse_count<<":"<<(subject->timer!=nullptr)<<":"<<(subject->protocol.private_data_1!=nullptr)<<":"<<subject->server_id;
    else out<<":deleted";
    std::vector<std::string> pools=pool_snapshot();std::sort(pools.begin(),pools.end());for(const auto&pool:pools)out<<";"<<pool;return out.str();}
static std::string run(unsigned bits,unsigned scenario,unsigned mode){
    effects.clear();effect_hook={};probe={};new_socket_missing=false;next_identity=0;last_error=73;
    zval object,type,id,zsocket;type.kind=2;type.number=1|(bits&1?SW_FLAG_KEEP:0)|(bits&2?SW_SOCK_SSL:0);
    object.type_value=scenario==4?nullptr:&type;id.kind=IS_STRING;id.bytes=scenario==6?std::string("id\0key",6):"";object.id_value=&id;
    object.socket_value=bits&128?&zsocket:nullptr;
    auto *old=new Client(1,false);subject=old;old->server_id=scenario==6?id.bytes:"host:123";
    old->keep=bits&512;old->timer=bits&32?&timer_node:nullptr;old->protocol.private_data_1=bits&64?&callable:nullptr;old->reuse_count=7;
    object.client=old;
    if(bits&4){Client *extra=nullptr;if(bits&1024){extra=new Client(1,false);extra->server_id=old->server_id;subject=old;}prepare_pool(old->server_id,old,bits&8,extra);}
    liveness=bits&16;new_socket_missing=bits&256;effects.clear();probe=[] {return snapshot();};
    effect_hook=[&](const std::string&name){
        if(scenario==1&&name=="timer-delete")subject->keep=!subject->keep;
        if(scenario==2&&name=="callable-free")subject->server_id="changed";
        if(scenario==8&&name=="destructor")object.socket_value=object.socket_value?nullptr:&zsocket;
        if(scenario==3&&(name=="reuseCount"||name=="ssl"))throw std::runtime_error("native Zend effect");
    };
    Client *returned=nullptr;std::string exception;
    char host[]="host\0suffix";int port=scenario==5?65536:123;
    try{if(mode==0)returned=php_swoole_client_new(&object,host,scenario==7?11:4,port);else php_swoole_client_free(&object,old);}catch(const std::runtime_error&e){exception=e.what();}
    std::ostringstream output;output<<exception<<":"<<(returned?returned->identity:0)<<":"<<object.number<<":"<<(object.client==nullptr)<<":"<<(object.socket_value==nullptr)<<":"<<snapshot();
    for(const auto&item:effects)output<<"|"<<item;
    probe={};effect_hook={};while(!live_clients.empty())delete *live_clients.begin();subject=nullptr;clear_pool();return output.str();
}
} // BODY_NAMESPACE
// DRIVER
