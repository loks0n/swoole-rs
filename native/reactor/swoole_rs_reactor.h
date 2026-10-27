#ifndef SWOOLE_RS_REACTOR_H
#define SWOOLE_RS_REACTOR_H
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <sys/types.h>
#include <sys/socket.h>
#ifdef __APPLE__
#include <TargetConditionals.h>
#endif
#ifdef __cplusplus
extern "C" {

#endif
typedef struct { uint32_t phase; int32_t action; int64_t value; } swr_v1_reactor_output_action;
/* Complete output workflow POD: no Native object/pointer is retained. */
typedef struct {
    uint32_t phase, pending, requested, flags, length, offset;
    int32_t corked, error;
    int64_t begin, end, result;
    int32_t previous_action, validation;
} swr_v1_reactor_output_workflow_state;
swr_v1_reactor_output_action swr_v1_reactor_output_workflow(swr_v1_reactor_output_workflow_state *, uint32_t, int64_t, int64_t);

swr_v1_reactor_output_action swr_v1_reactor_output_data(uint32_t, uint32_t, uint32_t, uint32_t, intptr_t, int32_t);
swr_v1_reactor_output_action swr_v1_reactor_output_file(uint32_t, int32_t, int64_t, int64_t, int64_t, intptr_t, int32_t, uint32_t);
swr_v1_reactor_output_action swr_v1_reactor_output_request(uint32_t, int32_t, uint32_t);
size_t swr_v1_reactor_output_chunk(int64_t, int64_t, size_t);
size_t swr_v1_reactor_output_layout(uint32_t);
swr_v1_reactor_output_action swr_v1_reactor_output_parameters(uint32_t, int32_t, int64_t, int64_t, size_t, int64_t);

struct iovec;
/* Rust-owned IOVector descriptor storage, used by every Rust reactor build. */
typedef struct { struct iovec *original, *iterator; int32_t status; } swr_v1_reactor_iov_allocation;
swr_v1_reactor_iov_allocation swr_v1_reactor_iov_owned_new(const struct iovec *, int32_t);
void swr_v1_reactor_iov_owned_free(struct iovec *);
size_t swr_v1_reactor_iov_owned_length(const struct iovec *, int32_t);
size_t swr_v1_reactor_iov_owned_layout(uint32_t);
typedef struct { size_t offset_bytes, advance, consumed; int32_t remain_count, index, action; } swr_v1_reactor_iov_progress_reply;
size_t swr_v1_reactor_iov_progress_layout(uint32_t);
swr_v1_reactor_iov_progress_reply swr_v1_reactor_iov_owned_progress(struct iovec *, intptr_t, int32_t, int32_t, size_t);

struct pollfd;
struct epoll_event;
struct kevent;
typedef struct { uint32_t phase; } swr_v1_reactor_signal_state;
int32_t swr_v1_reactor_signal_workflow(swr_v1_reactor_signal_state *, int32_t);
typedef struct { uint32_t phase; int32_t action; } swr_v1_reactor_builtin_reply;
swr_v1_reactor_builtin_reply swr_v1_reactor_builtin_step(uint32_t, uint32_t, uint32_t, uint64_t);

typedef struct { uint32_t phase; } swr_v1_reactor_init_state;
typedef struct { int32_t selected; uint32_t observe_kqueue, factory; } swr_v1_reactor_backend_plan;
swr_v1_reactor_backend_plan swr_v1_reactor_backend_type(int32_t, uint32_t, uint32_t, uint32_t);
int32_t swr_v1_reactor_init_next(swr_v1_reactor_init_state *, uint32_t, uint32_t, uint32_t, uint32_t);

typedef struct swr_v1_reactor_deferred swr_v1_reactor_deferred;
int32_t swr_v1_reactor_deferred_push(swr_v1_reactor_deferred **, uintptr_t);
int32_t swr_v1_reactor_deferred_step(swr_v1_reactor_deferred *, uint32_t *, uintptr_t *);
int32_t swr_v1_reactor_deferred_clear(swr_v1_reactor_deferred **, uintptr_t *);

typedef struct swr_v1_reactor_callbacks swr_v1_reactor_callbacks;
typedef struct { int32_t key; uint32_t phase; size_t index; } swr_v1_reactor_callback_cursor;
int32_t swr_v1_reactor_callbacks_lookup(const swr_v1_reactor_callbacks *, uint32_t, int32_t, uintptr_t *);
int32_t swr_v1_reactor_callbacks_erase(swr_v1_reactor_callbacks *, uint32_t, int32_t, uintptr_t *);
int32_t swr_v1_reactor_callbacks_next(const swr_v1_reactor_callbacks *, uint32_t, swr_v1_reactor_callback_cursor *, uint32_t, uintptr_t *);
typedef struct { swr_v1_reactor_callback_cursor cursor; uint32_t kind; } swr_v1_reactor_callback_copy;
int32_t swr_v1_reactor_callbacks_ensure(swr_v1_reactor_callbacks **, uint32_t, int32_t, uintptr_t, uintptr_t *);
int32_t swr_v1_reactor_callbacks_copy_next(const swr_v1_reactor_callbacks *, swr_v1_reactor_callback_copy *, uintptr_t *);
int32_t swr_v1_reactor_callbacks_clear_next(swr_v1_reactor_callbacks **, uintptr_t *);
size_t swr_v1_reactor_callbacks_copy_layout(uint32_t);
/* Each backend's whole wait() loop in one call (#336, #391). Rust runs the loop and its readiness
   order; these are the native effects, each passed `context` (prepare/remove also the socket). */
enum { SWR_REACTOR_POLL, SWR_REACTOR_EPOLL, SWR_REACTOR_KQUEUE };
typedef struct {
    void *context;
    uint32_t backend;
    const void *events;     /* pollfd, epoll_event or kevent entries */
    void *const *sockets;   /* poll: the socket of each pollfd entry */
    const bool *running, *once;
    int (*wait)(void *, int *entries); /* the kernel wait; poll stores its entry count */
    void (*before_wait)(void *);
    void (*begin)(void *);
    int (*catch_error)(void *);
    void (*end)(void *, int timed_out);
    int (*interrupted)(void *); /* nullable: epoll io_uring builds only */
    void (*interrupt)(void *);  /* nullable */
    void (*wait_failed)(void *);
    void (*prepare)(void *, void *socket, int fd, int hup); /* fd -1: the socket's own */
    int (*removed)(void *socket);
    int (*oneshot)(void *socket);
    int (*handle)(void *, uint32_t kind); /* 0 read, 1 write, 2 error */
    void (*handler_failed)(void *, uint32_t kind);
    void (*remove)(void *, void *socket);
    void (*signal)(void *signal);      /* nullable: kqueue only */
    void (*unknown)(void *, int filter); /* nullable: kqueue only */
} swr_v1_reactor_wait_ops;
int32_t swr_v1_reactor_run(const swr_v1_reactor_wait_ops *);
typedef struct { size_t size, alignment, fields[6]; } swr_v1_reactor_backend_layout;
#if defined(__linux__) && !defined(__ANDROID__)
typedef struct swr_v1_reactor_epoll_events swr_v1_reactor_epoll_events;
swr_v1_reactor_epoll_events *swr_v1_reactor_epoll_new(size_t);
void swr_v1_reactor_epoll_free(swr_v1_reactor_epoll_events *);
struct epoll_event *swr_v1_reactor_epoll_data(swr_v1_reactor_epoll_events *);
swr_v1_reactor_backend_layout swr_v1_reactor_epoll_layout(void);
#endif
#if (defined(__APPLE__) && TARGET_OS_OSX) || defined(__FreeBSD__) || defined(__OpenBSD__) || defined(__NetBSD__) || defined(__DragonFly__)
typedef struct swr_v1_reactor_kqueue_events swr_v1_reactor_kqueue_events;
swr_v1_reactor_kqueue_events *swr_v1_reactor_kqueue_new(size_t);
void swr_v1_reactor_kqueue_free(swr_v1_reactor_kqueue_events *);
struct kevent *swr_v1_reactor_kqueue_data(swr_v1_reactor_kqueue_events *);
swr_v1_reactor_backend_layout swr_v1_reactor_kqueue_layout(void);
#endif
typedef struct swr_v1_reactor_poll_snapshot swr_v1_reactor_poll_snapshot;
typedef struct { size_t size, alignment, fd, events, revents; } swr_v1_reactor_poll_layout_info;
swr_v1_reactor_poll_layout_info swr_v1_reactor_poll_layout(void);
swr_v1_reactor_poll_snapshot *swr_v1_reactor_poll_new(size_t);
void swr_v1_reactor_poll_free(swr_v1_reactor_poll_snapshot *);
/* Actual target libc pollfd storage, borrowed until owner destruction. */
struct pollfd *swr_v1_reactor_poll_data(swr_v1_reactor_poll_snapshot *);
typedef struct { uint32_t phase; } swr_v1_reactor_flush_state;
typedef struct { int64_t seconds, nanoseconds; uint32_t finite; } swr_v1_reactor_kqueue_timeout_result;
// Independent zero state; requests10running/11EINTR/12uring-handler/13once.
swr_v1_reactor_kqueue_timeout_result swr_v1_reactor_kqueue_timeout(int32_t, uint32_t);
// Independent zero-initialized workflow states; effects1..7, observations10..15.
int32_t swr_v1_reactor_flush_workflow(swr_v1_reactor_flush_state *, int32_t);
typedef struct { uint32_t offset, length, close_wait; } swr_v1_stream_view_action;
int32_t swr_v1_stream_prepare(uint8_t *, size_t);
int32_t swr_v1_stream_length(const uint8_t *, size_t);
swr_v1_stream_view_action swr_v1_stream_view(uint32_t);
/* network::Socket's descriptor options, syscall included. fd_option: -1 leaves a
 * flag alone. warnings: fd_option 1 F_GETFL, 2 F_SETFL, 4 F_GETFD, 8 F_SETFD failed;
 * cork/uncork 1 TCP_CORK, 2 TCP_NODELAY failed. */
typedef struct { bool ok; uint32_t warnings; } swr_v1_socket_option_result;
typedef struct { uint8_t tcp_nopush, tcp_nodelay; } swr_v1_socket_cork_state;
swr_v1_socket_option_result swr_v1_socket_fd_option(int fd, int nonblock, int cloexec);
int swr_v1_socket_tcp_nopush(int fd, int nopush);
bool swr_v1_socket_tcp_nodelay(int fd, int nodelay);
swr_v1_socket_option_result swr_v1_socket_cork(int fd, swr_v1_socket_cork_state *state);
swr_v1_socket_option_result swr_v1_socket_uncork(int fd, bool enable_tcp_nodelay, swr_v1_socket_cork_state *state);
bool swr_v1_socket_buffer_size(int fd, bool recv, bool send, uint32_t size);
bool swr_v1_socket_kernel_timeout(int fd, bool send, double timeout);
bool swr_v1_socket_listen(int fd, int backlog, int default_backlog);
/* network::Socket's descriptor I/O. status 0 ready; 1 timed out (wait) or
 * EINPROGRESS (connect); 2 failed with errno `error`. */
typedef struct { int status, error; } swr_v1_socket_io_result;
struct sockaddr;
swr_v1_socket_io_result swr_v1_socket_wait(int fd, int16_t events, int timeout_ms, bool dont_restart, void (*dispatch)(void));
void swr_v1_socket_clean(int fd);
ssize_t swr_v1_socket_recvfrom(int fd, void *buffer, size_t length, int flags, struct sockaddr *address, socklen_t *address_length, uint32_t retries);
int swr_v1_socket_accept(int fd, struct sockaddr *address, socklen_t *address_length, bool nonblock, bool *listener_cloexec);
swr_v1_socket_io_result swr_v1_socket_connect(int fd, const struct sockaddr *address, socklen_t length);
/* getsockname/getpeername/bind: caller sets *address_length to the storage
 * capacity; native code keeps the address type and the bound flag. */
bool swr_v1_socket_get_name(int fd, struct sockaddr *address, socklen_t *address_length);
bool swr_v1_socket_get_peer_name(int fd, struct sockaddr *address, socklen_t *address_length);
bool swr_v1_socket_bind(int fd, const struct sockaddr *address, socklen_t length);
swr_v1_socket_io_result swr_v1_socket_pending_error(int fd);
/* sendfile's range check (fstat included) and chunk size: 0 with *end set, 1
 * fstat failed (errno set), 2 empty file, 3 range outside the file. */
int swr_v1_socket_sendfile_range(int file_fd, off_t begin, size_t length, off_t *end);
size_t swr_v1_socket_sendfile_chunk(off_t begin, off_t end);
/* Socket::ssl_recv/ssl_send: ERR_clear_error, SSL_read/SSL_write and SSL_get_error.
 * Native code sets the want flags, then logs (protocol_error) and sets errno
 * (error, when nonzero). */
typedef struct {
    ssize_t value;
    bool want_read;
    bool want_write;
    int error;
    bool protocol_error;
} swr_v1_socket_ssl_io_result;
swr_v1_socket_ssl_io_result swr_v1_socket_ssl_recv(struct ssl_st *ssl, void *buffer, size_t length);
swr_v1_socket_ssl_io_result swr_v1_socket_ssl_send(struct ssl_st *ssl, const void *buffer, size_t length);
/* Socket::ssl_accept/ssl_connect: one SSL_accept/SSL_connect step and its
 * classification. Native code sets the want flags, ssl_state (state >= 0) and the
 * last error (when nonzero), then logs: 1 bad client, 2 failed handshake with
 * ssl_error, 3 peer closed (connect). code is the method's return value. */
typedef struct {
    int code;
    bool want_read;
    bool want_write;
    int state;
    int last_error;
    int log;
    int ssl_error;
} swr_v1_socket_ssl_handshake_result;
swr_v1_socket_ssl_handshake_result swr_v1_socket_ssl_accept(struct ssl_st *ssl, bool dtls);
swr_v1_socket_ssl_handshake_result swr_v1_socket_ssl_connect(struct ssl_st *ssl);
/* Socket::ssl_check_host: X509_check_host on the peer certificate (consumed; may be
 * null): 0 none, 1 match, 2 no match. Socket::ssl_verify: the verify error that
 * rejects the peer, or X509_V_OK (a self-signed leaf passes when allowed). */
int swr_v1_socket_ssl_check_host(struct x509_st *cert, const char *name, size_t length);
long swr_v1_socket_ssl_verify(const struct ssl_st *ssl, bool allow_self_signed);
/* network::Socket's per-request reads and writes: recv/send/peek with EINTR and
 * dont_restart, driving `tls` (ssl_recv/ssl_send/SSL_peek on `socket`) when set;
 * catch_error's classification (swReturnCode). */
typedef ssize_t (*swr_v1_socket_tls_io)(void *socket, void *buffer, size_t length);
ssize_t swr_v1_socket_recv(int fd, void *buffer, size_t length, int flags, bool nonblock, bool dont_restart, swr_v1_socket_tls_io tls, void *socket);
ssize_t swr_v1_socket_send(int fd, const void *buffer, size_t length, int flags, bool dont_restart, swr_v1_socket_tls_io tls, void *socket);
ssize_t swr_v1_socket_peek(int fd, void *buffer, size_t length, int flags, swr_v1_socket_tls_io tls, void *socket);
/* Socket::readv/writev: readv(2)/writev(2) over state's remaining iovecs, or tls one
 * iovec at a time until one comes up short; advances state like
 * IOVector::update_iterator and retries EINTR. Native code copies the IOVector's
 * cursor in and back. */
typedef struct {
    struct iovec *iterator;
    int remain_count;
    int index;
    size_t offset_bytes;
} swr_v1_socket_iov_state;
ssize_t swr_v1_socket_iov(int fd, bool write, swr_v1_socket_iov_state *state, swr_v1_socket_tls_io tls, void *socket);
int swr_v1_socket_catch_error(int error, bool *kernel_nobufs);
/* network::Socket's swSocketType <-> (domain, type), and the type a host names
 * with how many leading bytes convert_to_type erases. */
typedef struct { int socket_type; size_t erase; } swr_v1_socket_host_type_plan;
int swr_v1_socket_type(int domain, int type);
bool swr_v1_socket_domain_and_type(int socket_type, int *domain, int *type);
swr_v1_socket_host_type_plan swr_v1_socket_host_type(const uint8_t *host, size_t length);
/* swoole::socket: socket(2) with SW_SOCK_NONBLOCK/SW_SOCK_CLOEXEC applied. */
int swr_v1_socket_open(int domain, int type, int protocol, int flags);
#ifdef __cplusplus
}
static_assert(sizeof(swr_v1_reactor_builtin_reply) == 8, "reactor builtin reply ABI");
static_assert(sizeof(swr_v1_reactor_init_state) == 4, "reactor init state ABI");
static_assert(sizeof(swr_v1_reactor_backend_plan) == 12, "reactor backend plan ABI");
static_assert(sizeof(swr_v1_stream_view_action) == 12, "stream view ABI");
static_assert(sizeof(swr_v1_reactor_flush_state) == 4, "flush state ABI");
#include <functional>
namespace swoole {
class Reactor;
// The private member keeps Native payload effects outside Rust. Its placement
// before sockets_ preserves Native member destruction order after Reactor body.
class ReactorCallbacks {
    swr_v1_reactor_callbacks *owner_ = nullptr;
    template<class Function> Function *ensure(uint32_t kind, int32_t key);
    void clear() noexcept;
    void copy_from(const ReactorCallbacks &);
  public:
    using End = std::function<void(Reactor *)>;
    using Exit = std::function<bool(Reactor *, size_t &)>;
    ReactorCallbacks() = default;
    ReactorCallbacks(const ReactorCallbacks &);
    ReactorCallbacks &operator=(const ReactorCallbacks &);
    ~ReactorCallbacks() noexcept;
    void set_end(int32_t, const End &);
    void set_exit(int32_t, const Exit &);
    void erase_end(int32_t);
    size_t erase_exit(int32_t);
    bool has_exit(int32_t) const;
    void execute_end(Reactor *) const;
    bool if_exit(Reactor *, size_t &) const;
};
}
#endif
#endif
