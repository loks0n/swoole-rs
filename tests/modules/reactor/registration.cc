#include <cassert>
#include <cerrno>
#include <cstdint>
#include <iostream>
#include <map>
#include <string>
#include <vector>
#ifdef __linux__
#include <sys/epoll.h>
#endif
#ifdef __APPLE__
#include <sys/event.h>
#endif
#include "swoole_rs_reactor.h"
constexpr int SW_OK=0, SW_ERR=-1, SW_EVENT_DEAULT=256, SW_EVENT_READ=512, SW_EVENT_WRITE=1024, SW_EVENT_ERROR=2048, SW_EVENT_ONCE=4096;
constexpr int SW_LOG_WARNING=1, SW_ERROR_EVENT_ADD_FAILED=2, SW_ERROR_SOCKET_NOT_EXISTS=3, SW_ERROR_EVENT_REMOVE_FAILED=4, SW_ERROR_EVENT_UPDATE_FAILED=5, SW_TRACE_EVENT=6, SW_TRACE_REACTOR=7;
#ifndef __APPLE__
constexpr int EVFILT_READ=-1, EVFILT_WRITE=-2, EV_ADD=1, EV_DELETE=2;
#endif
static std::vector<std::string> effects;
#define swoole_error_log(...) do { assert(false && "unexpected Native warning in positive profile"); } while(false)
#define swoole_sys_warning(...) do { assert(false && "unexpected Native warning in positive profile"); } while(false)
#define swoole_print_backtrace_on_error() assert(false && "unexpected Native failure in positive profile")
#define swoole_trace(...) effects.emplace_back("trace")
#define swoole_trace_log(...) effects.emplace_back("trace")
struct { int id=1; } SwooleTG;
struct Socket { int fd=7,fd_type=2,events=0; bool removed=false; };
static Socket *current=nullptr;
struct Reactor {
    int id=1;
    std::map<int,Socket*> sockets;
    bool _exists(Socket *s) const { return sockets.count(s->fd)!=0; }
    size_t get_event_num() const { return sockets.size(); }
    void _add(Socket *s,int events) { effects.emplace_back("add"); sockets[s->fd]=s;s->events=events;s->removed=false; }
    void _set(Socket *s,int events) { effects.emplace_back("set");s->events=events; }
    void _del(Socket *s) { effects.emplace_back("del");sockets.erase(s->fd);s->events=0;s->removed=true; }
    static bool isset_read_event(int events) { return events<256 || (events&SW_EVENT_READ); }
    static bool isset_write_event(int events) { return events&SW_EVENT_WRITE; }
    static bool isset_error_event(int events) { return events&SW_EVENT_ERROR; }
};
struct RegistrationBase {
    Reactor *reactor_; int epfd_=3, max_events_=17;
    explicit RegistrationBase(Reactor *r):reactor_(r){}
    void after_removal_failure(Socket*) { assert(false && "unexpected Native removal failure"); }
};
struct FakeKevent { int fd,filter,flags,fflags; void *udata; };
static void TEST_EV_SET(FakeKevent *e,int fd,int filter,int flags,int fflags,int,void *token) {
    e->fd=fd;e->filter=filter;e->flags=flags;e->fflags=fflags;e->udata=token;
}
static int native_kevent(int,const FakeKevent *e,int count,void*,int,void*) {
    assert(count==1 && e->udata==current);
    effects.emplace_back("kqueue:"+std::to_string(e->filter)+":"+std::to_string(e->flags)+":"+std::to_string(e->fflags));
    return 0;
}
#ifdef __linux__
static int native_epoll_ctl(int,int operation,int,epoll_event *e) {
    if(operation!=EPOLL_CTL_DEL) assert(e && e->data.ptr==current);
    effects.emplace_back("epoll:"+std::to_string(operation)+":"+std::to_string(e?e->events:0));
    return 0;
}
#endif
#include "registration.inc"
template<class Backend> std::vector<std::string> run(int events, int updated=SW_EVENT_READ|SW_EVENT_WRITE) {
    effects.clear(); Reactor reactor; Socket socket; current=&socket; Backend backend(&reactor);
    assert(backend.add(&socket,events)==SW_OK);
    assert(reactor._exists(&socket) && socket.events==events);
    assert(backend.set(&socket,updated)==SW_OK);
    assert(socket.events==updated);
    assert(backend.del(&socket)==SW_OK);
    assert(!reactor._exists(&socket) && socket.removed);
    return effects;
}
int main() {
    unsigned cases=0;
    for(int events:{1,SW_EVENT_READ,SW_EVENT_WRITE,SW_EVENT_READ|SW_EVENT_WRITE,SW_EVENT_READ|SW_EVENT_WRITE|SW_EVENT_ONCE,SW_EVENT_READ|SW_EVENT_ERROR,SW_EVENT_READ|SW_EVENT_WRITE|SW_EVENT_ONCE|SW_EVENT_ERROR,2}) {
        const auto poll_original=run<PollOriginal>(events);
        assert(poll_original==run<PollSelected>(events)); ++cases;
        const auto kqueue_original=run<KqueueOriginal>(events);
        assert(kqueue_original==run<KqueueSelected>(events)); ++cases;
#ifdef __linux__
        const auto epoll_original=run<EpollOriginal>(events);
        assert(epoll_original==run<EpollSelected>(events)); ++cases;
#endif
    }
    for(int updated:{SW_EVENT_READ,SW_EVENT_WRITE}) {
        const int both=SW_EVENT_READ|SW_EVENT_WRITE;
        const auto p=run<PollOriginal>(both,updated);
        assert(p==run<PollSelected>(both,updated)); ++cases;
        const auto k=run<KqueueOriginal>(both,updated);
        assert(k==run<KqueueSelected>(both,updated)); ++cases;
#ifdef __linux__
        const auto e=run<EpollOriginal>(both,updated);
        assert(e==run<EpollSelected>(both,updated)); ++cases;
#endif
    }
    std::cout<<"{\"positive_registration_scenarios\":"<<cases<<",\"operations_per_engine\":"<<cases*3
             <<",\"native_faults\":false,\"kernel_syscall_facades\":true,\"allocation_probes\":false}\n";
}
