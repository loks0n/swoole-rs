// Included once per original/selected namespace, without a guard.
static bool closed = false;
static double now = 1;
static std::function<void()> diagnostic;
static int last_error = 0;
static std::string number(double value) { std::ostringstream out; out << std::hexfloat << value; return out.str(); }
static double microtime() { record("clock:" + number(now)); return now; }
static void swoole_set_last_error(int e) { last_error=e; record("last-error:"+std::to_string(e)); }
static const char *swoole_strerror(int e) { record("strerror:"+std::to_string(e)); return e ? "native-error" : ""; }
using EventType=uint32_t;
enum TimeoutType { SW_TIMEOUT_READ=1, SW_TIMEOUT_WRITE=2, SW_TIMEOUT_ALL=3 };
struct Coroutine {
    long cid;
    long get_cid() { record("cid:"+std::to_string(cid)); return cid; }
    static void print_socket_bound_error(int fd,const char *event,long cid) {
        record("bound-error:"+std::to_string(fd)+":"+event+":"+std::to_string(cid));
        if(diagnostic) diagnostic();
    }
};
struct Socket {
    struct Native { bool close_wait=false; } native;
    Native *socket=&native;
    Coroutine *read_co=nullptr,*write_co=nullptr;
    int sock_fd=77,errCode=0;
    const char *errMsg="";
    std::string errString;
    bool is_closed() const { record("closed:"+std::to_string(closed)); return closed; }
    const char *get_event_str(EventType event) const;
    void set_timeout(double timeout,int type=SW_TIMEOUT_ALL) const { record("set-timeout:"+number(timeout)+":"+std::to_string(type)); }
#include INLINE_FILE
    struct TimeoutController {
        Socket *socket_;
        double timeout,startup_time;
        bool has_timedout(TimeoutType type);
    };
};
#include METHODS_FILE
