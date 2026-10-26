#ifndef SWOOLE_RS_REACTOR_H
#define SWOOLE_RS_REACTOR_H
#include <stdint.h>
#include <stddef.h>
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
swr_v1_reactor_output_action swr_v1_reactor_output_parameters_workflow(swr_v1_reactor_output_workflow_state *, int64_t, size_t, int64_t);

typedef struct { uint32_t phase; int32_t action, value, seconds, microseconds; } swr_v1_reactor_socket_timeout_reply;
swr_v1_reactor_output_action swr_v1_reactor_socket_buffers(uint32_t, uint32_t, int32_t);
swr_v1_reactor_socket_timeout_reply swr_v1_reactor_socket_timeout(uint32_t, uint32_t, int32_t, int32_t, double);
size_t swr_v1_reactor_socket_timeout_layout(uint32_t);
swr_v1_reactor_output_action swr_v1_reactor_fd_options(uint32_t, int32_t, int32_t, int32_t, int32_t, int32_t, uint32_t);
swr_v1_reactor_output_action swr_v1_reactor_socket_connect(uint32_t operation, uint32_t phase, int32_t observed, double timeout);
swr_v1_reactor_output_action swr_v1_reactor_socket_poll(uint32_t, int32_t, int32_t, int32_t);
swr_v1_reactor_output_action swr_v1_reactor_socket_error(int32_t);
swr_v1_reactor_output_action swr_v1_reactor_socket_cork(uint32_t, uint32_t, int32_t, uint32_t);
swr_v1_reactor_output_action swr_v1_reactor_socket_tcp_option(uint32_t, uint32_t, int32_t, uint32_t);
swr_v1_reactor_output_action swr_v1_reactor_ordinary_io(uint32_t kind, uint32_t phase, int32_t observed, intptr_t result, intptr_t total, size_t length, int32_t flags);
swr_v1_reactor_output_action swr_v1_reactor_output_data(uint32_t, uint32_t, uint32_t, uint32_t, intptr_t, int32_t);
swr_v1_reactor_output_action swr_v1_reactor_output_file(uint32_t, int32_t, int64_t, int64_t, int64_t, intptr_t, int32_t, uint32_t);
swr_v1_reactor_output_action swr_v1_reactor_output_request(uint32_t, int32_t, uint32_t);
size_t swr_v1_reactor_output_chunk(int64_t, int64_t, size_t);
size_t swr_v1_reactor_output_layout(uint32_t);
swr_v1_reactor_output_action swr_v1_reactor_output_parameters(uint32_t, int32_t, int64_t, int64_t, size_t, int64_t);

typedef struct { uint32_t phase; int32_t timeout_msec; double began_at; } swr_v1_reactor_blocking_wait_state;
typedef struct { uint32_t phase; int32_t action; size_t length, offset; intptr_t value; } swr_v1_reactor_blocking_io_reply;
typedef struct { uint32_t phase, flags; } swr_v1_reactor_blocking_file_state;
int32_t swr_v1_reactor_blocking_wait(swr_v1_reactor_blocking_wait_state *, int32_t, double);
swr_v1_reactor_output_action swr_v1_reactor_blocking_event(uint32_t, uint32_t, int32_t);
swr_v1_reactor_blocking_io_reply swr_v1_reactor_blocking_io(uint32_t, uint32_t, size_t, intptr_t, intptr_t, int32_t, int64_t, int64_t);
swr_v1_reactor_output_action swr_v1_reactor_blocking_file(swr_v1_reactor_blocking_file_state *, int32_t, int64_t, int64_t, int64_t);
size_t swr_v1_reactor_blocking_layout(uint32_t, uint32_t);

struct iovec;
/* Rust-owned IOVector descriptor storage, used by every Rust reactor build. */
typedef struct { struct iovec *original, *iterator; int32_t status; } swr_v1_reactor_iov_allocation;
swr_v1_reactor_iov_allocation swr_v1_reactor_iov_owned_new(const struct iovec *, int32_t);
void swr_v1_reactor_iov_owned_free(struct iovec *);
size_t swr_v1_reactor_iov_owned_length(const struct iovec *, int32_t);
size_t swr_v1_reactor_iov_owned_layout(uint32_t);
typedef struct { size_t offset_bytes, advance, consumed; int32_t remain_count, index, action; } swr_v1_reactor_iov_progress_reply;
swr_v1_reactor_iov_progress_reply swr_v1_reactor_iov_progress(const struct iovec *, intptr_t, int32_t, int32_t, size_t);
size_t swr_v1_reactor_iov_progress_layout(uint32_t);
swr_v1_reactor_iov_progress_reply swr_v1_reactor_iov_owned_progress(struct iovec *, intptr_t, int32_t, int32_t, size_t);
typedef struct { size_t length, offset; int32_t status; } swr_v1_reactor_write_arguments;
swr_v1_reactor_write_arguments swr_v1_reactor_write_prepare(uint32_t, const struct iovec *, size_t);
swr_v1_reactor_write_arguments swr_v1_reactor_write_append(uint32_t, size_t, intptr_t);
size_t swr_v1_reactor_iovec_layout(uint32_t);

struct pollfd;
struct epoll_event;
struct kevent;
typedef struct { uint32_t phase, policy_phase; } swr_v1_reactor_write_workflow_state;
typedef struct { size_t buffered; intptr_t sent; uint32_t capacity, flags, nonblock, wait, interrupted; } swr_v1_reactor_write_facts;
size_t swr_v1_reactor_write_workflow_layout(uint32_t, uint32_t);
int32_t swr_v1_reactor_write_workflow(swr_v1_reactor_write_workflow_state *, size_t, swr_v1_reactor_write_facts *);
typedef struct { uint32_t phase; } swr_v1_reactor_signal_state;
int32_t swr_v1_reactor_signal_workflow(swr_v1_reactor_signal_state *, int32_t);
typedef struct { uint32_t phase; int32_t action; } swr_v1_reactor_builtin_reply;
swr_v1_reactor_builtin_reply swr_v1_reactor_builtin_step(uint32_t, uint32_t, uint32_t, uint64_t);

int32_t swr_v1_reactor_handler_select(uint32_t, int32_t, uint32_t);

typedef struct { uint32_t phase; } swr_v1_reactor_init_state;
typedef struct { int32_t selected; uint32_t observe_kqueue, factory; } swr_v1_reactor_backend_plan;
swr_v1_reactor_backend_plan swr_v1_reactor_backend_type(int32_t, uint32_t, uint32_t, uint32_t);
int32_t swr_v1_reactor_init_next(swr_v1_reactor_init_state *, uint32_t, uint32_t, uint32_t, uint32_t);

typedef struct swr_v1_reactor_deferred swr_v1_reactor_deferred;
int32_t swr_v1_reactor_deferred_push(swr_v1_reactor_deferred **, uintptr_t);
int32_t swr_v1_reactor_deferred_step(swr_v1_reactor_deferred *, uint32_t *, uintptr_t *);
int32_t swr_v1_reactor_deferred_clear(swr_v1_reactor_deferred **, uintptr_t *);

typedef struct swr_v1_reactor_callbacks swr_v1_reactor_callbacks;
typedef struct { int32_t key; uint32_t phase; } swr_v1_reactor_callback_cursor;
int32_t swr_v1_reactor_callbacks_lookup(const swr_v1_reactor_callbacks *, uint32_t, int32_t, uintptr_t *);
int32_t swr_v1_reactor_callbacks_insert(swr_v1_reactor_callbacks **, uint32_t, int32_t, uintptr_t, uintptr_t *);
int32_t swr_v1_reactor_callbacks_erase(swr_v1_reactor_callbacks *, uint32_t, int32_t, uintptr_t *);
int32_t swr_v1_reactor_callbacks_next(const swr_v1_reactor_callbacks *, uint32_t, swr_v1_reactor_callback_cursor *, uint32_t, uintptr_t *);
int32_t swr_v1_reactor_callbacks_drain(swr_v1_reactor_callbacks *, uint32_t *, uintptr_t *);
int32_t swr_v1_reactor_callbacks_free(swr_v1_reactor_callbacks *);
typedef struct { swr_v1_reactor_callback_cursor cursor; uint32_t kind; } swr_v1_reactor_callback_copy;
int32_t swr_v1_reactor_callbacks_ensure(swr_v1_reactor_callbacks **, uint32_t, int32_t, uintptr_t, uintptr_t *);
int32_t swr_v1_reactor_callbacks_copy_next(const swr_v1_reactor_callbacks *, swr_v1_reactor_callback_copy *, uintptr_t *);
int32_t swr_v1_reactor_callbacks_clear_next(swr_v1_reactor_callbacks **, uintptr_t *);
size_t swr_v1_reactor_callbacks_copy_layout(uint32_t);
typedef struct { size_t next, current; } swr_v1_reactor_batch_cursor;
typedef struct { uintptr_t token; int32_t fd; uint32_t mask; int32_t filter; uint32_t kind; } swr_v1_reactor_batch_record;
int32_t swr_v1_reactor_poll_record(const struct pollfd *, size_t, swr_v1_reactor_batch_cursor *, uint32_t, swr_v1_reactor_batch_record *);
typedef struct { size_t size, alignment, fields[6]; } swr_v1_reactor_backend_layout;
#if defined(__linux__) && !defined(__ANDROID__)
int32_t swr_v1_reactor_epoll_record(const struct epoll_event *, size_t, swr_v1_reactor_batch_cursor *, uint32_t, swr_v1_reactor_batch_record *);
typedef struct swr_v1_reactor_epoll_events swr_v1_reactor_epoll_events;
swr_v1_reactor_epoll_events *swr_v1_reactor_epoll_new(size_t);
void swr_v1_reactor_epoll_free(swr_v1_reactor_epoll_events *);
struct epoll_event *swr_v1_reactor_epoll_data(swr_v1_reactor_epoll_events *);
swr_v1_reactor_backend_layout swr_v1_reactor_epoll_layout(void);
#endif
#if (defined(__APPLE__) && TARGET_OS_OSX) || defined(__FreeBSD__) || defined(__OpenBSD__) || defined(__NetBSD__) || defined(__DragonFly__)
int32_t swr_v1_reactor_kqueue_record(const struct kevent *, size_t, swr_v1_reactor_batch_cursor *, uint32_t, swr_v1_reactor_batch_record *);
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
int32_t swr_v1_reactor_poll_reset(swr_v1_reactor_poll_snapshot *);
int32_t swr_v1_reactor_poll_push(swr_v1_reactor_poll_snapshot *, int32_t, int32_t);
/* Actual target libc pollfd storage, borrowed until owner destruction. */
struct pollfd *swr_v1_reactor_poll_data(swr_v1_reactor_poll_snapshot *);
int16_t swr_v1_reactor_poll_to(int32_t);
int32_t swr_v1_reactor_poll_from(int16_t);
typedef struct { uint32_t phase; } swr_v1_reactor_ready_state;
typedef struct { swr_v1_reactor_ready_state ready; uint32_t phase, mask, once, callback; } swr_v1_reactor_ready_workflow_state;
int32_t swr_v1_reactor_ready_workflow(swr_v1_reactor_ready_workflow_state *, uint32_t, int32_t);
typedef struct { uint32_t phase; } swr_v1_reactor_flush_state;
typedef struct { uint32_t phase; } swr_v1_reactor_wait_state;
typedef struct { int64_t seconds, nanoseconds; uint32_t finite; } swr_v1_reactor_kqueue_timeout_result;
int32_t swr_v1_reactor_wait_step(swr_v1_reactor_wait_state *, uint32_t, uint32_t, int32_t, uint32_t);
// Independent zero state; requests10running/11EINTR/12uring-handler/13once.
int32_t swr_v1_reactor_wait_workflow(swr_v1_reactor_wait_state *, uint32_t, int32_t);
swr_v1_reactor_kqueue_timeout_result swr_v1_reactor_kqueue_timeout(int32_t, uint32_t);
int32_t swr_v1_reactor_ready_step(swr_v1_reactor_ready_state *, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t);
typedef struct { uint32_t phase, filter; } swr_v1_reactor_registration_state;
int32_t swr_v1_reactor_poll_registration(uint32_t, uint32_t, uint32_t, size_t, int32_t);
int32_t swr_v1_reactor_epoll_registration(swr_v1_reactor_registration_state *, uint32_t, uint32_t, int32_t, int32_t);
#if defined(__linux__) && !defined(__ANDROID__)
uint32_t swr_v1_reactor_epoll_mask(int32_t);
#endif
int32_t swr_v1_reactor_kqueue_registration(swr_v1_reactor_registration_state *, uint32_t, int32_t, uint32_t, int32_t, int32_t);
int32_t swr_v1_reactor_flush_step(swr_v1_reactor_flush_state *, uint32_t, uint32_t, int32_t);
int32_t swr_v1_reactor_drain_step(swr_v1_reactor_flush_state *, uint32_t, int32_t);
// Independent zero-initialized workflow states; effects1..7, observations10..15.
int32_t swr_v1_reactor_flush_workflow(swr_v1_reactor_flush_state *, int32_t);
int32_t swr_v1_reactor_drain_workflow(swr_v1_reactor_flush_state *, int32_t);
typedef struct { int32_t events; uint32_t action, publish; } swr_v1_reactor_interest_action;
int32_t swr_v1_reactor_ready(swr_v1_reactor_ready_state *, uint32_t, uint32_t, uint32_t, uint32_t);
typedef struct { uint32_t offset, length, close_wait; } swr_v1_stream_view_action;
int32_t swr_v1_stream_prepare(uint8_t *, size_t);
int32_t swr_v1_stream_length(const uint8_t *, size_t);
swr_v1_stream_view_action swr_v1_stream_view(uint32_t);
int32_t swr_v1_reactor_write(swr_v1_reactor_ready_state *, size_t, size_t, uint32_t, uint32_t, intptr_t, uint32_t, uint32_t);
int32_t swr_v1_reactor_filter(swr_v1_reactor_ready_state *, uint32_t, int32_t);
int32_t swr_v1_reactor_interest(uint32_t, int32_t, int32_t, swr_v1_reactor_interest_action *);
#ifdef __cplusplus
}
static_assert(sizeof(swr_v1_reactor_builtin_reply) == 8, "reactor builtin reply ABI");
static_assert(sizeof(swr_v1_reactor_init_state) == 4, "reactor init state ABI");
static_assert(sizeof(swr_v1_reactor_backend_plan) == 12, "reactor backend plan ABI");
static_assert(sizeof(swr_v1_stream_view_action) == 12, "stream view ABI");
static_assert(sizeof(swr_v1_reactor_registration_state) == 8, "registration state ABI");
static_assert(sizeof(swr_v1_reactor_flush_state) == 4, "flush state ABI");
static_assert(sizeof(swr_v1_reactor_ready_state) == 4, "readiness state ABI");
static_assert(sizeof(swr_v1_reactor_interest_action) == 12, "interest action ABI");
#include <functional>
#include <cstdlib>
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
// Transient typed Native facts only; original routing performs no effects
// between these ordinary field reads. Rust owns all selection/fallback policy.
template<class ReactorT>
inline auto swr_reactor_resolve_handler(const ReactorT *reactor, int fd_type, int event, uint32_t operation)
    -> decltype(reactor->default_write_handler) {
    int32_t selected = swr_v1_reactor_handler_select(operation, event, 1u << 31);
    // Rust rejects invalid/empty event selection before any fd-indexed read,
    // preserving the original isset/get access domain. READ has no fallback.
    if (selected == 0) return nullptr;
    if (selected == 1) return reactor->read_handler[fd_type];
    if (selected != 6) std::abort();
    decltype(reactor->default_write_handler) slots[] = {
        reactor->read_handler[fd_type], reactor->write_handler[fd_type], reactor->error_handler[fd_type],
        reactor->default_write_handler, reactor->default_error_handler
    };
    uint32_t present = (slots[0] != nullptr) | ((slots[1] != nullptr) << 1) | ((slots[2] != nullptr) << 2) |
                       ((slots[3] != nullptr) << 3) | ((slots[4] != nullptr) << 4);
    selected = swr_v1_reactor_handler_select(operation, event, present);
    if (selected == 0) return nullptr;
    if (selected < 1 || selected > 5) std::abort();
    return slots[selected - 1];
}
template<class ReactorT, class SocketT>
inline int swr_reactor_interest(const ReactorT *reactor, SocketT *socket, uint32_t operation, int bits = 0) {
    swr_v1_reactor_interest_action result{};
    if (swr_v1_reactor_interest(operation, socket->events, bits, &result) != 0) return -1;
    if (result.publish) socket->events = result.events;
    switch (result.action) {
    case 1: return reactor->set(socket, result.events);
    case 2: return reactor->add(socket, result.events);
    case 3: return reactor->del(socket);
    default: return 0;
    }
}
}
#endif
#endif
