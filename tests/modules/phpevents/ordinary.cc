// Complete pinned/selected ordinary bodies with modeled native APIs.
// No real descriptors, event loop, callbacks, retirement, faults or IPC execute.
#include "swoole_rs_phpevents.h"
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <map>
#include <string>
#include <unordered_map>
#include <vector>
#define SUCCESS 0
#define SW_OK 0
#define SW_ERR -1
#define SW_EVENT_READ 512
#define SW_EVENT_WRITE 1024
#define SW_FD_USER 7
#define E_WARNING 2
#define PHP_STREAM_AS_FD_FOR_SELECT 1
#define PHP_STREAM_CAST_INTERNAL 2
#define IS_RESOURCE 1
#define IS_LONG 2
#define IS_OBJECT 3
#define IS_NULL 4
#define ZVAL_IS_NULL(z) (Z_TYPE_P(z)==IS_NULL)
struct zval { int kind;int64_t number;int family;int refs=1; };
struct Wrapper {void *wops;};
static Wrapper php_plain_files_wrapper{reinterpret_cast<void *>(1)};
static Wrapper other_wrapper{reinterpret_cast<void *>(2)};
struct php_stream {int fd;Wrapper *wrapper=nullptr;};
struct php_socket {int bsd_socket;};
static std::vector<std::string> events;
static int read_kind(zval *z) {events.push_back("kind:"+std::to_string(z->kind));return z->kind;}
static int64_t number(zval *z) {events.push_back("number:"+std::to_string(z->number));return z->number;}
#define Z_TYPE_P(z) read_kind(z)
#define Z_LVAL_P(z) number(z)
#define Z_OBJCE_P(z) nullptr
static php_stream stream_value;
static php_socket socket_value;
static zval property_value{IS_LONG,0,0};
static php_stream *load_stream(zval *) {events.push_back("stream");return &stream_value;}
#define php_stream_from_zval_no_verify(stream,z) (stream)=load_stream(z)
static int php_stream_cast(php_stream *stream,int flags,void **output,int show_error) {
    events.push_back("cast:"+std::to_string(flags)+":"+std::to_string(show_error));std::memcpy(output,&stream->fd,sizeof(stream->fd));return SUCCESS;
}
static bool family(zval *z,int value) {events.push_back("class:"+std::to_string(value));return z->family==value;}
static bool sw_zval_is_co_socket(zval *z) {return family(z,1);}
static bool sw_zval_is_client(zval *z) {return family(z,2);}
static bool sw_zval_is_process(zval *z) {return family(z,3);}
#ifdef SWOOLE_SOCKETS_SUPPORT
static bool sw_zval_is_php_socket(zval *z) {return family(z,4);}
static php_socket *read_socket(zval *) {events.push_back("socket");return &socket_value;}
#define SW_Z_SOCKET_P(z) read_socket(z)
static bool socket_closed(php_socket *) {events.push_back("closed");return false;}
#define IS_INVALID_SOCKET(z) socket_closed(z)
#endif
#define SW_ZEND_STR_FD 1
#define SW_ZEND_STR_SOCK 2
#define SW_ZEND_STR_PIPE 3
#define SW_ZSTR_KNOWN(z) z
static zval *sw_zend_read_property_ex(void *,zval *,int name,int silent) {events.push_back("property:"+std::to_string(name)+":"+std::to_string(silent));return &property_value;}
template<class... Args> static void php_swoole_fatal_error(int,const char *text,Args...) {events.push_back(std::string("warning:")+text);}
struct ClassEntry {int function_table;const char *name;};
static ClassEntry entry{11,"Swoole\\Event"};
static ClassEntry *swoole_event_ce=&entry;
#define ZSTR_VAL(z) z
static int function_table=12;
#define CG(field) function_table
using zif_handler = int;
struct zend_function_entry { const char *fname; zif_handler handler; const int *arg_info; uint32_t num_args; uint32_t flags; };
#define ZEND_ACC_PUBLIC 0x100
#define ZEND_ACC_STATIC 0x40
#define ZEND_FN(name) handler_##name
#define ZEND_FENTRY(name,handler,info,flags) {#name,handler,info,uint32_t(sizeof(info)/sizeof(int)-1),flags},
#define PHP_FE_END {nullptr,0,nullptr,0,0}
enum { handler_swoole_event_add,handler_swoole_event_del,handler_swoole_event_set,handler_swoole_event_isset,handler_swoole_event_dispatch,handler_swoole_event_defer,handler_swoole_event_cycle,handler_swoole_event_write,handler_swoole_event_wait,handler_swoole_event_rshutdown,handler_swoole_event_exit };
#define SW_INIT_CLASS_ENTRY(module,name,parent,methods) do { \
 events.push_back(std::string("class:")+name+":13:"+std::to_string(module_number)); \
 for (const auto &method : methods) { \
  if (!method.fname) {assert(!method.handler && !method.arg_info && !method.num_args && !method.flags);break;} \
  events.push_back(std::string("method:")+method.fname+":"+std::to_string(method.handler)+":"+std::to_string(*method.arg_info)+":"+std::to_string(method.num_args)+":"+std::to_string(method.flags)); \
 } \
}while(0)
#define SW_SET_CLASS_CREATE(module,create) events.push_back("create-deny")
using zend_internal_arg_info=int;
#define ARG(name,id) static const int arginfo_swoole_event_##name[]={id}
ARG(add,0);ARG(del,1);ARG(set,2);ARG(wait,3);ARG(isset,4);ARG(dispatch,5);ARG(defer,6);ARG(cycle,7);ARG(write,8);ARG(exit,9);ARG(rshutdown,10);
static void sw_zend_register_function_alias(int *origin,const char *name,size_t length,int aliases,const char *alias,size_t alias_length,const int *info) {
    events.push_back("alias:"+std::to_string(*origin)+":"+std::string(name,length)+":"+std::to_string(aliases)+":"+std::string(alias,alias_length)+":"+std::to_string(*info));
}
#define SW_FUNCTION_ALIAS(table,name,aliases,alias,info) sw_zend_register_function_alias(table,name,sizeof(name)-1,aliases,alias,sizeof(alias)-1,info)
namespace zend {
struct Callable;
}
static std::map<zend::Callable *,bool> callbacks;
namespace zend {
struct Callable {int id;int *ptr(){::events.push_back("fcc:"+std::to_string(id));return &id;}~Callable(){callbacks[this]=false;}};
}
static zend::Callable *sw_callable_create_ex(zval *z,const char *name,bool allow_null=false) {
    events.push_back(std::string("callback:")+name+":"+std::to_string(allow_null)+":"+std::to_string(z!=nullptr));
    if(!z)return nullptr;
    auto result=new zend::Callable{static_cast<int>(z->number)};callbacks[result]=true;return result;
}
struct EventObject {zval zsocket;zend::Callable *readable_callback,*writable_callback;};
struct Socket {void *object=nullptr;int fd=0;int64_t events=0;bool removed=false;void set_nonblock(){::events.push_back("nonblock");}void free(){::events.push_back("free-socket");}};
static Socket model_socket;
static std::unordered_map<int,Socket *> event_socket_map;
static std::vector<void *> allocations;
static void *ecalloc(size_t count,size_t size) {events.push_back("allocate");auto result=std::calloc(count,size);allocations.push_back(result);return result;}
static void addref(zval *z) {events.push_back("retain");++z->refs;}
#define Z_TRY_ADDREF_P(z) addref(z)
static Socket *make_socket(int fd,int type) {events.push_back("make:"+std::to_string(fd)+":"+std::to_string(type));model_socket.fd=fd;return &model_socket;}
static int swoole_event_add(Socket *socket,int64_t mask) {events.push_back("backend-add:"+std::to_string(socket->fd)+":"+std::to_string(mask));return SW_OK;}
static void event_check_reactor(){events.push_back("check-reactor");}
static void event_object_free(void *){events.push_back("free-object");}
struct ModelTask {void (*callback)(void *)=nullptr;void *data=nullptr;};
struct ModelReactor {ModelTask future_task,idle_task;};
static ModelReactor model_reactor;
static bool reactor_ready=true;
static ModelReactor *sw_reactor() {events.push_back("reactor");return reactor_ready?&model_reactor:nullptr;}
static zend::Callable *sw_callable_create(zval *value) {return sw_callable_create_ex(value,"cycle",false);}
static int swoole_event_write(Socket *socket,char *data,size_t length) {events.push_back("backend-write:"+std::to_string(socket->fd)+":"+std::string(data,length));return SW_OK;}
static int swoole_event_del(Socket *) {events.push_back("backend-del");return SW_OK;}
static void sw_callable_free(void *) {events.push_back("unexpected-callback-free");}
static void swoole_event_defer(void (*)(void *),void *) {events.push_back("defer");}
static int swoole_event_set(Socket *socket,int64_t mask) {events.push_back("backend-set:"+std::to_string(socket->fd)+":"+std::to_string(mask));return SW_OK;}
using Reactor=ModelReactor;
struct Event {Socket *socket;};
static bool enabled_coroutine;
static bool php_swoole_is_enable_coroutine(){events.push_back("coro:"+std::to_string(enabled_coroutine));return enabled_coroutine;}
#define UNEXPECTED(value) (value)
template<class... Args> static void php_swoole_error(int,const char *text,Args...) {events.push_back(std::string("warning:")+text);}
namespace zend { namespace function {
static bool call(const int *fcc,uint32_t count,zval *arguments,zval *result,bool coroutine) {
    assert(count==1 && arguments && !result && arguments[0].number==42);
    events.push_back("native-call:"+std::to_string(*fcc)+":"+std::to_string(count)+":"+std::to_string(coroutine)+":"+std::to_string(arguments[0].number));return true;
}
static bool call(Callable *callable,uint32_t count,zval *arguments,zval *result,bool coroutine) {
    assert(count==0 && !arguments && !result && callable->id==303);
    events.push_back("native-callable:"+std::to_string(callable->id)+":"+std::to_string(coroutine));return true;
}
}}
struct Result {bool success;int64_t value;};
#define PHP_FUNCTION(name) Result zif_##name()
#define RETURN_FALSE return Result{false,0}
#define RETURN_TRUE return Result{true,1}
#define RETURN_BOOL(value) do {const bool result_bool=(value);return Result{result_bool,result_bool};}while(0)
#define RETURN_LONG(value) return Result{true,value}
using zend_long=int64_t;
using zend_bool=bool;
static bool input_before;
static char *input_data;
static size_t input_length;
static zval input_fd,input_read,input_write;
static zval *parameters[3];
static int64_t input_mask;
#define ZEND_PARSE_PARAMETERS_START(min,max) {size_t argument=0;
#define Z_PARAM_ZVAL(z) z=parameters[argument++];
#define Z_PARAM_OPTIONAL
#define Z_PARAM_LONG(value) value=input_mask;
#define Z_PARAM_BOOL(value) value=input_before;
#define Z_PARAM_STRING(value,length) value=input_data;length=input_length;
#define ZEND_PARSE_PARAMETERS_END_EX(failure) }
#define FAILURE -1
#define ZEND_NUM_ARGS() 2
static int zend_parse_parameters(int count,const char *format,zval **descriptor,zend_long *mask) {
    events.push_back(std::string("parse:")+std::to_string(count)+":"+format);*descriptor=parameters[0];*mask=input_mask;return SUCCESS;
}
namespace reference {
#include "reference.inc"
}
namespace candidate {
#include "candidate.inc"
}
using Convert=int(*)(zval *);
static std::vector<std::string> convert(Convert fn,int type,int object_family,int value) {
    events.clear();zval input{type,value,object_family};property_value={IS_LONG,value,0};stream_value.fd=socket_value.bsd_socket=value;
    events.push_back("return:"+std::to_string(fn(&input)));return events;
}
using Add=Result(*)();
static std::vector<std::string> add(Add fn,int fd,int64_t mask) {
    events.clear();event_socket_map.clear();candidate::event_socket_map.erase(fd);model_socket={};input_fd={IS_LONG,fd,0};input_read={0,101,0};input_write={0,102,0};input_mask=mask;
    parameters[0]=&input_fd;parameters[1]=mask&SW_EVENT_READ?&input_read:nullptr;parameters[2]=mask&SW_EVENT_WRITE?&input_write:nullptr;
    const auto result=fn();events.push_back("return:"+std::to_string(result.success)+":"+std::to_string(result.value));
    const bool present=fn==candidate::zif_swoole_event_add?candidate::event_socket_map.contains(fd):event_socket_map.count(fd)!=0;
    events.push_back("registry:"+std::to_string(present)+":"+std::to_string(input_fd.refs));
    assert(result.success && result.value==fd && present && input_fd.refs==2);
    assert((fn==candidate::zif_swoole_event_add?candidate::event_get_socket(fd):reference::event_get_socket(fd))==&model_socket);
    if(fn==candidate::zif_swoole_event_add) {
        auto payload=static_cast<candidate::EventObject *>(model_socket.object);
        assert(payload && payload->zsocket.number==fd && (payload->readable_callback.identity!=0)==bool(mask&SW_EVENT_READ) && (payload->writable_callback.identity!=0)==bool(mask&SW_EVENT_WRITE));
    } else {
        auto payload=static_cast<EventObject *>(model_socket.object);
        assert(payload && payload->zsocket.number==fd && (payload->readable_callback!=nullptr)==bool(mask&SW_EVENT_READ) && (payload->writable_callback!=nullptr)==bool(mask&SW_EVENT_WRITE));
    }
    // Private mock allocations are reclaimed directly, without executing any
    // Event lifecycle, callback, shutdown, retirement or fault profile.
    for(auto pointer:allocations) { std::free(pointer); }
    allocations.clear();
    for(auto &item:callbacks) { if(item.second)delete item.first; }
    callbacks.clear();
    return events;
}
// Ordinary mask update with unchanged callbacks. No callback replacement,
// deferral, Event lifecycle or backend failure executes in these scenarios.
static std::vector<std::string> update(Add fn,int64_t mask) {
    events.clear();event_socket_map.clear();candidate::event_socket_map.erase(42);model_socket={};
    input_fd={IS_LONG,42,0};parameters[0]=&input_fd;parameters[1]=parameters[2]=nullptr;input_mask=mask;
    {
        zend::Callable readable{201},writable{202};
        EventObject payload{input_fd,&readable,&writable};
        candidate::EventObject owned{input_fd,{reinterpret_cast<uintptr_t>(&readable)},{reinterpret_cast<uintptr_t>(&writable)}};
        model_socket.object=fn==candidate::zif_swoole_event_set?static_cast<void *>(&owned):static_cast<void *>(&payload);model_socket.fd=42;
        if(fn==candidate::zif_swoole_event_set)candidate::event_socket_map.insert(42,&model_socket);
        else event_socket_map[42]=&model_socket;
        const auto result=fn();
        events.push_back("return:"+std::to_string(result.success)+":"+std::to_string(result.value));
        assert(result.success && payload.readable_callback==&readable && payload.writable_callback==&writable);
        assert(owned.readable_callback.identity==reinterpret_cast<uintptr_t>(&readable) && owned.writable_callback.identity==reinterpret_cast<uintptr_t>(&writable));
        candidate::event_socket_map.erase(42);event_socket_map.clear();
    }
    callbacks.clear();return events;
}
static std::vector<std::string> query(Add fn,bool ready,bool present,bool removed,int64_t stored,int64_t mask) {
    events.clear();event_socket_map.clear();candidate::event_socket_map.erase(42);model_socket={};
    reactor_ready=ready;input_fd={IS_LONG,42,0};parameters[0]=&input_fd;input_mask=mask;
    model_socket.fd=42;model_socket.removed=removed;model_socket.events=stored;
    if(present) {
        if(fn==candidate::zif_swoole_event_isset)candidate::event_socket_map.insert(42,&model_socket);
        else event_socket_map[42]=&model_socket;
    }
    const auto result=fn();
    events.push_back("return:"+std::to_string(result.success)+":"+std::to_string(result.value));
    assert(result.success==(ready && present && !removed && (stored&mask)!=0));
    candidate::event_socket_map.erase(42);event_socket_map.clear();reactor_ready=true;
    return events;
}
// Normal modeled operations only. Backend write records bytes, performs no IO;
// missing-entry delete returns before any retirement; cycle installs fresh data
// and never invokes/defers/retires a callback. Direct mock cleanup is private.
static std::vector<std::string> write_operation(Add fn,std::string data) {
    events.clear();event_socket_map.clear();candidate::event_socket_map.erase(42);model_socket={};
    input_fd={IS_LONG,42,0};parameters[0]=&input_fd;input_data=&data[0];input_length=data.size();model_socket.fd=42;
    if(fn==candidate::zif_swoole_event_write)candidate::event_socket_map.insert(42,&model_socket);
    else event_socket_map[42]=&model_socket;
    const auto result=fn();events.push_back("return:"+std::to_string(result.success));assert(result.success);
    candidate::event_socket_map.erase(42);event_socket_map.clear();return events;
}
static std::vector<std::string> empty_delete(Add fn) {
    events.clear();event_socket_map.clear();candidate::event_socket_map.erase(42);reactor_ready=true;
    input_fd={IS_LONG,42,0};parameters[0]=&input_fd;
    const auto result=fn();events.push_back("return:"+std::to_string(result.success));assert(!result.success);return events;
}
static std::vector<std::string> fresh_cycle(Add fn,bool before) {
    events.clear();model_reactor={};reactor_ready=true;input_before=before;
    zval callback{IS_OBJECT,303,0};parameters[0]=&callback;
    const auto result=fn();auto &slot=before?model_reactor.future_task:model_reactor.idle_task;
    auto &other=before?model_reactor.idle_task:model_reactor.future_task;
    const auto expected=fn==candidate::zif_swoole_event_cycle?candidate::event_cycle_callback:reference::event_cycle_callback;
    assert(result.success && slot.callback==expected && slot.data && !other.callback && !other.data);
    assert(static_cast<zend::Callable *>(slot.data)->id==303);
    events.push_back("return:"+std::to_string(result.success));
    delete static_cast<zend::Callable *>(slot.data);slot={};callbacks.clear();return events;
}
// Successful dispatcher bodies only. Native call APIs are recording stubs and
// invoke no PHP/user callback or coroutine. Error/retirement/defer handlers never
// execute. Private mock storage is reclaimed outside the Event lifecycle.
using Dispatch=int(*)(Reactor *,Event *);
static std::vector<std::string> dispatch_success(Dispatch fn,bool coroutine) {
    events.clear();enabled_coroutine=coroutine;
    {
        zend::Callable read{101},write{102};EventObject payload{{IS_LONG,42,0},&read,&write};
        candidate::EventObject owned{{IS_LONG,42,0},{reinterpret_cast<uintptr_t>(&read)},{reinterpret_cast<uintptr_t>(&write)}};
        Socket socket;socket.fd=42;
        void *identity=(fn==candidate::event_readable_callback || fn==candidate::event_writable_callback)?static_cast<void *>(&owned):static_cast<void *>(&payload);
        socket.object=identity;Event event{&socket};
        const int result=fn(&model_reactor,&event);assert(result==SW_OK && socket.object==identity);
        events.push_back("return:"+std::to_string(result));
    }
    callbacks.clear();return events;
}
using CycleDispatch=void(*)(void *);
static std::vector<std::string> cycle_dispatch_success(CycleDispatch fn,bool coroutine) {
    events.clear();enabled_coroutine=coroutine;
    {zend::Callable callback{303};fn(&callback);assert(callback.id==303);}
    callbacks.clear();return events;
}
// Independent metadata-only corpus. No Socket/Zend object is created, invoked,
// dereferenced or reclaimed by this registry; HashMap stores copied integers.
static size_t registry_metadata() {
    SwrPhpEventRegistry *registry=nullptr;
    std::unordered_map<int,uintptr_t> original;
    assert(!swr_v1_phpevents_registry_contains(registry,42));
    assert(swr_v1_phpevents_registry_get(registry,42)==0);
    assert(!swr_v1_phpevents_registry_erase(registry,42));
    uint32_t state=19;
    for(size_t index=0;index<4096;++index) {
        state=state*1664525u+1013904223u;
        const int key=static_cast<int>((state>>8)&1023u);
        const uintptr_t value=state%7==0?0:state;
        switch(state&3u) {
        case 0:original[key]=value;swr_v1_phpevents_registry_insert(&registry,key,value);break;
        case 1:assert(swr_v1_phpevents_registry_erase(registry,key)==original.erase(key));break;
        default:break;
        }
        const auto found=original.find(key);
        assert(bool(swr_v1_phpevents_registry_contains(registry,key))==(found!=original.end()));
        assert(swr_v1_phpevents_registry_get(registry,key)==(found==original.end()?0:found->second));
    }
    // Replacement, zero-valued presence and descriptor boundaries are explicit.
    for(int key:{0,1,42,INT32_MAX}) {
        swr_v1_phpevents_registry_insert(&registry,key,123);
        swr_v1_phpevents_registry_insert(&registry,key,0);
        assert(swr_v1_phpevents_registry_contains(registry,key));
        assert(swr_v1_phpevents_registry_get(registry,key)==0);
        assert(swr_v1_phpevents_registry_erase(registry,key));
        assert(!swr_v1_phpevents_registry_erase(registry,key));
    }
    swr_v1_phpevents_registry_drop(registry);registry=nullptr;
    return 4096;
}
int main() {
    const size_t metadata_operations=registry_metadata();
    events.clear();reference::php_swoole_event_minit(17);const auto aliases=events;events.clear();candidate::php_swoole_event_minit(17);assert(events==aliases);
    size_t descriptors=0,registrations=0,streams=0,updates=0,queries=0,writes=0,cycles=0,dispatches=0;
    for(int value:{0,1,42,INT32_MAX}) {
        assert(convert(reference::php_swoole_convert_to_fd,IS_LONG,0,value)==convert(candidate::php_swoole_convert_to_fd,IS_LONG,0,value));++descriptors;
        assert(convert(reference::php_swoole_convert_to_fd,IS_RESOURCE,0,value)==convert(candidate::php_swoole_convert_to_fd,IS_RESOURCE,0,value));++descriptors;
    }
    for(int type:{1,2,3})for(int value:{-1,0,1,42}) {
        assert(convert(reference::php_swoole_convert_to_fd,IS_OBJECT,type,value)==convert(candidate::php_swoole_convert_to_fd,IS_OBJECT,type,value));++descriptors;
    }
#ifdef SWOOLE_SOCKETS_SUPPORT
    for(int value:{0,1,42}) {assert(convert(reference::php_swoole_convert_to_fd,IS_OBJECT,4,value)==convert(candidate::php_swoole_convert_to_fd,IS_OBJECT,4,value));++descriptors;}
#endif
    // Successful ordinary stream wrappers only; optional fallback/error paths
    // remain source-accounted and unexecuted, with no real descriptor activity.
    for(int fd:{0,1,42,INT32_MAX})for(Wrapper *wrapper:{static_cast<Wrapper *>(nullptr),&php_plain_files_wrapper,&other_wrapper}) {
        stream_value.fd=fd;stream_value.wrapper=wrapper;zval input{IS_RESOURCE,fd,0};
        int original_async=-1,selected_async=-1;
        events.clear();const int original_fd=reference::php_swoole_convert_to_fd_ex(&input,&original_async);const auto original_events=events;
        events.clear();const int selected_fd=candidate::php_swoole_convert_to_fd_ex(&input,&selected_async);
        assert(original_fd==selected_fd && selected_fd==fd && original_async==selected_async && events==original_events);
        assert(selected_async==(wrapper==&php_plain_files_wrapper?0:1));++streams;
    }
    for(int fd:{1,42})for(int64_t mask:{int64_t(SW_EVENT_READ),int64_t(SW_EVENT_WRITE),int64_t(SW_EVENT_READ|SW_EVENT_WRITE)}) {assert(add(reference::zif_swoole_event_add,fd,mask)==add(candidate::zif_swoole_event_add,fd,mask));++registrations;}
    assert(add(reference::zif_swoole_event_add,0,SW_EVENT_READ)==add(candidate::zif_swoole_event_add,0,SW_EVENT_READ));++registrations;
    for(int64_t mask:{int64_t(0),int64_t(SW_EVENT_READ),int64_t(SW_EVENT_WRITE),int64_t(SW_EVENT_READ|SW_EVENT_WRITE)}) {
        assert(update(reference::zif_swoole_event_set,mask)==update(candidate::zif_swoole_event_set,mask));++updates;
    }
    for(bool ready:{false,true})for(bool present:{false,true})for(bool removed:{false,true})
    for(int64_t stored:{int64_t(0),int64_t(SW_EVENT_READ),int64_t(SW_EVENT_WRITE),int64_t(SW_EVENT_READ|SW_EVENT_WRITE)})
    for(int64_t mask:{int64_t(0),int64_t(SW_EVENT_READ),int64_t(SW_EVENT_WRITE),int64_t(SW_EVENT_READ|SW_EVENT_WRITE),int64_t(64)}) {
        assert(query(reference::zif_swoole_event_isset,ready,present,removed,stored,mask)==query(candidate::zif_swoole_event_isset,ready,present,removed,stored,mask));++queries;
    }
    for(const auto &data:{std::string("ordinary"),std::string("A\0B",3)}) {
        assert(write_operation(reference::zif_swoole_event_write,data)==write_operation(candidate::zif_swoole_event_write,data));++writes;
    }
    assert(empty_delete(reference::zif_swoole_event_del)==empty_delete(candidate::zif_swoole_event_del));
    for(bool before:{false,true}) {assert(fresh_cycle(reference::zif_swoole_event_cycle,before)==fresh_cycle(candidate::zif_swoole_event_cycle,before));++cycles;}
    for(bool coroutine:{false,true}) {
        assert(dispatch_success(reference::event_readable_callback,coroutine)==dispatch_success(candidate::event_readable_callback,coroutine));++dispatches;
        assert(dispatch_success(reference::event_writable_callback,coroutine)==dispatch_success(candidate::event_writable_callback,coroutine));++dispatches;
        assert(cycle_dispatch_success(reference::event_cycle_callback,coroutine)==cycle_dispatch_success(candidate::event_cycle_callback,coroutine));++dispatches;
    }
    std::cout<<"{\"alias_registrations\":11,\"descriptor_scenarios\":"<<descriptors<<",\"registration_scenarios\":"<<registrations<<",\"stream_scenarios\":"<<streams<<",\"metadata_operations\":"<<metadata_operations<<",\"ordinary_updates\":"<<updates<<",\"ordinary_queries\":"<<queries<<",\"modeled_writes\":"<<writes<<",\"empty_deletes\":1,\"fresh_cycles\":"<<cycles<<",\"modeled_successful_dispatches\":"<<dispatches<<",\"native_runtime_executed\":false,\"fault_shutdown_retirement_ipc_executed\":false}\n";
}
