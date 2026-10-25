#include <cassert>
#include <csetjmp>
#include <sys/wait.h>
#include <cerrno>
#include <cstdarg>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>
#include <unordered_map>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>
#ifdef __APPLE__
#include <sys/event.h>
#endif
static std::jmp_buf callback_jump;
#include "swoole_rs_reactor.h"
using swoole::swr_reactor_interest;
constexpr int SW_OK=0, SW_EVENT_READ=512, SW_EVENT_WRITE=1024, SW_EVENT_ONCE=4096;
// Normalized test event bits are disjoint; actual platform constants below.
#ifndef __linux__
constexpr unsigned EPOLLIN=1, EPOLLOUT=4, EPOLLERR=8, EPOLLHUP=16, EPOLLRDHUP=8192;
#else
#include <sys/epoll.h>
#endif
struct Socket { int events=0; int removed=0; int fd=7,fd_type=3,event_hup=0; };
struct Event { Socket *socket; int fd=7, type=3,reactor_id=0; };
struct Raw { int revents=0; unsigned events=0; int fd=7; struct {void *ptr=nullptr;} data; };
struct Kevent { int filter=-1; void *udata=nullptr; };
#ifndef EVFILT_READ
constexpr int EVFILT_READ=-1,EVFILT_WRITE=-2;
#endif
struct Runner;
using Handler=int (*)(Runner *, Event *);
struct Runner {
    Socket socket;
    Event event{&socket};
    Raw events_[2];
    Kevent kevents_[1];
    int id=9,batch=1;
    std::unordered_map<int,Socket*> sockets;
    Runner() {sockets[7]=&socket;events_[0].data.ptr=&socket;kevents_[0].udata=&socket;}
    bool exists(int fd) {return sockets.count(fd);}
    Socket *get_socket(int fd) {return sockets.at(fd);}
    bool fetch_event(Event *,void *);
    void del_once_socket(Socket *);
    Runner *reactor_=this;
    Handler handler=nullptr;
    Socket *victim=nullptr,*replacement=nullptr;
    int replacement_fd=-1;
    int ret=0, mutation=0, kind=0, callback_count=0;
    std::vector<std::string> trace;
    static int callback(Runner *r, Event *e) {
        r->trace.push_back(std::to_string(r->kind)+":"+std::to_string(e->socket->events)+":"+std::to_string(errno));
        if (++r->callback_count==1) {
            switch(r->mutation) {
            case 1: e->socket->removed=1; break;
            case 8:
                r->sockets.erase(r->victim->fd); r->victim->removed=1;
                assert(close(r->victim->fd)==0);
                assert(dup2(r->replacement_fd,r->victim->fd)==r->victim->fd);
                r->sockets[r->replacement->fd]=r->replacement;
                break;
            case 9: std::longjmp(callback_jump,1);
            case 2: e->socket->events ^= SW_EVENT_ONCE; break;
            case 3: r->kevents_[0].filter=EVFILT_WRITE; r->events_[0].revents=POLLOUT; r->events_[0].events=EPOLLOUT; break;
            case 4: r->events_[0].revents=POLLERR; r->events_[0].events=EPOLLERR; break;
            case 5: r->events_[0].revents=0; r->events_[0].events=0; break;
            case 6: e->socket->removed=1; e->socket->removed=0; e->socket->events=SW_EVENT_ONCE; break;
            }
        }
        errno=EAGAIN;
        return r->mutation==7 ? -1 : 0;
    }
    Handler get_handler(int, int e) { kind=e; return callback; }
    Handler get_error_handler(int) { kind=3; return callback; }
    void _del(Socket *s) { trace.push_back("delete"); s->removed=1; s->events=0; }
    void del(Socket *s) { _del(s); }
    void log(const char *format) { trace.push_back(format); errno=ERANGE; }
    void run_kqueue_0(); void run_kqueue_1();
    void run_poll_0(); void run_poll_1(); void run_epoll_0(); void run_epoll_1();
};
#define sw_unlikely(x) (x)
#define swoole_trace(...) ((void)0)
#define swoole_sys_warning(format, ...) log(format)
#define swoole_print_backtrace_on_error() trace.push_back("backtrace")
struct InterestBase {
    mutable std::vector<int> trace;
    bool fail=false;
    int call(Socket *s,int e,int op) const {
        trace.insert(trace.end(), {op,s->events,e});
        if(fail) {errno=EBADF;return -1;}
        s->events=op==3?0:e; s->removed=op==3; return 0;
    }
    int set(Socket *s,int e) const {return call(s,e,1);}
    int add(Socket *s,int e) const {return call(s,e,2);}
    int del(Socket *s) const {return call(s,0,3);}
};
#include "actual.inc"
static void run(Runner &r, int backend, int candidate) {
    errno=EDOM;
    if(backend==0) {if(candidate)r.run_poll_1();else r.run_poll_0();}
    else if(backend==1) {if(candidate)r.run_epoll_1();else r.run_epoll_0();}
    else {if(candidate)r.run_kqueue_1();else r.run_kqueue_0();}
}
static void compare(int backend,int raw,int mutation,int once,int removed) {
    Runner a,b;
    a.socket.events=b.socket.events=SW_EVENT_READ|SW_EVENT_WRITE|(once?SW_EVENT_ONCE:0);
    a.socket.removed=b.socket.removed=removed;
    a.mutation=b.mutation=mutation;
    a.kevents_[0].filter=b.kevents_[0].filter=raw?EVFILT_WRITE:EVFILT_READ;
    a.events_[0].revents=b.events_[0].revents=raw;
    a.events_[0].events=b.events_[0].events=raw;
    run(a,backend,0); int original_errno=errno;
    run(b,backend,1);
    assert(a.trace==b.trace);
    assert(a.socket.events==b.socket.events && a.socket.removed==b.socket.removed);
    assert(errno==original_errno);
}
template<class T> int interest(T &r,Socket &s,int op,int bits) {
    switch(op) {
    case 0:return r.add_event(&s,bits); case 1:return r.del_event(&s,bits);
    case 2:return r.remove_read_event(&s); case 3:return r.remove_write_event(&s);
    case 4:return r.add_read_event(&s); default:return r.add_write_event(&s);
    }
}
int main() {
    unsigned count=0;
    const int poll_bits[]={POLLIN,POLLOUT,POLLERR,POLLHUP,POLLNVAL};
    const int epoll_bits[]={EPOLLIN,EPOLLOUT,EPOLLERR,EPOLLHUP,EPOLLRDHUP};
    for(int backend=0;backend<2;backend++) for(int mask=0;mask<32;mask++) {
        int raw=0; for(int i=0;i<5;i++) if(mask&(1<<i))raw|=(backend?epoll_bits:poll_bits)[i];
        for(int mutation=0;mutation<8;mutation++) for(int once=0;once<2;once++) for(int removed=0;removed<2;removed++) {
            compare(backend,raw,mutation,once,removed); ++count;
        }
    }
    for(int raw=0;raw<2;raw++)for(int mutation=0;mutation<8;mutation++)for(int once=0;once<2;once++)for(int removed=0;removed<2;removed++){compare(2,raw,mutation,once,removed);++count;}
    unsigned interests=0;
    const int options[]={0,SW_EVENT_READ,SW_EVENT_WRITE,SW_EVENT_READ|SW_EVENT_WRITE,SW_EVENT_ONCE,SW_EVENT_READ|SW_EVENT_ONCE,SW_EVENT_WRITE|SW_EVENT_ONCE,SW_EVENT_READ|SW_EVENT_WRITE|SW_EVENT_ONCE};
    for(int events:options)for(int bits:options)for(int op=0;op<6;op++)for(int fail=0;fail<2;fail++) {
        Interest0 a; Interest1 b; a.fail=b.fail=fail;
        Socket sa,sb; sa.events=sb.events=events;
        errno=EDOM; int ra=interest(a,sa,op,bits), ea=errno;
        errno=EDOM; int rb=interest(b,sb,op,bits);
        assert(ra==rb && ea==errno && sa.events==sb.events && sa.removed==sb.removed && a.trace==b.trace); ++interests;
    }
    int pair[2]; assert(socketpair(AF_UNIX,SOCK_STREAM,0,pair)==0);
    assert(write(pair[0],"x",1)==1);
    pollfd p{pair[1],POLLIN|POLLOUT,0}; assert(poll(&p,1,1000)==1);
    assert(p.revents&POLLIN); compare(0,p.revents,0,1,0);
#ifdef __linux__
    int kernel=epoll_create1(0); assert(kernel>=0); epoll_event ee{};
    ee.events=EPOLLIN|EPOLLOUT; ee.data.ptr=nullptr;
    assert(epoll_ctl(kernel,EPOLL_CTL_ADD,pair[1],&ee)==0);
    assert(epoll_wait(kernel,&ee,1,1000)==1); compare(1,ee.events,0,1,0); close(kernel);
#else
    int kernel=kqueue(); assert(kernel>=0); struct kevent change,event;
    EV_SET(&change,pair[1],EVFILT_READ,EV_ADD,0,0,nullptr);
    assert(kevent(kernel,&change,1,nullptr,0,nullptr)==0);
    timespec timeout{1,0}; assert(kevent(kernel,nullptr,0,&event,1,&timeout)==1);
    assert(event.filter==EVFILT_READ);compare(2,0,0,1,0);close(kernel);
#endif
    close(pair[0]); p.revents=0; assert(poll(&p,1,1000)==1); compare(0,p.revents,0,1,0);close(pair[1]);
    // A pending numeric poll fd resolves to the replacement registration. Epoll
    // retains the removed old pointer. Preserve this existing backend difference.
    for(int backend=0;backend<2;backend++)for(int candidate=0;candidate<2;candidate++) {
        int old_pair[2], fresh_pair[2];
        assert(socketpair(AF_UNIX,SOCK_STREAM,0,old_pair)==0);
        assert(socketpair(AF_UNIX,SOCK_STREAM,0,fresh_pair)==0);
        assert(write(old_pair[0],"a",1)==1 && write(old_pair[1],"b",1)==1);
        pollfd pending[2]={{old_pair[0],POLLIN,0},{old_pair[1],POLLIN,0}};
        assert(poll(pending,2,1000)==2);
        assert((pending[0].revents&POLLIN) && (pending[1].revents&POLLIN));
        Runner r; Socket old,replacement;
        old.fd=old_pair[1]; replacement.fd=old.fd;
        r.victim=&old; r.replacement=&replacement; r.replacement_fd=fresh_pair[1];r.mutation=8;r.batch=2;
        r.socket.fd=old_pair[0]; r.events_[0].fd=r.socket.fd;
        r.sockets.clear(); r.sockets[r.socket.fd]=&r.socket; r.sockets[old.fd]=&old;
        r.events_[0].revents=pending[0].revents;r.events_[0].events=EPOLLIN;
        r.events_[1].revents=pending[1].revents;r.events_[1].events=EPOLLIN;r.events_[1].fd=old.fd;r.events_[1].data.ptr=&old;
        run(r,backend,candidate);
        assert(r.callback_count==(backend==0?2:1));
        assert(old.removed && !replacement.removed);
        char byte;assert(recv(old.fd,&byte,1,MSG_DONTWAIT)==-1 && (errno==EAGAIN||errno==EWOULDBLOCK));
        close(old_pair[0]);close(old_pair[1]);close(fresh_pair[0]);close(fresh_pair[1]);
    }
    // Native bailout happens after Rust returns. No Rust frame or reference is
    // abandoned, and restarting creates independent readiness state.
    for(int backend=0;backend<3;backend++)for(int candidate=0;candidate<2;candidate++) {
        Runner *r=new Runner; r->mutation=9;r->events_[0].revents=POLLIN;r->events_[0].events=EPOLLIN;
        if(setjmp(callback_jump)==0){run(*r,backend,candidate);assert(false);}
        assert(r->callback_count==1);r->mutation=0;run(*r,backend,candidate);assert(r->callback_count==2);delete r;
    }
    pid_t child=fork();assert(child>=0);
    if(child==0) {for(int b=0;b<3;b++)compare(b,b==0?POLLIN:(b==1?EPOLLIN:0),0,1,0);_exit(0);}
    int status;assert(waitpid(child,&status,0)==child && WIFEXITED(status) && WEXITSTATUS(status)==0);
    std::cout<<"dispatch="<<count<<" interest="<<interests<<" real_poll=2 real_platform_backend=1 fd_reuse=4 native_bailout=6 fork=1 errors=0\n";
}
