#include <sys/socket.h>
#include <poll.h>
#include <unistd.h>
#include <cstdint>
#include <cstdio>
#include <cstdlib>

enum { SW_OK=0, SW_ERR=-1, SW_ERROR=-2, SW_READY=2, SW_WAIT=1, SW_CONTINUE=3 };
struct Reactor { void *ptr; int remove_read_event(void *) { return 0; } };
struct Socket { bool close_notified=false, ssl_want_read=false; void *ssl=nullptr; long total_recv_bytes=0; };
struct Event { int fd; Socket *socket; };
struct Counters { long total_recv_bytes=0; };
struct Connection {
    int server_fd=1; bool close_queued=false, active=true;
    double last_recv_time=0;
    int recv_queued_bytes=0, waiting_time=0; void *timer=nullptr;
};
static int reads,writes,checks,failures;
struct ListenPort {
    Counters data; Counters *gs=&data;
    int onRead(Reactor *, ListenPort *, Event *) { ++reads; return 42; }
};
struct Server {
    Connection conn; ListenPort port; Counters data; Counters *gs=&data; int max_queued_bytes=0;
    Connection *get_connection(int) { return &conn; }
    ListenPort *get_port_by_fd(int) { return &port; }
    bool is_process_mode() { return false; }
    void abort_connection(Reactor *, ListenPort *, Socket *) { std::abort(); }
};
using ReturnCode=int;
static double microtime() { return 0; }
static ReturnCode ReactorThread_verify_ssl_state(Reactor *, ListenPort *, Socket *) { return SW_CONTINUE; }
static int ReactorThread_onWrite(Reactor *, Event *) { ++writes; return 43; }
static void ReactorThread_resume_data_receiving(void *) {}
static void *swoole_timer_add(long, bool, void (*)(void *), void *) { std::abort(); }
static void sw_atomic_fetch_add(long *target, long n) { *target += n; }
// ACTUAL_ON_READ
static void check(bool condition, const char *name) {
    ++checks; if (!condition) { ++failures; std::fprintf(stderr,"FAIL %s\n",name); }
}
int main() {
    int pair[2]; if (socketpair(AF_UNIX,SOCK_STREAM,0,pair)) return 2;
    if (shutdown(pair[0],SHUT_WR)) return 2;
    pollfd cached{pair[1],POLLIN,0};
    if (poll(&cached,1,1000)!=1 || !(cached.revents&POLLIN)) return 2;
    Server server; Reactor reactor{&server}; Socket socket; Event event{pair[1],&socket};
    check(ReactorThread_onRead(&reactor,&event)==42 && reads==1,"ordinary readable protocol callback preserved");
    // A close command can be handled after poll returns but before this cached read event is dispatched.
    server.conn.close_queued=true; reads=0;
    check(ReactorThread_onRead(&reactor,&event)==SW_OK && reads==0 && writes==0,
          "cached plain read cannot enter application protocol after close queues");
    reads=0;
    socket.ssl=&server; socket.ssl_want_read=true;
    check(ReactorThread_onRead(&reactor,&event)==43 && reads==0 && writes==1,
          "queued TLS shutdown read readiness reaches existing write retry");
    socket.close_notified=true;
    check(ReactorThread_onRead(&reactor,&event)==SW_OK && reads==0 && writes==1,
          "terminal close notification remains guarded");
    close(pair[0]); close(pair[1]);
    std::printf("{\"checks\":%d,\"failures\":%d}\n",checks,failures);
    return failures?1:0;
}
