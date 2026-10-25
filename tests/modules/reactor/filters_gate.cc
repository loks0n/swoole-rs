#include <cassert>
#include <cerrno>
#include <cstdarg>
#include <cstdio>
#include <iostream>
#include <string>
#include <vector>
#ifdef __APPLE__
#include <sys/event.h>
#include <sys/socket.h>
#include <unistd.h>
#endif
#include "swoole_rs_reactor.h"
constexpr int SW_OK=0,SW_ERR=-1,SW_EVENT_READ=512,SW_EVENT_WRITE=1024,SW_EVENT_DEAULT=256;
#ifndef EVFILT_READ
constexpr int EVFILT_READ=-1,EVFILT_WRITE=-2,EV_ADD=1,EV_DELETE=2;
#endif
#ifndef NOTE_EOF
#define NOTE_EOF 2
#endif
constexpr int SW_LOG_WARNING=1,SW_ERROR_EVENT_ADD_FAILED=2,SW_ERROR_EVENT_UPDATE_FAILED=3,SW_ERROR_EVENT_REMOVE_FAILED=4;
struct Socket {int fd=13,fd_type=7,events=0,removed=0;};
struct TestKevent {int fd,filter,flags,fflags; void *udata;};
static void TEST_EV_SET(TestKevent *e,int fd,int filter,int flags,int fflags,int,void *udata) {*e={fd,filter,flags,fflags,udata};}
struct FiltersBase;
static FiltersBase *active;
struct FiltersBase {
    FiltersBase *reactor_=this;
    int epfd_=29,id=8,fail_at=0,call_count=0,sys_errno=EIO,removal_errno=EIO;
    bool mutate_on_removal=false, real_kernel=false;
    std::vector<std::string> trace;
    void publish(Socket *s,int events,int op) {trace.push_back("publish:"+std::to_string(op)+":"+std::to_string(s->events));s->events=events;s->removed=op==3;}
    void _add(Socket *s,int events) {publish(s,events,1);}
    void _set(Socket *s,int events) {publish(s,events,2);}
    void _del(Socket *s) {publish(s,0,3);}
    void after_removal_failure(Socket *s) {trace.push_back("removal-failure");errno=removal_errno;if(mutate_on_removal)s->events^=SW_EVENT_WRITE;}
    void error_log(int,int code,const char *format,...) {
        char text[512];va_list args;va_start(args,format);vsnprintf(text,sizeof(text),format,args);va_end(args);
        trace.push_back(std::to_string(code)+":"+text);errno=ERANGE;
    }
};
static int native_kevent(int epfd,TestKevent *event,int n,void *,int,void *) {
    assert(epfd==active->epfd_ && n==1);
    active->trace.push_back("syscall:"+std::to_string(event->fd)+":"+std::to_string(event->filter)+":"+std::to_string(event->flags)+":"+std::to_string(event->fflags));
    if(++active->call_count==active->fail_at){errno=active->sys_errno;return -1;}
#ifdef __APPLE__
    if(active->real_kernel) {
        struct kevent change;
        EV_SET(&change,event->fd,event->filter,event->flags,event->fflags,0,event->udata);
        return ::kevent(epfd,&change,1,nullptr,0,nullptr);
    }
#endif
    return 0;
}
#define swoole_error_log(...) error_log(__VA_ARGS__)
#define swoole_print_backtrace_on_error() trace.push_back("backtrace")
#define swoole_trace_log(...) ((void)0)
#include "filters.inc"
template<class T> int run(T &r,Socket &s,int operation,int events) {
    active=&r;errno=EDOM;
    switch(operation){case 0:return r.add(&s,events);case 1:return r.set(&s,events);default:return r.del(&s);}
}
#ifdef __APPLE__
template<class T> std::vector<std::string> kernel() {
    int pair[2];assert(socketpair(AF_UNIX,SOCK_STREAM,0,pair)==0);
    T r;r.epfd_=kqueue();r.real_kernel=true;assert(r.epfd_>=0);
    Socket s;s.fd=pair[1];
    assert(run(r,s,0,SW_EVENT_READ|SW_EVENT_WRITE)==0);
    assert(write(pair[0],"x",1)==1);
    struct kevent ready[2];timespec timeout{1,0};
    int n=kevent(r.epfd_,nullptr,0,ready,2,&timeout);assert(n>0);
    bool read=false;for(int i=0;i<n;i++)read|=ready[i].filter==EVFILT_READ;assert(read);
    assert(run(r,s,1,SW_EVENT_WRITE)==0);
    assert(run(r,s,2,0)==0 && s.removed);
    close(pair[0]);close(pair[1]);close(r.epfd_);
    // File descriptor numbers are implementation details of each fresh pair.
    return r.trace;
}
#endif
int main() {
    unsigned count=0;
    const int errors[]={EBADF,ENOENT,EIO,ERANGE};
    const int options[]={0,1,255,256,SW_EVENT_READ,SW_EVENT_WRITE,SW_EVENT_READ|SW_EVENT_WRITE,4096,SW_EVENT_READ|4096,SW_EVENT_WRITE|4096,SW_EVENT_READ|SW_EVENT_WRITE|4096,-1};
    for(int events:options)for(int requested:options)for(int op=0;op<3;op++)for(int fail=0;fail<3;fail++)for(int sys:errors)for(int post:errors)for(int removed=0;removed<2;removed++)for(int mutate=0;mutate<2;mutate++) {
        Socket sa,sb;sa.events=sb.events=events;sa.removed=sb.removed=removed;
        Filters0 a;Filters1 b;
        a.fail_at=b.fail_at=fail;a.sys_errno=b.sys_errno=sys;a.removal_errno=b.removal_errno=post;a.mutate_on_removal=b.mutate_on_removal=mutate;
        int ra=run(a,sa,op,requested),ea=errno;int rb=run(b,sb,op,requested);
        assert(ra==rb && ea==errno && sa.events==sb.events && sa.removed==sb.removed && a.trace==b.trace);
        ++count;
    }
    // Explicit partial-update failure: successful READ registration is retained
    // in the kernel executor trace, but native registry publication never occurs.
    Filters1 partial;Socket socket;partial.fail_at=2;
    assert(run(partial,socket,0,SW_EVENT_READ|SW_EVENT_WRITE)==-1);
    assert(partial.call_count==2 && socket.events==0);
    int actual_kernel=0;
#ifdef __APPLE__
    auto original=kernel<Filters0>(),candidate=kernel<Filters1>();assert(original==candidate);actual_kernel=2;
#endif
    std::cout<<"kqueue_registration="<<count<<" partial_failure=1 actual_kernel="<<actual_kernel<<" errors=0\n";
}
