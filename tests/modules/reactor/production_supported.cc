// Separately named supported consumer; broad failed profile remains stopped.
// Genuine production Reactor/Socket calls. No embedded backend implementation.
extern "C" {
#include <php.h>
#include <Zend/zend_exceptions.h>
}
#include "swoole.h"
#include "swoole_socket.h"
#include "swoole_reactor.h"
#include <dlfcn.h>
#include <stdexcept>
#include <type_traits>
#include <string>
#include <vector>
#include <sys/socket.h>
#include <unistd.h>
#include <fcntl.h>
using namespace swoole;
namespace {
struct Witness { unsigned reads=0,writes=0;std::string order;bool valid=true; };
int on_read(Reactor *reactor,Event *event) {
    auto *state=static_cast<Witness*>(reactor->ptr);char byte=0;
    state->valid=state->valid&&::recv(event->fd,&byte,1,MSG_DONTWAIT)==1&&byte=='r';
    ++state->reads;state->order+='R';return SW_OK;
}
int on_write(Reactor *reactor,Event *event) {
    auto *state=static_cast<Witness*>(reactor->ptr);
    state->valid=state->valid&&::send(event->fd,"w",1,0)==1;
    ++state->writes;state->order+='W';return SW_OK;
}
void image(zval *result,const char *key,const char *symbol) {
    Dl_info info{};void *address=dlsym(RTLD_DEFAULT,symbol);
    if(address&&dladdr(address,&info))add_assoc_string(result,key,const_cast<char*>(info.dli_fname));
    else add_assoc_null(result,key);
}
}
ZEND_BEGIN_ARG_WITH_RETURN_TYPE_INFO_EX(arginfo_swr_reactor_supported,0,0,IS_ARRAY,0)
ZEND_END_ARG_INFO()
PHP_FUNCTION(swr_reactor_supported) {
    ZEND_PARSE_PARAMETERS_NONE();array_init(return_value);
    image(return_value,"method_image","_ZN6swoole7ReactorC1EiNS0_4TypeE");
    image(return_value,"storage_image","swr_v1_reactor_poll_new");
    image(return_value,"batch_image","swr_v1_reactor_poll_record");
#if defined(SWOOLE_RS_REACTOR_SOCKETS_OWNED) && SWOOLE_RS_REACTOR_SOCKETS_OWNED
    add_assoc_long(return_value,"registry_owned_compiled",1);
    add_assoc_long(return_value,"registry_policy",swr_v1_reactor_sockets_policy());
    image(return_value,"registry_len_image","swr_v1_reactor_sockets_len");
    image(return_value,"registry_policy_image","swr_v1_reactor_sockets_policy");
#else
    add_assoc_long(return_value,"registry_owned_compiled",0);
    add_assoc_long(return_value,"registry_policy",0);
    add_assoc_null(return_value,"registry_len_image");
    add_assoc_null(return_value,"registry_policy_image");
#endif
    zval rows;array_init(&rows);unsigned cases=0;
    auto check=[&](bool value) { add_next_index_bool(&rows,value); };
    try {
        for(Reactor::Type backend:{Reactor::TYPE_POLL,
#ifdef __linux__
                                  Reactor::TYPE_EPOLL
#else
                                  Reactor::TYPE_KQUEUE
#endif
        })for(int mode:{0,1,2,3})for(bool once_socket:{false,true}) {
            // Separate supported inventory: one kqueue filter per ready record.
            if(backend==Reactor::TYPE_KQUEUE&&mode==2)continue;
            Reactor reactor(8,backend);check(reactor.ready_);reactor.once=true;reactor.timeout_msec=20;
            Witness state;reactor.ptr=&state;
            reactor.set_handler(SW_FD_USER,SW_EVENT_READ,on_read);
            reactor.set_handler(SW_FD_USER,SW_EVENT_WRITE,on_write);
            int pair[2];if(::socketpair(AF_UNIX,SOCK_STREAM,0,pair)!=0)throw std::runtime_error("private socketpair failed");
            auto *socket=make_socket(pair[0],SW_FD_USER);check(socket&&socket->fd==pair[0]);
            const bool readable=mode==0||mode==2,writable=mode==1||mode==2;
            int interest=(readable||mode==3?SW_EVENT_READ:0)|(writable?SW_EVENT_WRITE:0)|(once_socket?SW_EVENT_ONCE:0);
            check(reactor.add(socket,SW_EVENT_READ|SW_EVENT_WRITE)==SW_OK&&reactor.get_event_num()==1);
            check(reactor.set(socket,interest)==SW_OK);
            if(readable&&::send(pair[1],"r",1,0)!=1)throw std::runtime_error("private positive write failed");
            check(reactor.wait()==SW_OK);
            check(state.reads==unsigned(readable));check(state.writes==unsigned(writable));
            check(state.order==(mode==0?"R":mode==1?"W":mode==2?"RW":""));
            check(state.valid);
            const bool removed=once_socket&&mode!=3;
            check(bool(socket->removed)==removed);check(reactor.get_event_num()==unsigned(!removed));
            check(reactor.timed_out==(mode==3));
            if(writable) {char byte=0;check(::recv(pair[1],&byte,1,MSG_DONTWAIT)==1&&byte=='w');}
            else check(true);
            if(!socket->removed)check(reactor.del(socket)==SW_OK);else check(true);
            check(reactor.get_event_num()==0);
            // Token stays live until the complete batch and explicit unregister.
            socket->free();::close(pair[1]);++cases;
        }
        add_assoc_long(return_value,"cases",cases);add_assoc_zval(return_value,"outcomes",&rows);
    } catch(const std::exception &error) {zval_ptr_dtor(&rows);zend_throw_exception(zend_ce_exception,error.what(),0);}
}
PHP_FUNCTION(swr_reactor_callbacks_supported) {
    ZEND_PARSE_PARAMETERS_NONE();array_init(return_value);
    image(return_value,"method_image","_ZN6swoole7ReactorC1EiNS0_4TypeE");
    image(return_value,"callbacks_image","swr_v1_reactor_callbacks_insert");
    zval rows;array_init(&rows);
    auto check=[&](bool value){add_next_index_bool(&rows,value);};
    try {
        // Genuine live production Reactor, never copied. Remove only its local
        // installed functions before manual ordinary callback execution.
        Reactor reactor(8,Reactor::TYPE_POLL);check(reactor.ready_);check(reactor.get_event_num()==0);
        for(int key=0;key<=7;++key)reactor.erase_end_callback(static_cast<Reactor::EndCallback>(key));
        check(reactor.remove_exit_condition(Reactor::EXIT_CONDITION_DEFER_TASK)==1);
        check(reactor.remove_exit_condition(Reactor::EXIT_CONDITION_DEFAULT)==1);
        check(!reactor.isset_exit_condition(Reactor::EXIT_CONDITION_TIMER));
        std::vector<int> trace;
        auto end=[&](int key,const std::function<void(Reactor*)>&fn){reactor.set_end_callback(static_cast<Reactor::EndCallback>(key),fn);};
        auto exit=[&](int key,const std::function<bool(Reactor*,size_t&)>&fn){reactor.set_exit_condition(static_cast<Reactor::ExitCondition>(key),fn);};
        end(1,[&](Reactor*){trace.push_back(1);});
        end(3,[&](Reactor*){trace.push_back(3);});
        end(5,[&](Reactor*){trace.push_back(5);});
        reactor.execute_end_callbacks(true);check(reactor.timed_out);check(trace==std::vector<int>({1,3,5}));trace.clear();
        end(3,[&](Reactor*){trace.push_back(99);});
        reactor.execute_end_callbacks(false);check(!reactor.timed_out);check(trace==std::vector<int>({1,99,5}));trace.clear();
        reactor.erase_end_callback(Reactor::PRIORITY_SIGNAL_CALLBACK);reactor.erase_end_callback(Reactor::PRIORITY_TIMER);
        reactor.execute_end_callbacks(false);check(trace==std::vector<int>({1,5}));trace.clear();
        end(3,[&](Reactor*){trace.push_back(3);});
        end(1,[&](Reactor*){
            trace.push_back(1);
            end(0,[&](Reactor*){trace.push_back(0);});
            end(2,[&](Reactor*){trace.push_back(2);});
            reactor.erase_end_callback(Reactor::PRIORITY_SIGNAL_CALLBACK);
        });
        reactor.execute_end_callbacks(false);check(trace==std::vector<int>({1,2,5}));trace.clear();
        exit(0,[&](Reactor*,size_t &events){check(events==0);events+=7;trace.push_back(0);return true;});
        exit(2,[&](Reactor*,size_t &events){check(events==7);trace.push_back(2);return false;});
        exit(3,[&](Reactor*,size_t &events){check(events==7);trace.push_back(3);return true;});
        check(reactor.isset_exit_condition(Reactor::EXIT_CONDITION_WAIT_PID));
        check(!reactor.if_exit());check(trace==std::vector<int>({0,2}));trace.clear();
        check(reactor.remove_exit_condition(Reactor::EXIT_CONDITION_WAIT_PID)==1);
        check(reactor.remove_exit_condition(Reactor::EXIT_CONDITION_WAIT_PID)==0);
        check(reactor.if_exit());check(trace==std::vector<int>({0,3}));
        // All captures stay live and no custom destruction observer is used.
        add_assoc_zval(return_value,"outcomes",&rows);
    } catch(const std::exception &error) {zval_ptr_dtor(&rows);zend_throw_exception(zend_ce_exception,error.what(),0);}
}
namespace {
unsigned handler_invocations;
int handler_one(Reactor*,Event*){++handler_invocations;return 1;}
int handler_two(Reactor*,Event*){++handler_invocations;return 2;}
int handler_three(Reactor*,Event*){++handler_invocations;return 3;}
int handler_four(Reactor*,Event*){++handler_invocations;return 4;}
int handler_five(Reactor*,Event*){++handler_invocations;return 5;}
}
PHP_FUNCTION(swr_reactor_handlers_supported) {
    ZEND_PARSE_PARAMETERS_NONE();array_init(return_value);
    image(return_value,"method_image","_ZN6swoole7ReactorC1EiNS0_4TypeE");
    image(return_value,"setter_image","_ZN6swoole7Reactor11set_handlerEiiPFiPS0_PNS_5EventEE");
    image(return_value,"isset_image","_ZNK6swoole7Reactor13isset_handlerEii");
    image(return_value,"handlers_image","swr_v1_reactor_handler_select");
    zval rows;array_init(&rows);unsigned cases=0;handler_invocations=0;
    auto check=[&](bool value){add_next_index_bool(&rows,value);};
    try {
        Reactor r(8,Reactor::TYPE_POLL);
        if(!r.ready_)throw std::runtime_error("private poll reactor not ready");
        ReactorHandler pointers[]={handler_one,handler_two,handler_three,handler_four,handler_five};
        for(unsigned present=0;present<32;++present)for(auto fd:{SW_FD_USER,SW_FD_STREAM}) {
            ReactorHandler values[5];for(unsigned slot=0;slot<5;++slot)values[slot]=(present&(1u<<slot))?pointers[slot]:nullptr;
            r.read_handler[fd]=values[0];r.write_handler[fd]=values[1];r.error_handler[fd]=values[2];r.default_write_handler=values[3];r.default_error_handler=values[4];
            for(int mask=0;mask<8;++mask)for(int once=0;once<2;++once){
                int event=(mask<<9)|(once?SW_EVENT_ONCE:0);int slot=(event<SW_EVENT_DEAULT||(mask&1))?0:(mask&2)?1:(mask&4)?2:-1;
                check(r.isset_handler(fd,event)==(slot>=0&&values[slot]!=nullptr));++cases;
            }
            for(int slot=0;slot<3;++slot){
                auto result=r.get_handler(static_cast<FdType>(fd),static_cast<EventType>(1<<(9+slot)));
                auto expected=values[slot]?values[slot]:slot==1?values[3]:slot==2?values[4]:nullptr;
                check(result==expected);if(result)check(result(&r,nullptr)==(expected==pointers[0]?1:expected==pointers[1]?2:expected==pointers[2]?3:expected==pointers[3]?4:5));++cases;
            }
            auto expected=values[2]?values[2]:values[4]?values[4]:values[0]?values[0]:values[1]?values[1]:values[3];
            auto result=r.get_error_handler(static_cast<FdType>(fd));check(result==expected);if(result)check(result(&r,nullptr)>0);++cases;
        }
        for(int mask=0;mask<8;++mask)for(int once=0;once<2;++once)for(int candidate=0;candidate<6;++candidate)for(auto fd:{SW_FD_USER,SW_FD_STREAM}){
            if(mask==0&&once)continue;
            for(auto index:{SW_FD_USER,SW_FD_STREAM}){r.read_handler[index]=handler_one;r.write_handler[index]=handler_two;r.error_handler[index]=handler_three;}
            auto value=candidate?pointers[candidate-1]:nullptr;int event=(mask<<9)|(once?SW_EVENT_ONCE:0);
            r.set_handler(fd,event,value);int slot=(event<SW_EVENT_DEAULT||(mask&1))?0:(mask&2)?1:2;
            check(r.read_handler[fd]==(slot==0?value:handler_one));check(r.write_handler[fd]==(slot==1?value:handler_two));check(r.error_handler[fd]==(slot==2?value:handler_three));
            auto other=fd==SW_FD_USER?SW_FD_STREAM:SW_FD_USER;
            check(r.read_handler[other]==handler_one&&r.write_handler[other]==handler_two&&r.error_handler[other]==handler_three);++cases;
        }
        for(int legacy:{7,255}){r.set_handler(SW_FD_USER,legacy,handler_one);check(r.read_handler[SW_FD_USER]==handler_one);check(r.isset_handler(SW_FD_USER,legacy));++cases;}
        add_assoc_long(return_value,"cases",cases);add_assoc_long(return_value,"native_invocations",handler_invocations);add_assoc_zval(return_value,"outcomes",&rows);
    } catch(const std::exception &error){zval_ptr_dtor(&rows);zend_throw_exception(zend_ce_exception,error.what(),0);}
}
PHP_FUNCTION(swr_reactor_builtins_supported) {
    ZEND_PARSE_PARAMETERS_NONE();array_init(return_value);
    image(return_value,"method_image","_ZN6swoole7ReactorC1EiNS0_4TypeE");
    image(return_value,"begin_image","_ZNK6swoole7Reactor22execute_begin_callbackEv");
    image(return_value,"end_image","_ZN6swoole7Reactor21execute_end_callbacksEb");
    image(return_value,"builtins_image","swr_v1_reactor_builtin_step");
#if defined(__APPLE__)
    image(return_value,"defer_method_image","_ZN6swoole7Reactor5deferERKNSt3__18functionIFvPvEEES3_");
#else
    image(return_value,"defer_method_image","_ZN6swoole7Reactor5deferERKSt8functionIFvPvEES2_");
#endif
#if defined(SWOOLE_RS_REACTOR_DEFER_OWNED) && SWOOLE_RS_REACTOR_DEFER_OWNED
    static_assert(std::is_same<decltype(Reactor::defer_tasks),ReactorDeferredQueue *>::value,"selected deferred field source type");
    static_assert(std::is_same<decltype(Reactor::destroy_callbacks),ReactorDeferredQueue>::value,"selected actual destroy queue source type");
    add_assoc_long(return_value,"defer_owned_compiled",1);
    image(return_value,"defer_push_image","swr_v1_reactor_deferred_push");
    image(return_value,"defer_step_image","swr_v1_reactor_deferred_step");
    image(return_value,"defer_clear_image","swr_v1_reactor_deferred_clear");
#else
    static_assert(std::is_same<decltype(Reactor::defer_tasks),CallbackManager *>::value,"Native deferred field source type");
    static_assert(std::is_same<decltype(Reactor::destroy_callbacks),CallbackManager>::value,"Native actual destroy queue source type");
    add_assoc_long(return_value,"defer_owned_compiled",0);
#endif
    zval rows;array_init(&rows);auto check=[&](bool value){add_next_index_bool(&rows,value);};
    try {
        std::vector<int> trace;bool accepted=false;unsigned queries=0;
        Reactor r(8,Reactor::TYPE_POLL);check(r.ready_);check(r.get_event_num()==0);
        // Keep the three real installed builtin functions; isolate unrelated
        // signal/timer/trim/worker effects from this separately named inventory.
        for(int key=0;key<=7;++key)if(key!=Reactor::PRIORITY_DEFER_TASK&&key!=Reactor::PRIORITY_IDLE_TASK&&key!=Reactor::PRIORITY_TRY_EXIT)r.erase_end_callback(static_cast<Reactor::EndCallback>(key));
        for(int key=0;key<=Reactor::EXIT_CONDITION_IOURING;++key)if(key!=Reactor::EXIT_CONDITION_DEFER_TASK)r.remove_exit_condition(static_cast<Reactor::ExitCondition>(key));
        r.remove_exit_condition(Reactor::EXIT_CONDITION_USER_AFTER_DEFAULT);
        r.running=true;r.wait_exit=false;check(r.defer_tasks==nullptr);check(r.if_exit());
        r.future_task.callback=[&](void *data){check(data==&trace);trace.push_back(0);};r.future_task.data=&trace;
        r.execute_begin_callback();check(trace==std::vector<int>({0}));trace.clear();r.future_task={};
        r.execute_begin_callback();check(trace.empty());
        r.defer([&](void *data){check(data==&trace);check(r.defer_tasks==nullptr);trace.push_back(2);},&trace);
        r.defer([&](void*){trace.push_back(3);});check(!r.if_exit());check(r.defer_tasks!=nullptr);
        r.idle_task.callback=[&](void *data){check(data==&trace);trace.push_back(4);};r.idle_task.data=&trace;
        r.execute_end_callbacks(false);check(trace==std::vector<int>({2,3,4}));check(r.defer_tasks==nullptr);check(r.if_exit());trace.clear();r.idle_task={};
        r.defer([&](void*){check(r.defer_tasks==nullptr);trace.push_back(5);r.defer([&](void*){trace.push_back(6);});});
        r.execute_end_callbacks(false);check(trace==std::vector<int>({5}));check(r.defer_tasks!=nullptr);check(!r.if_exit());
        r.execute_end_callbacks(false);check(trace==std::vector<int>({5,6}));check(r.defer_tasks==nullptr);check(r.if_exit());
        r.set_exit_condition(Reactor::EXIT_CONDITION_USER_BEFORE_DEFAULT,[&](Reactor *self,size_t&){++queries;self->wait_exit=false;return accepted;});
        for(bool value:{false,true}){accepted=value;r.running=true;r.wait_exit=true;unsigned before=queries;r.execute_end_callbacks(false);check(queries==before+1);check(r.running==!accepted);check(!r.wait_exit);}
        check(r.remove_exit_condition(Reactor::EXIT_CONDITION_USER_BEFORE_DEFAULT)==1);
        r.running=true;r.wait_exit=false;r.execute_end_callbacks(false);check(r.running);check(queries==2);
        add_assoc_zval(return_value,"outcomes",&rows);
    } catch(const std::exception &error){zval_ptr_dtor(&rows);zend_throw_exception(zend_ce_exception,error.what(),0);}
}

namespace {
struct OrdinaryOutputPair {
    network::Socket *socket=nullptr;int peer=-1;
    OrdinaryOutputPair(){int pair[2];if(::socketpair(AF_UNIX,SOCK_STREAM,0,pair)!=0)throw std::runtime_error("private output socketpair failed");socket=make_socket(pair[0],SW_FD_USER);peer=pair[1];timeval limit{1,0};if(::setsockopt(peer,SOL_SOCKET,SO_RCVTIMEO,&limit,sizeof(limit))!=0){socket->free();socket=nullptr;::close(peer);peer=-1;throw std::runtime_error("private output receive setup failed");}}
    ~OrdinaryOutputPair(){if(socket)socket->free();if(peer!=-1)::close(peer);}
    std::string receive(size_t length){std::string bytes(length,char(0));size_t offset=0;while(offset<length){auto n=::recv(peer,&bytes[offset],length-offset,0);if(n<=0)throw std::runtime_error("positive output receive failed");offset+=n;}return bytes;}
};
struct OrdinaryOutputFile {
    char path[64]="/tmp/swr-reactor-output-XXXXXX";
    explicit OrdinaryOutputFile(const std::string &bytes){int fd=::mkstemp(path);if(fd<0)throw std::runtime_error("private output file setup failed");auto n=::write(fd,bytes.data(),bytes.size());::close(fd);if(n!=static_cast<ssize_t>(bytes.size())){::unlink(path);throw std::runtime_error("private positive output file write failed");}}
    ~OrdinaryOutputFile(){::unlink(path);}
};
}
PHP_FUNCTION(swr_reactor_output_supported) {
    ZEND_PARSE_PARAMETERS_NONE();array_init(return_value);
    image(return_value,"method_image","_ZN6swoole7network6Socket11handle_sendEv");
    image(return_value,"sendfile_image","_ZN6swoole7network6Socket15handle_sendfileEv");
#if defined(__APPLE__)
    image(return_value,"request_image","_ZN6swoole7network6Socket14sendfile_asyncEPKcxm");
#else
    image(return_value,"request_image","_ZN6swoole7network6Socket14sendfile_asyncEPKclm");
#endif
    image(return_value,"data_policy_image","swr_v1_reactor_output_data");
    image(return_value,"file_policy_image","swr_v1_reactor_output_file");
    image(return_value,"request_policy_image","swr_v1_reactor_output_request");
    image(return_value,"parameters_policy_image","swr_v1_reactor_output_parameters");
    image(return_value,"workflow_policy_image","swr_v1_reactor_output_workflow");
    image(return_value,"buffer_constructor_image","_ZN6swoole6BufferC1Ej");
#if defined(SWOOLE_RS_BUFFER_TYPED) && SWOOLE_RS_BUFFER_TYPED
    add_assoc_long(return_value,"typed_buffer_compiled",1);
    image(return_value,"typed_buffer_front_image","_ZNK6swoole6Buffer11typed_frontEv");
    image(return_value,"typed_buffer_create_image","swr_v1_buffer_typed_create");
    image(return_value,"typed_buffer_push_image","swr_v1_buffer_typed_push");
    image(return_value,"typed_buffer_front_image_rust","swr_v1_buffer_typed_front");
    image(return_value,"typed_buffer_consume_image","swr_v1_buffer_typed_consume");
    image(return_value,"typed_buffer_pop_image","swr_v1_buffer_typed_pop");
#else
    add_assoc_long(return_value,"typed_buffer_compiled",0);
#endif
    zval rows;array_init(&rows);auto check=[&](bool value){add_next_index_bool(&rows,value);if(!value)throw std::runtime_error("ordinary output assertion failed");};unsigned cases=0;
    try {
        std::string payload;for(unsigned i=0;i<47;++i)payload+=static_cast<char>(i);
        for(size_t length:{size_t(1),size_t(7),size_t(31)}){
            OrdinaryOutputPair pair;auto *socket=pair.socket;check(socket&&socket->fd>=0);
            socket->out_buffer=new Buffer(SW_SEND_BUFFER_SIZE);check(socket->out_buffer!=nullptr);
            socket->out_buffer->append(payload.data(),length);check(socket->out_buffer->count()==1);
            check(socket->handle_send()==SW_OK);check(socket->out_buffer->empty()&&socket->out_buffer->count()==0);
            check(pair.receive(length)==payload.substr(0,length));check(!socket->send_wait&&!socket->close_wait);check(socket->out_buffer->length()==0);++cases;
        }
        OrdinaryOutputFile file(payload);
        for(off_t offset:{off_t(0),off_t(2)})for(size_t length:{size_t(0),size_t(1),size_t(7)}){
            OrdinaryOutputPair pair;auto *socket=pair.socket;check(socket&&socket->fd>=0);
            check(socket->sendfile_async(file.path,offset,length)==SW_OK);check(socket->out_buffer&&socket->out_buffer->count()==1);
#if defined(SWOOLE_RS_BUFFER_TYPED) && SWOOLE_RS_BUFFER_TYPED
            auto *task=static_cast<network::SendfileRequest*>(socket->out_buffer->typed_front().token);
#else
            auto *task=static_cast<network::SendfileRequest*>(socket->out_buffer->front()->value.ptr);
#endif
            size_t expected=length?length:payload.size()-offset;
            check(task->begin==offset&&task->end==static_cast<off_t>(offset+expected));check(task->corked==0);
            unsigned attempts=0;while(!socket->out_buffer->empty()){
                if(++attempts>16||socket->handle_sendfile()!=SW_OK)throw std::runtime_error("ordinary positive queued sendfile failed");
            }
            check(socket->out_buffer->count()==0);check(pair.receive(expected)==payload.substr(offset,expected));
            check(!socket->send_wait&&!socket->close_wait);check(socket->out_buffer->length()==0);++cases;
        }
        add_assoc_long(return_value,"cases",cases);add_assoc_zval(return_value,"outcomes",&rows);
    }catch(const std::exception &error){zval_ptr_dtor(&rows);zend_throw_exception(zend_ce_exception,error.what(),0);}
}

PHP_FUNCTION(swr_reactor_blocking_supported) {
    ZEND_PARSE_PARAMETERS_NONE();array_init(return_value);
    image(return_value,"method_image","_ZN6swoole7network6Socket9send_syncEPKvmi");
    image(return_value,"vector_image","_ZN6swoole7network6Socket11writev_syncEPK5iovecm");
    image(return_value,"event_image","_ZNK6swoole7network6Socket15what_event_wantEi");
    image(return_value,"iov_image","_ZN6swoole7network8IOVector15update_iteratorEl");
    image(return_value,"iov_constructor_image","_ZN6swoole7network8IOVectorC1EPK5ioveci");
    image(return_value,"iov_destructor_image","_ZN6swoole7network8IOVectorD1Ev");
#if defined(SWOOLE_RS_REACTOR_IOV_OWNED) && SWOOLE_RS_REACTOR_IOV_OWNED
    add_assoc_long(return_value,"iov_owned_compiled",1);
    image(return_value,"iov_owned_length_image","swr_v1_reactor_iov_owned_length");
#else
    add_assoc_long(return_value,"iov_owned_compiled",0);
#endif
#if defined(__APPLE__)
    image(return_value,"file_image","_ZN6swoole7network6Socket13sendfile_syncEPKcxm");
    image(return_value,"wait_image","_ZN6swoole7network6Socket8wait_forERKNSt3__18functionIF12swReturnCodevEEEii");
#else
    image(return_value,"file_image","_ZN6swoole7network6Socket13sendfile_syncEPKclm");
    image(return_value,"wait_image","_ZN6swoole7network6Socket8wait_forERKSt8functionIF12swReturnCodevEEii");
#endif
    image(return_value,"wait_policy_image","swr_v1_reactor_blocking_wait");
    image(return_value,"io_policy_image","swr_v1_reactor_blocking_io");
    image(return_value,"file_policy_image","swr_v1_reactor_blocking_file");
    image(return_value,"event_policy_image","swr_v1_reactor_blocking_event");
    image(return_value,"iov_policy_image","swr_v1_reactor_iov_progress");
    zval rows;array_init(&rows);auto check=[&](bool value){add_next_index_bool(&rows,value);if(!value)throw std::runtime_error("ordinary blocking assertion failed");};unsigned cases=0;
    try {
        std::string payload;for(unsigned i=0;i<47;++i)payload+=static_cast<char>(i);
        auto prepared=[&](network::Socket *socket){check(socket->nonblock);check((::fcntl(socket->fd,F_GETFL)&O_NONBLOCK)!=0);check(!socket->send_wait&&!socket->close_wait);check(socket->out_buffer==nullptr);};
        for(size_t length:{size_t(1),size_t(7),size_t(31)}){
            OrdinaryOutputPair pair;auto *socket=pair.socket;check(socket&&socket->fd>=0);
            check(socket->send_sync(payload.data(),length,0)==static_cast<ssize_t>(length));check(pair.receive(length)==payload.substr(0,length));prepared(socket);++cases;
        }
        iovec vectors[]={{&payload[0],2},{&payload[2],3},{&payload[5],7}};
        {OrdinaryOutputPair pair;auto *socket=pair.socket;check(socket&&socket->fd>=0);check(socket->writev_sync(vectors,3)==12);check(pair.receive(12)==payload.substr(0,12));prepared(socket);++cases;}
        OrdinaryOutputFile file(payload);
        for(off_t offset:{off_t(0),off_t(2)}){OrdinaryOutputPair pair;auto *socket=pair.socket;check(socket&&socket->fd>=0);check(socket->sendfile_sync(file.path,offset,0)==SW_OK);check(pair.receive(payload.size()-offset)==payload.substr(offset));prepared(socket);++cases;}
        {OrdinaryOutputPair pair;auto *socket=pair.socket;check(socket&&socket->fd>=0);unsigned callbacks=0;
            check(socket->wait_for([&]()->ReturnCode{++callbacks;return callbacks==1?SW_CONTINUE:SW_READY;},SW_EVENT_WRITE,-1));
            check(callbacks==2);check(socket->nonblock);check((::fcntl(socket->fd,F_GETFL)&O_NONBLOCK)!=0);check(!socket->kernel_nobufs);check(socket->out_buffer==nullptr&&!socket->send_wait&&!socket->close_wait);++cases;}
        {network::IOVector v(vectors,3);check(v.length()==12&&v.count==3);check(vectors[0].iov_len==2&&vectors[1].iov_len==3&&vectors[2].iov_len==7);
            v.update_iterator(1);check(v.get_remain_count()==3&&v.get_index()==0&&v.get_offset_bytes()==1);check(v.get_iterator()->iov_base==&payload[1]&&v.get_iterator()->iov_len==1);
            v.update_iterator(1);check(v.get_remain_count()==2&&v.get_index()==1&&v.get_offset_bytes()==1);check(v.get_iterator()->iov_base==&payload[2]&&v.get_iterator()->iov_len==3);
            v.update_iterator(3);check(v.get_remain_count()==1&&v.get_index()==2&&v.get_offset_bytes()==1);check(v.get_iterator()->iov_base==&payload[5]&&v.get_iterator()->iov_len==7);
            auto *previous=v.get_iterator();v.update_iterator(7);check(v.get_remain_count()==0&&v.get_index()==3&&v.get_offset_bytes()==1);check(v.get_iterator()==previous);
            bool unchanged=true;for(int i=0;i<3;++i)unchanged=unchanged&&v.iov[i].iov_base==vectors[i].iov_base&&v.iov[i].iov_len==vectors[i].iov_len;check(unchanged);check(vectors[0].iov_len==2&&vectors[1].iov_len==3&&vectors[2].iov_len==7);++cases;}
        add_assoc_long(return_value,"cases",cases);add_assoc_zval(return_value,"outcomes",&rows);
    }catch(const std::exception &error){zval_ptr_dtor(&rows);zend_throw_exception(zend_ce_exception,error.what(),0);}
}

PHP_FUNCTION(swr_reactor_ordinary_supported) {
    ZEND_PARSE_PARAMETERS_NONE();array_init(return_value);
    image(return_value,"method_image","_ZN6swoole7network6Socket4sendEPKvmi");
    image(return_value,"recv_image","_ZN6swoole7network6Socket4recvEPvmi");
    image(return_value,"peek_image","_ZNK6swoole7network6Socket4peekEPvmi");
    image(return_value,"readv_image","_ZN6swoole7network6Socket5readvEPNS0_8IOVectorE");
    image(return_value,"writev_image","_ZN6swoole7network6Socket6writevEPNS0_8IOVectorE");
    image(return_value,"read_image","_ZN6swoole7network6Socket9read_syncEPvm");
    image(return_value,"write_image","_ZN6swoole7network6Socket10write_syncEPKvm");
    image(return_value,"receive_image","_ZN6swoole7network6Socket9recv_syncEPvmi");
    image(return_value,"fd_image","_ZN6swoole7network6Socket13set_fd_optionEii");
    image(return_value,"buffer_image","_ZNK6swoole7network6Socket15set_buffer_sizeEj");
    image(return_value,"set_timeout_image","_ZN6swoole7network6Socket11set_timeoutEdi");
    image(return_value,"get_timeout_image","_ZNK6swoole7network6Socket11get_timeoutE13swTimeoutType");
    image(return_value,"kernel_read_image","_ZN6swoole7network6Socket23set_kernel_read_timeoutEd");
    image(return_value,"kernel_write_image","_ZN6swoole7network6Socket24set_kernel_write_timeoutEd");
    image(return_value,"poll_image","_ZNK6swoole7network6Socket10wait_eventEii");
    image(return_value,"error_image","_ZN6swoole7network6Socket11catch_errorEi");
    image(return_value,"timedout_image","_ZNK6swoole7network6Socket12has_timedoutEv");
    image(return_value,"ordinary_policy_image","swr_v1_reactor_ordinary_io");
    image(return_value,"blocking_policy_image","swr_v1_reactor_blocking_io");
    image(return_value,"buffer_policy_image","swr_v1_reactor_socket_buffers");
    image(return_value,"timeout_policy_image","swr_v1_reactor_socket_timeout");
    image(return_value,"poll_policy_image","swr_v1_reactor_socket_poll");
    image(return_value,"error_policy_image","swr_v1_reactor_socket_error");
    image(return_value,"fd_policy_image","swr_v1_reactor_fd_options");
    zval rows,values;array_init(&rows);array_init(&values);
    auto check=[&](bool value){add_next_index_bool(&rows,value);if(!value)throw std::runtime_error("ordinary Socket assertion failed");};
    auto guard=[](bool value){if(!value)throw std::runtime_error("positive ordinary Socket prerequisite/effect failed");};unsigned cases=0;
    try {
        std::string payload;for(unsigned i=0;i<47;++i)payload+=static_cast<char>(i);
        auto preload=[&](OrdinaryOutputPair &pair,const std::string &data){guard(::send(pair.peer,data.data(),data.size(),0)==static_cast<ssize_t>(data.size()));};
        auto finish=[&](network::Socket *socket,const std::string &data,const std::string &expected,size_t tx,size_t rx,size_t sent,size_t received){
            check(data==expected);check(socket->out_buffer==nullptr&&!socket->send_wait&&!socket->close_wait);
            check(socket->total_send_bytes==tx+sent&&socket->total_recv_bytes==rx+received);
            check(socket->fd>=0&&socket->ssl==nullptr);int flags=::fcntl(socket->fd,F_GETFL);guard(flags>=0);check(bool(flags&O_NONBLOCK)==bool(socket->nonblock));
        };
        for(size_t length:{size_t(1),size_t(7),size_t(31)})for(unsigned operation=0;operation<7;++operation){
            OrdinaryOutputPair pair;auto *socket=pair.socket;guard(socket!=nullptr);size_t tx=socket->total_send_bytes,rx=socket->total_recv_bytes;std::string expected=payload.substr(0,length),data(length,char(0));bool sending=operation==0||operation==4;
            if(!sending)preload(pair,expected);
            if(operation==2){ssize_t n=socket->peek(&data[0],length,0);guard(n>0&&static_cast<size_t>(n)<=length);check(data.substr(0,n)==expected.substr(0,n));}
            size_t offset=0;unsigned calls=0;
            while(offset<length){guard(++calls<=64);ssize_t n=0;switch(operation){
                case 0:n=socket->send(expected.data()+offset,length-offset,0);break;
                case 1:case 2:n=socket->recv(&data[offset],length-offset,0);break;
                case 3:n=socket->read_sync(&data[offset],length-offset);break;
                case 4:n=socket->write_sync(expected.data()+offset,length-offset);break;
                case 5:case 6:n=socket->recv_sync(&data[offset],length-offset,operation==6?MSG_WAITALL:0);break;
                default:throw std::runtime_error("ordinary fixture operation");
            }guard(n>0&&static_cast<size_t>(n)<=length-offset);offset+=n;}
            if(sending)data=pair.receive(length);
            finish(socket,data,expected,tx,rx,operation==0?length:0,(operation==1||operation==2||operation>=5)?length:0);++cases;
        }
        for(bool sending:{false,true}){OrdinaryOutputPair pair;auto *socket=pair.socket;guard(socket!=nullptr);size_t tx=socket->total_send_bytes,rx=socket->total_recv_bytes;std::string expected=payload.substr(0,12),data=sending?expected:std::string(12,char(0));
            if(!sending)preload(pair,expected);iovec parts[]={{&data[0],2},{&data[2],3},{&data[5],7}};network::IOVector vector(parts,3);unsigned calls=0;
            while(vector.get_remain_count()>0){guard(++calls<=16);ssize_t n=sending?socket->writev(&vector):socket->readv(&vector);guard(n>0);}
            if(sending)data=pair.receive(12);finish(socket,data,expected,tx,rx,0,0);check(vector.count==3&&vector.get_index()==3&&vector.get_remain_count()==0);
            bool original=true;for(int i=0;i<3;++i)original=original&&vector.iov[i].iov_base==parts[i].iov_base&&vector.iov[i].iov_len==parts[i].iov_len;check(original);++cases;
        }
        for(auto mode:{std::pair<int,int>{0,0},{1,0},{1,1}}){OrdinaryOutputPair pair;auto *socket=pair.socket;guard(socket!=nullptr);check(socket->set_fd_option(mode.first,mode.second));int flags=::fcntl(socket->fd,F_GETFL),descriptor=::fcntl(socket->fd,F_GETFD);guard(flags>=0&&descriptor>=0);check(bool(flags&O_NONBLOCK)==bool(mode.first)&&socket->nonblock==mode.first);check(bool(descriptor&FD_CLOEXEC)==bool(mode.second)&&socket->cloexec==mode.second);++cases;}
        for(uint32_t size:{512u,4096u,16384u}){OrdinaryOutputPair pair;auto *socket=pair.socket;guard(socket!=nullptr);auto before=socket->buffer_size;check(socket->set_buffer_size(size));int send=0,recv=0;socklen_t length=sizeof(int);guard(::getsockopt(socket->fd,SOL_SOCKET,SO_SNDBUF,&send,&length)==0&&length==sizeof(int));length=sizeof(int);guard(::getsockopt(socket->fd,SOL_SOCKET,SO_RCVBUF,&recv,&length)==0&&length==sizeof(int));check(send>0&&recv>0);check(socket->buffer_size==before);add_next_index_long(&values,send);add_next_index_long(&values,recv);++cases;}
        for(double value:{0.125,1.25,7.75}){OrdinaryOutputPair pair;auto *socket=pair.socket;guard(socket!=nullptr);socket->set_timeout(value,SW_TIMEOUT_ALL);check(socket->get_timeout(SW_TIMEOUT_DNS)==value);check(socket->get_timeout(SW_TIMEOUT_CONNECT)==value);check(socket->get_timeout(SW_TIMEOUT_READ)==value);check(socket->get_timeout(SW_TIMEOUT_WRITE)==value);socket->set_timeout(0,SW_TIMEOUT_ALL);check(socket->dns_timeout==value&&socket->connect_timeout==value&&socket->read_timeout==value&&socket->write_timeout==value);
            socket->set_timeout(value+0.5,SW_TIMEOUT_ALL);check(socket->set_kernel_read_timeout(value));check(socket->write_timeout==value&&socket->read_timeout==value+0.5);timeval time{};socklen_t length=sizeof(time);guard(::getsockopt(socket->fd,SOL_SOCKET,SO_SNDTIMEO,&time,&length)==0&&length==sizeof(time));check(time.tv_sec>=0&&time.tv_usec>=0&&(time.tv_sec>0||time.tv_usec>0));add_next_index_long(&values,time.tv_sec);add_next_index_long(&values,time.tv_usec);
            check(socket->set_kernel_write_timeout(value+0.25));check(socket->read_timeout==value+0.25&&socket->write_timeout==value);length=sizeof(time);guard(::getsockopt(socket->fd,SOL_SOCKET,SO_RCVTIMEO,&time,&length)==0&&length==sizeof(time));check(time.tv_sec>=0&&time.tv_usec>=0&&(time.tv_sec>0||time.tv_usec>0));add_next_index_long(&values,time.tv_sec);add_next_index_long(&values,time.tv_usec);++cases;
        }
        {OrdinaryOutputPair pair;auto *socket=pair.socket;guard(socket!=nullptr);swoole_set_last_error(0);errno=0;check(!socket->has_timedout());check(socket->catch_error(0)==SW_WAIT);check(!socket->kernel_nobufs);++cases;}
        for(bool readable:{false,true}){OrdinaryOutputPair pair;auto *socket=pair.socket;guard(socket!=nullptr);if(readable)preload(pair,"x");check(socket->wait_event(1000,readable?SW_EVENT_READ:SW_EVENT_WRITE)==SW_OK);if(readable){char byte=0;guard(::recv(socket->fd,&byte,1,0)==1&&byte=='x');}check(socket->out_buffer==nullptr&&!socket->send_wait&&!socket->close_wait);++cases;}
        add_assoc_long(return_value,"cases",cases);add_assoc_zval(return_value,"outcomes",&rows);add_assoc_zval(return_value,"kernel_values",&values);
    }catch(const std::exception &error){zval_ptr_dtor(&rows);zval_ptr_dtor(&values);zend_throw_exception(zend_ce_exception,error.what(),0);}
}

PHP_FUNCTION(swr_reactor_datagram_supported) {
    ZEND_PARSE_PARAMETERS_NONE();array_init(return_value);
    image(return_value,"method_image","_ZN6swoole7network6Socket11sendto_syncERKNS0_7AddressEPKvmi");
    image(return_value,"receive_image","_ZNK6swoole7network6Socket8recvfromEPcmiP8sockaddrPj");
    image(return_value,"sync_image","_ZN6swoole7network6Socket13recvfrom_syncEPcmiP8sockaddrPj");
    image(return_value,"address_image","_ZN6swoole7network6Socket13recvfrom_syncEPcmiPNS0_7AddressE");
    image(return_value,"ordinary_policy_image","swr_v1_reactor_ordinary_io");
    image(return_value,"blocking_policy_image","swr_v1_reactor_blocking_io");
    zval rows;array_init(&rows);unsigned cases=0;
    auto check=[&](bool value){add_next_index_bool(&rows,value);if(!value)throw std::runtime_error("ordinary datagram assertion failed");};
    auto guard=[](bool value){if(!value)throw std::runtime_error("positive datagram prerequisite/effect failed");};
    try {
        std::string payload;for(unsigned i=0;i<47;++i)payload+=static_cast<char>(i);
        for(size_t length:{size_t(1),size_t(7),size_t(31)}){
            // A bounded private filesystem UNIX endpoint exercises actual sendto.
            // Native owns all resources; no external network or shared port.
            char directory[]="/tmp/swr-reactor-datagram-XXXXXX";
            guard(::mkdtemp(directory)!=nullptr);
            std::string path=std::string(directory)+"/receiver";
            int descriptor=-1,receiver=-1;network::Socket *socket=nullptr;
            try {
                receiver=::socket(AF_UNIX,SOCK_DGRAM,0);guard(receiver>=0);
                network::Address destination{};destination.addr.un.sun_family=AF_UNIX;
                guard(path.size()<sizeof(destination.addr.un.sun_path));
                std::memcpy(destination.addr.un.sun_path,path.c_str(),path.size()+1);
                destination.len=sizeof(destination.addr.un);
                guard(::bind(receiver,&destination.addr.ss,destination.len)==0);
                timeval limit{1,0};guard(::setsockopt(receiver,SOL_SOCKET,SO_RCVTIMEO,&limit,sizeof(limit))==0);
                descriptor=::socket(AF_UNIX,SOCK_DGRAM,0);guard(descriptor>=0);
                socket=make_socket(descriptor,SW_FD_USER);guard(socket!=nullptr);descriptor=-1;
                size_t tx=socket->total_send_bytes,rx=socket->total_recv_bytes;
                check(socket->sendto_sync(destination,payload.data(),length,0)==static_cast<ssize_t>(length));
                std::string received(length,char(0));auto n=::recv(receiver,&received[0],length,0);
                check(n==static_cast<ssize_t>(length));check(received==payload.substr(0,length));
                check(socket->out_buffer==nullptr&&!socket->close_wait&&!socket->send_wait);
                check(socket->total_send_bytes==tx&&socket->total_recv_bytes==rx);
                check(socket->fd>=0&&socket->ssl==nullptr);++cases;
            } catch(...){if(socket)socket->free();if(descriptor>=0)::close(descriptor);if(receiver>=0)::close(receiver);::unlink(path.c_str());::rmdir(directory);throw;}
            socket->free();::close(receiver);guard(::unlink(path.c_str())==0);guard(::rmdir(directory)==0);
            for(unsigned operation=0;operation<3;++operation){
                int pair[2];guard(::socketpair(AF_UNIX,SOCK_DGRAM,0,pair)==0);
                network::Socket *socket=nullptr;
                try {
                    socket=make_socket(pair[0],SW_FD_USER);guard(socket!=nullptr);pair[0]=-1;
                    timeval limit{1,0};guard(::setsockopt(socket->fd,SOL_SOCKET,SO_RCVTIMEO,&limit,sizeof(limit))==0);
                    guard(::send(pair[1],payload.data(),length,0)==static_cast<ssize_t>(length));
                    size_t tx=socket->total_send_bytes,rx=socket->total_recv_bytes;
                    network::Address address{};address.len=sizeof(address.addr);
                    std::string data(length,char(0));ssize_t n;
                    if(operation==0)n=socket->recvfrom(&data[0],length,0,&address.addr.ss,&address.len);
                    else if(operation==1)n=socket->recvfrom_sync(&data[0],length,0,&address.addr.ss,&address.len);
                    else n=socket->recvfrom_sync(&data[0],length,0,&address);
                    check(n==static_cast<ssize_t>(length));check(data==payload.substr(0,length));
                    check(address.len<=sizeof(address.addr));
                    check(socket->out_buffer==nullptr&&!socket->close_wait&&!socket->send_wait);
                    check(socket->total_send_bytes==tx&&socket->total_recv_bytes==rx);
                    check(socket->fd>=0&&socket->ssl==nullptr);++cases;
                }catch(...){if(socket)socket->free();if(pair[0]>=0)::close(pair[0]);::close(pair[1]);throw;}
                socket->free();::close(pair[1]);
            }
        }
        add_assoc_long(return_value,"cases",cases);add_assoc_zval(return_value,"outcomes",&rows);
    }catch(const std::exception &error){zval_ptr_dtor(&rows);zend_throw_exception(zend_ce_exception,error.what(),0);}
}

static const zend_function_entry functions[]={PHP_FE(swr_reactor_supported,arginfo_swr_reactor_supported) PHP_FE(swr_reactor_callbacks_supported,arginfo_swr_reactor_supported) PHP_FE(swr_reactor_handlers_supported,arginfo_swr_reactor_supported) PHP_FE(swr_reactor_builtins_supported,arginfo_swr_reactor_supported) PHP_FE(swr_reactor_output_supported,arginfo_swr_reactor_supported) PHP_FE(swr_reactor_blocking_supported,arginfo_swr_reactor_supported) PHP_FE(swr_reactor_ordinary_supported,arginfo_swr_reactor_supported) PHP_FE(swr_reactor_datagram_supported,arginfo_swr_reactor_supported) PHP_FE_END};
extern "C" {
zend_module_entry swr_reactor_supported_module_entry={STANDARD_MODULE_HEADER,"swr_reactor_supported",functions,
    nullptr,nullptr,nullptr,nullptr,nullptr,"1",STANDARD_MODULE_PROPERTIES};
ZEND_GET_MODULE(swr_reactor_supported)
}
