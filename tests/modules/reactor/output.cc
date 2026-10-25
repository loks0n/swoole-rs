#include <cassert>
#include <cerrno>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <limits>
#include <memory>
#include <string>
#include <vector>
#include <sys/types.h>
#include "swoole_rs_reactor.h"
#define SW_OK 0
#define SW_ERR -1
#define SW_WAIT 2
#define SW_CLOSE 3
#define SW_ERROR 4
#define SW_SOCKET_CORK_MIN_SIZE 8
#define SW_SENDFILE_CHUNK_SIZE 7
#define SW_SEND_BUFFER_SIZE 16
#define SW_LOG_WARNING 1
#define SW_ERROR_FILE_EMPTY 1
#define SW_ERROR_INVALID_PARAMS 2
#define swoole_sys_warning(...) std::abort()
#define swoole_error_log(...) std::abort()
#define swoole_trace(...) ((void) 0)
namespace swoole {
using TableStringLength = uint32_t;
struct FileStatus { off_t st_size; };
struct File {std::string path;File(const char *p):path(p){} const std::string &get_path()const{return path;}bool ready()const{return true;}bool stat(FileStatus *s)const{s->st_size=31;return true;}};
struct SendfileRequest {File file;off_t begin,end=0;int corked=0;SendfileRequest(const char *p,off_t b):file(p),begin(b){}const char *get_filename()const{return file.path.c_str();}};
struct BufferChunk {enum{TYPE_SENDFILE=1};uint32_t length=0,offset=0;union{char *str;void *ptr;}value{};void(*destroy)(BufferChunk*)=nullptr;};
struct Buffer {BufferChunk chunk;bool occupied=false;unsigned popped=0;explicit Buffer(int){}BufferChunk *front(){assert(occupied);return &chunk;}BufferChunk *alloc(int type,int length){assert(type==1&&length==0&&!occupied);occupied=true;return &chunk;}void pop(){assert(occupied);if(chunk.destroy)chunk.destroy(&chunk);occupied=false;++popped;}~Buffer(){if(occupied&&chunk.destroy)chunk.destroy(&chunk);}};
template<class T> uint64_t time(bool){return 123;}
struct Socket {Buffer *out_buffer=nullptr;int fd=17,close_wait=0,send_wait=0;void *send_timer=nullptr;uint64_t last_sent_time=0;size_t send_size=1;bool cork_result=true;unsigned sends=0,corks=0,uncorks=0;std::string supplied;
ssize_t send(const void *p,size_t n,int flags){assert(flags==0&&n>0&&send_size<=n);++sends;supplied.assign(static_cast<const char*>(p),n);return send_size;}
ssize_t sendfile(const File&,off_t *offset,size_t n){assert(n>0&&send_size<=n);++sends;*offset+=send_size;return send_size;}
bool cork(){++corks;return cork_result;}bool uncork(){++uncorks;return true;}int catch_write_error(int){std::abort();}
int handle_send();int handle_sendfile();int sendfile_async(const char*,off_t,size_t);
};
#include "output.inc"
}
int main(){using namespace swoole;unsigned checks=0,cases=0;auto check=[&](bool v){assert(v);++checks;};
check(swr_v1_reactor_output_layout(0)==sizeof(swr_v1_reactor_output_action));check(swr_v1_reactor_output_layout(1)==alignof(swr_v1_reactor_output_action));check(swr_v1_reactor_output_layout(2)==offsetof(swr_v1_reactor_output_action,value));
std::string data("abcdef\0ghijklmnop",17);
for(size_t remaining:{size_t(1),size_t(7),size_t(13)})for(size_t sent=1;sent<=remaining;++sent){Buffer buffer(16);Socket socket;socket.out_buffer=&buffer;socket.send_size=sent;buffer.occupied=true;buffer.chunk.length=remaining+3;buffer.chunk.offset=3;buffer.chunk.value.str=&data[0];auto rc=socket.handle_send();check(rc==(sent==remaining?SW_OK:SW_ERR));check(socket.supplied==data.substr(3,remaining));check(socket.sends==1);check(buffer.popped==(sent==remaining));check(socket.send_wait==(sent<remaining));if(sent<remaining)check(buffer.chunk.offset==3+sent);check(socket.close_wait==0);++cases;}
for(bool existing:{false,true})for(size_t length:{size_t(0),size_t(1),size_t(7),size_t(19)})for(bool timer:{false,true})for(bool cork_ok:{false,true}){
Socket socket;std::unique_ptr<Buffer> supplied;if(existing){supplied.reset(new Buffer(16));socket.out_buffer=supplied.get();}socket.cork_result=cork_ok;socket.send_timer=timer?&socket:nullptr;
check(socket.sendfile_async("ordinary-file",2,length)==SW_OK);std::unique_ptr<Buffer> allocated;if(!existing)allocated.reset(socket.out_buffer);check(socket.out_buffer!=nullptr);auto *task=static_cast<SendfileRequest*>(socket.out_buffer->front()->value.ptr);const size_t actual_length=length?length:29;check(task->begin==2&&task->end==static_cast<off_t>(actual_length+2));check(socket.out_buffer->front()->destroy==Socket_sendfile_destructor);size_t remaining=actual_length;unsigned iterations=0;
while(remaining){socket.send_size=std::min<size_t>(3,std::min(remaining,size_t(SW_SENDFILE_CHUNK_SIZE)));remaining-=socket.send_size;check(socket.handle_sendfile()==SW_OK);++iterations;if(remaining){auto *live=static_cast<SendfileRequest*>(socket.out_buffer->front()->value.ptr);check(live->begin==static_cast<off_t>(actual_length+2-remaining));check(live->end==static_cast<off_t>(actual_length+2));}}
check(socket.sends==iterations);check(socket.corks==(actual_length>SW_SOCKET_CORK_MIN_SIZE));check(socket.uncorks==(actual_length>SW_SOCKET_CORK_MIN_SIZE&&cork_ok));check(socket.out_buffer->popped==1);check(!socket.out_buffer->occupied);check(socket.last_sent_time==(timer?123u:0u));check(socket.send_wait==0&&socket.close_wait==0);++cases;}
std::cout<<"{\"cases\":"<<cases<<",\"checks\":"<<checks<<",\"layout_facts\":3,\"positive_lengths_and_sends_only\":true}\n";
}
