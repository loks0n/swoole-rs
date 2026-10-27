#ifndef SWOOLE_RS_REACTOR_H
#define SWOOLE_RS_REACTOR_H
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
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
