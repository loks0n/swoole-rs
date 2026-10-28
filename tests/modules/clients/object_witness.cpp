/* SPDX-License-Identifier: Apache-2.0 */
#include "swoole_rs_clients.h"
#include <cassert>
#include <cstdint>
#include <iostream>
#include <memory>
#include <new>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
// DECLARATIONS
namespace BODY_NAMESPACE {
using SocketType=int;using Fn=void(*)();
constexpr int SW_FD_STREAM_CLIENT=11,SW_FD_DGRAM_CLIENT=12,SW_SOCK_NONBLOCK=2,SW_SOCK_CLOEXEC=4,SW_CLIENT_BUFFER_SIZE=1024,SW_SEND_BUFFER_SIZE=2048,SW_INPUT_BUFFER_SIZE=4096;
static void Client_tcp_recv_sync(){}static void Client_tcp_connect_async(){}static void Client_tcp_send_async(){}static void Client_tcp_sendfile_async(){}static void Client_tcp_connect_sync(){}static void Client_tcp_send_sync(){}static void Client_tcp_sendfile_sync(){}static void Client_udp_connect(){}static void Client_udp_recv(){}static void Client_udp_send(){}static void Client_onPackage(){}
static Fn routes[]={nullptr,Client_tcp_recv_sync,Client_tcp_connect_async,Client_tcp_send_async,Client_tcp_sendfile_async,Client_tcp_connect_sync,Client_tcp_send_sync,Client_tcp_sendfile_sync,Client_udp_connect,Client_udp_recv,Client_udp_send,Client_onPackage};
static unsigned bits,scenario,mutation;static int failure,event_index;static bool cleanup;static std::ostringstream trace;
struct Client;static Client*current;
struct Socket;struct Buffer;
static std::vector<Socket*>owned_sockets;static std::vector<Buffer*>owned_buffers;
static void event(const std::string&);static void change(unsigned);
struct Socket {
 int fd=41,chunk_size=0,type=1;void*object=nullptr;bool alive=true;
 static bool is_stream(int t){event("static-stream:"+std::to_string(t));change(1);return t==1||t==3;}
 bool is_stream(){event("socket-stream:"+std::to_string(type));change(3);return type==1||type==3;}
 static void get_domain_and_type(int,int*,int*);
 void free(){event("socket-free");change(8);delete this;}
 ~Socket(){if(!cleanup)event("socket-delete:"+std::to_string(object==nullptr));alive=false;for(auto &p:owned_sockets)if(p==this)p=nullptr;}
};
struct Buffer{int id;~Buffer(){if(!cleanup){event("buffer-delete:"+std::to_string(id));change(7);}for(auto &p:owned_buffers)if(p==this)p=nullptr;}};
struct Client {
#ifdef SELECTED_STATE
 // The selected Client's flags are Rust's (#439); scenarios set and read them the same way.
 std::unique_ptr<swr_v1_clients_state,decltype(&swr_v1_clients_state_free)> state_{nullptr,swr_v1_clients_state_free};
 bool is_async() const{return swr_v1_clients_flag(state_.get(),SWR_CLIENTS_ASYNC);}
 bool is_closed() const{return swr_v1_clients_flag(state_.get(),SWR_CLIENTS_CLOSED);}
 void set_async(bool v){swr_v1_clients_set_flag(state_.get(),SWR_CLIENTS_ASYNC,v);}
 void set_closed(bool v){swr_v1_clients_set_flag(state_.get(),SWR_CLIENTS_CLOSED,v);}
#else
 bool async,closed=false;
 bool is_async() const{return async;}
 bool is_closed() const{return closed;}
 void set_async(bool v){async=v;}
 void set_closed(bool v){closed=v;}
#endif
 int fd_type=-1,input_buffer_size=-2,sock_domain_=-3,sock_type_=-4;
 Socket*socket=nullptr;Buffer*buffer=nullptr;
 Fn recv_=nullptr,connect_=nullptr,send_=nullptr,sendfile_=nullptr;
 struct{int type=-5;}remote_addr;
 struct{char package_length_type='?';int package_length_size=-6,package_body_offset=-7,package_max_length=-8;Fn onPackage=nullptr;}protocol;
 Client(SocketType,bool);~Client();int close();
};
static std::string state(){std::ostringstream out;out<<current->is_async()<<current->is_closed()<<','<<current->fd_type<<','<<current->input_buffer_size<<','<<current->sock_domain_<<','<<current->sock_type_<<','<<current->remote_addr.type<<','<<current->protocol.package_length_type<<','<<current->protocol.package_length_size<<','<<current->protocol.package_body_offset<<','<<current->protocol.package_max_length<<','<<(current->buffer?current->buffer->id:0)<<',';for(auto f:{current->recv_,current->connect_,current->send_,current->sendfile_,current->protocol.onPackage}){unsigned id=0;for(unsigned i=0;i<12;++i)if(routes[i]==f)id=i;out<<id<<'.';}if(current->socket)out<<current->socket->fd<<','<<current->socket->chunk_size<<','<<(current->socket->object==current);else out<<"null";return out.str();}
static void event(const std::string&name){trace<<name<<':'<<state()<<';';if(event_index++==failure)throw std::runtime_error(name);}
static void change(unsigned point){if(mutation!=point)return;if(point==1||point==2||point==3||point==6||point==7)current->set_async(!current->is_async());if(point==6)current->set_closed(true);}
void Socket::get_domain_and_type(int t,int*d,int*s){event("domain:"+std::to_string(t));*d=100+t;*s=200+t;change(4);}
static Socket*make_socket(int t,int fd_type,int flags){event("make:"+std::to_string(t)+":"+std::to_string(fd_type)+":"+std::to_string(flags));change(2);if(bits&2)return nullptr;auto*s=new Socket;s->type=bits&4?2:t;s->fd=41;owned_sockets.push_back(s);return s;}
static void swoole_sys_warning(const char*p){event(std::string("warning:")+p);}
int Client::close(){event("close");change(6);return scenario%2?-1:0;}
// ACTUAL_BODY
static std::string run(unsigned input,unsigned sc,unsigned mut,int fail){
 bits=input;scenario=sc;mutation=mut;failure=fail;event_index=0;cleanup=false;trace.str("");trace.clear();owned_sockets.clear();owned_buffers.clear();
 alignas(Client) unsigned char storage[sizeof(Client)];current=reinterpret_cast<Client*>(storage);bool constructed=false;std::string exception;int types[]={1,2,3,4,5,999};
 try{new(storage)Client(types[sc%6],bits&1);constructed=true;event("constructed");}catch(const std::exception&e){exception=e.what();}
 // Constructor exception prefixes are compared without invoking a destructor on
 // an object whose constructor did not complete. No fake successful cleanup.
 if(constructed){
  failure=-1;
  if(bits&8){current->buffer=new Buffer{1};owned_buffers.push_back(current->buffer);}
  current->set_closed(bits&16);
  if(bits&32)current->set_async(!current->is_async());
  trace<<"pre-dtor:"<<state()<<';';
  current->~Client();
  // Track destruction from the actual native destructors. Do not assume the
  // Client consumed resources: the original null-Socket early return leaves a
  // subsequently injected buffer untouched. Preserve that live-resource state.

 }
 size_t live_sockets=0,live_buffers=0;for(auto*p:owned_sockets)live_sockets+=p!=nullptr;for(auto*p:owned_buffers)live_buffers+=p!=nullptr;
 trace<<"throw:"<<exception<<"|live:"<<live_sockets<<","<<live_buffers;
 cleanup=true;for(auto*p:owned_sockets)delete p;for(auto*p:owned_buffers)delete p;
 return trace.str();
}
}
// DRIVER
