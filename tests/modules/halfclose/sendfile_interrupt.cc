#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>
#include <fcntl.h>
#include <cerrno>
#include <cstdlib>
#include <cstdio>
#include <chrono>
#include <string>
#include <algorithm>
#include <signal.h>
#include <sys/time.h>
static volatile sig_atomic_t signals;
static void on_signal(int) { ++signals; }

static int warnings, calls;
static bool interrupt_once;
static int boundary_error = EINTR;
enum { SW_OK = 0, SW_ERR = -1, SW_ERROR = -2, SW_CLOSE = -3, SW_WAIT = 1, SW_INVALID = -4 };
static constexpr int SW_ERROR_SSL_BAD_CLIENT = 1000001, SW_ERROR_SSL_RESET = 1000002;
static constexpr int SW_SOCKET_CORK_MIN_SIZE = 65536, SW_SENDFILE_CHUNK_SIZE = 2097152, SW_BUFFER_SIZE_BIG = 8192;
#define swoole_trace(...) ((void) 0)
#define swoole_sys_warning(...) (++warnings)
template <typename T> static double time(bool) { return 0; }
#if defined(__APPLE__)
#define HAVE_SENDFILE 1
#define HAVE_KQUEUE 1
#endif
// ACTUAL_OS_SENDFILE
struct SendfileRequest {
    int file;
    off_t begin = 0, end;
    int corked = -1;
    const char *get_filename() { return "owned fixture"; }
};
struct BufferChunk { struct { void *ptr; } value; };
struct Buffer {
    BufferChunk chunk;
    bool popped = false;
    BufferChunk *front() { return &chunk; }
    void pop() { popped = true; }
};
class Socket {
  public:
    int fd;
    Buffer *out_buffer;
    bool close_wait = false, send_wait = false, kernel_nobufs = false;
    void *send_timer = nullptr;
    double last_sent_time = 0;
    bool cork() { return false; }
    void uncork() {}
    int catch_error(int err);
    int catch_write_error(int err) { return catch_error(err); }
    ssize_t sendfile(int in_fd, off_t *offset, size_t size) {
        ++calls;
        if (interrupt_once) { interrupt_once = false; errno = boundary_error; return -1; }
        return swoole_sendfile(fd, in_fd, offset, size);
    }
    int handle_sendfile();
};
// ACTUAL_SOCKET_METHODS
static int checks, failures;
static void check(bool ok, const char *name) {
    ++checks;
    if (!ok) { ++failures; std::fprintf(stderr, "FAIL %s\n", name); }
}
int main(int argc, char **argv) {
    if (argc < 2) return 2;
    bool real_signal = argc > 2 && std::string(argv[2]) == "signal";
    bool wait_case = argc > 2 && std::string(argv[2]) == "eagain";
    bool close_case = argc > 2 && std::string(argv[2]) == "epipe";
    interrupt_once = argc < 3 || wait_case || close_case;
    boundary_error = wait_case ? EAGAIN : close_case ? EPIPE : EINTR;
    int file = open(argv[1], O_RDONLY), listener = socket(AF_INET, SOCK_STREAM, 0);
    sockaddr_in address{}; address.sin_family = AF_INET; address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    socklen_t len = sizeof(address);
    if (file < 0 || bind(listener, reinterpret_cast<sockaddr *>(&address), len) < 0 ||
        listen(listener, 1) < 0 || getsockname(listener, reinterpret_cast<sockaddr *>(&address), &len) < 0) return 2;
    int client = socket(AF_INET, SOCK_STREAM, 0);
    int small = 4096; setsockopt(client, SOL_SOCKET, SO_RCVBUF, &small, sizeof(small));
    if (connect(client, reinterpret_cast<sockaddr *>(&address), len) < 0) return 2;
    int peer = accept(listener, nullptr, nullptr); close(listener);
    if (peer < 0) return 2;
    std::string expected(8192, '\0');
    if (pread(file, &expected[0], expected.size(), 0) != static_cast<ssize_t>(expected.size())) return 2;
    SendfileRequest task{file, 0, static_cast<off_t>(expected.size())};
    Buffer buffer{{{&task}}}; Socket sender{peer, &buffer};
    bool injected = interrupt_once || real_signal;
    size_t filler = 0;
    if (real_signal) {
        setsockopt(peer, SOL_SOCKET, SO_SNDBUF, &small, sizeof(small));
        fcntl(peer, F_SETFL, O_NONBLOCK);
        char padding[16384]{}; ssize_t sent;
        for (int i = 0; i < 3; ++i) {
            while ((sent = send(peer, padding, sizeof(padding), 0)) > 0) filler += sent;
            usleep(50000);
        }
        fcntl(peer, F_SETFL, 0);
        struct sigaction action{}; action.sa_handler = on_signal; sigemptyset(&action.sa_mask);
        sigaction(SIGALRM, &action, nullptr);
        struct itimerval timer{}; timer.it_value.tv_usec = 10000;
        setitimer(ITIMER_REAL, &timer, nullptr);
    }
    int result = sender.handle_sendfile();
    if (real_signal) {
        int saved_errno = errno;
        struct itimerval timer{}; setitimer(ITIMER_REAL, &timer, nullptr);
        check(signals == 1 && saved_errno == EINTR, "real zero-progress OS syscall interrupted");
        char padding[16384];
        while (filler) {
            ssize_t n = read(client, padding, std::min(filler, sizeof(padding)));
            if (n <= 0) return 2;
            filler -= n;
        }
    }
    if (close_case) {
        check(result == SW_ERR && sender.close_wait && !buffer.popped, "fatal transport preserves caller close contract");
        check(warnings == 0, "fatal transport does not become a file warning");
        close(peer); close(file); close(client);
        std::printf("{\"checks\":%d,\"failures\":%d,\"calls\":%d,\"bytes\":0}\n", checks, failures, calls);
        return failures ? 1 : 0;
    }
    if (wait_case) {
        check(result == SW_ERR && sender.send_wait && !buffer.popped, "backpressure preserves queued file and readiness contract");
        sender.send_wait = false;
    } else {
        check(result == SW_OK && (!injected || !buffer.popped), "interrupted file chunk retained for retry");
    }
    check(warnings == 0, "interruption is not a fatal file error");
    for (int i = 0; !buffer.popped && i < 100; ++i) sender.handle_sendfile();
    close(peer); close(file);
    std::string received; char data[8192]; ssize_t n;
    while ((n = read(client, data, sizeof(data))) > 0) received.append(data, n);
    close(client);
    check(buffer.popped && received == expected && task.begin == task.end, "actual TCP file bytes complete");
    std::printf("{\"checks\":%d,\"failures\":%d,\"calls\":%d,\"bytes\":%zu}\n", checks, failures, calls, received.size());
    return failures ? 1 : 0;
}
