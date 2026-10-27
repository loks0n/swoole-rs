/* SPDX-License-Identifier: Apache-2.0 */
#ifndef SWOOLE_RS_HOOKS_H
#define SWOOLE_RS_HOOKS_H
#include <stddef.h>
#include <stdint.h>
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <dirent.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <sys/types.h>
#include <sys/types.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef bool (*swr_v1_hook_offload)(void (*job)(void *), void *context);
FILE *swr_v1_hook_fopen(const char *pathname, const char *mode, swr_v1_hook_offload offload);
FILE *swr_v1_hook_fdopen(int fd, const char *mode, swr_v1_hook_offload offload);
FILE *swr_v1_hook_freopen(const char *pathname, const char *mode, FILE *stream, swr_v1_hook_offload offload);
size_t swr_v1_hook_fread(void *ptr, size_t size, size_t nmemb, FILE *stream, swr_v1_hook_offload offload);
size_t swr_v1_hook_fwrite(const void *ptr, size_t size, size_t nmemb, FILE *stream, swr_v1_hook_offload offload);
char *swr_v1_hook_fgets(char *s, int size, FILE *stream, swr_v1_hook_offload offload);
int swr_v1_hook_fputs(const char *s, FILE *stream, swr_v1_hook_offload offload);
int swr_v1_hook_feof(FILE *stream, swr_v1_hook_offload offload);
int swr_v1_hook_fflush(FILE *stream, swr_v1_hook_offload offload);
int swr_v1_hook_fclose(FILE *stream, swr_v1_hook_offload offload);
DIR *swr_v1_hook_opendir(const char *name, swr_v1_hook_offload offload);
struct dirent *swr_v1_hook_readdir(DIR *dirp, swr_v1_hook_offload offload);
int swr_v1_hook_closedir(DIR *dirp, swr_v1_hook_offload offload);
int swr_v1_hook_open(const char *pathname, int flags, mode_t mode, swr_v1_hook_offload offload);
int swr_v1_hook_fstat(int fd, struct stat *statbuf, swr_v1_hook_offload offload);
int swr_v1_hook_stat(const char *path, struct stat *statbuf, swr_v1_hook_offload offload);
int swr_v1_hook_lstat(const char *path, struct stat *statbuf, swr_v1_hook_offload offload);
int swr_v1_hook_unlink(const char *pathname, swr_v1_hook_offload offload);
int swr_v1_hook_mkdir(const char *pathname, mode_t mode, swr_v1_hook_offload offload);
int swr_v1_hook_rmdir(const char *pathname, swr_v1_hook_offload offload);
int swr_v1_hook_rename(const char *oldpath, const char *newpath, swr_v1_hook_offload offload);
int swr_v1_hook_fsync(int fd, swr_v1_hook_offload offload);
int swr_v1_hook_fdatasync(int fd, swr_v1_hook_offload offload);
int swr_v1_hook_ftruncate(int fd, off_t length, swr_v1_hook_offload offload);
off_t swr_v1_hook_lseek(int fd, off_t offset, int whence, swr_v1_hook_offload offload);
ssize_t swr_v1_hook_readlink(const char *pathname, char *buf, size_t len, swr_v1_hook_offload offload);
int swr_v1_hook_statvfs(const char *path, struct statvfs *buf, swr_v1_hook_offload offload);
int swr_v1_hook_access(const char *pathname, int mode, swr_v1_hook_offload offload);
bool swr_v1_hook_no_coro(bool reactor, bool coroutine);
int32_t swr_v1_hook_transition(uint32_t requested, uint32_t installed, uint32_t bit);
uint32_t swr_v1_hook_filter(uint32_t flags, uint32_t unavailable);
bool swr_v1_hook_file_result(bool open, int64_t result);
typedef struct { int32_t result; bool invalid; } swr_v1_hook_flock_outcome;
swr_v1_hook_flock_outcome swr_v1_hook_coroutine_flock(int32_t fd, int32_t operation, int (*coroutine_sleep)(double), double initial, double maximum);
/* A hooked stream socket name's host and port, as parse_ip_address_ex splits it.
 * Status 0 parsed; 1 bracketed IPv6 without "]:"; 2 no ':' before the last byte. */
typedef struct { int32_t status; size_t host_offset, host_length; int32_t port; } swr_v1_hooks_address_plan;
swr_v1_hooks_address_plan swr_v1_hooks_parse_address(const uint8_t *name, size_t length);
/* PHP's sleep family, whole: argument checks, duration and the sleep. Pass
 * coroutine_sleep (System::sleep) inside a coroutine, null outside one. Status 0
 * done; 1 argument `value` invalid; 2 interrupted, time left in seconds and
 * nanoseconds; 3 warn (nanosleep: then true; sleep_until: target passed, then false). */
typedef int32_t (*swr_v1_hooks_coroutine_sleep)(double seconds);
typedef struct { int32_t status; int64_t value, seconds, nanoseconds; } swr_v1_hooks_sleep_outcome;
swr_v1_hooks_sleep_outcome swr_v1_hooks_sleep(int64_t seconds, swr_v1_hooks_coroutine_sleep coroutine_sleep);
swr_v1_hooks_sleep_outcome swr_v1_hooks_usleep(int64_t microseconds, swr_v1_hooks_coroutine_sleep coroutine_sleep);
swr_v1_hooks_sleep_outcome swr_v1_hooks_nanosleep(int64_t seconds, int64_t nanoseconds, swr_v1_hooks_coroutine_sleep coroutine_sleep);
swr_v1_hooks_sleep_outcome swr_v1_hooks_sleep_until(double timestamp, double top, swr_v1_hooks_coroutine_sleep coroutine_sleep);
double swr_v1_hook_backoff(double current, double initial, double maximum);
int64_t swr_v1_hook_transfer_result(int64_t result, uint64_t total);
typedef struct { uint64_t total; bool again; } swr_v1_hook_transfer_plan;
swr_v1_hook_transfer_plan swr_v1_hook_transfer(int64_t result, uint64_t total, uint64_t requested, bool wait);
int32_t swr_v1_hook_submit(int32_t result, bool again, bool busy, bool interrupted);
typedef struct { int64_t result; int32_t error; } swr_v1_hook_completion_plan;
swr_v1_hook_completion_plan swr_v1_hook_completion(int64_t result, int32_t canceled, int32_t timeout);
uint32_t swr_v1_hook_poll_revents(uint32_t requested, uint32_t received, uint32_t event, uint32_t read_write, uint32_t error);
enum swr_hook_timer_action { SWR_HOOK_TIMER_ENABLE = 1, SWR_HOOK_TIMER_ADD = 2, SWR_HOOK_TIMER_SENTINEL = 4, SWR_HOOK_TIMER_DELETE = 8, SWR_HOOK_TIMER_CLEAR = 16 };
uint32_t swr_v1_hook_timer(uint32_t operation, bool enabled, bool present, bool sentinel, double timeout);
enum swr_hook_wait_action { SWR_HOOK_WAIT_DONE = 0, SWR_HOOK_WAIT_CALLBACK = 1, SWR_HOOK_WAIT_SLEEP = 2, SWR_HOOK_WAIT_CANCELED = -1, SWR_HOOK_WAIT_INVALID = -2 };
typedef struct { double delay; uint32_t phase; int32_t action; } swr_v1_hook_wait_plan;
swr_v1_hook_wait_plan swr_v1_hook_wait_for(uint32_t phase, double delay, bool result, double initial, double maximum);
typedef struct { uint32_t revents; bool wake; } swr_v1_hook_event_plan;
swr_v1_hook_event_plan swr_v1_hook_event_waiter(uint32_t received, uint32_t event);
typedef struct { int32_t result; int32_t last_error; int32_t error; } swr_v1_hook_wait_event_outcome;
swr_v1_hook_wait_event_outcome swr_v1_hook_wait_event(int32_t fd, int32_t events, double timeout, int (*wait)(int fd, int events, double timeout, int *revents));
typedef struct {
    void *(*current)(void);
    bool (*busy)(void);
    void (*listen)(int signo, bool on);
    void (*waiting)(bool on);
    bool (*yield_for)(void *co, double timeout);
    void (*resume)(void *co);
} swr_v1_hook_signal_ops;
typedef struct { int32_t signo; int32_t last_error; } swr_v1_hook_signalled;
void swr_v1_hook_signal_wake(int signo);
swr_v1_hook_signalled swr_v1_hook_wait_signal(const int32_t *signals, size_t count, double timeout, const swr_v1_hook_signal_ops *ops);
enum swr_hook_retry_action { SWR_HOOK_RETRY_DONE = 0, SWR_HOOK_RETRY_IO = 1, SWR_HOOK_RETRY_CLASSIFY = 2, SWR_HOOK_RETRY_TIMER = 3, SWR_HOOK_RETRY_WAIT = 4 };
typedef struct { uint32_t phase; int32_t action; } swr_v1_hook_retry_plan;
swr_v1_hook_retry_plan swr_v1_hook_retry(uint32_t phase, int64_t result, bool success);
swr_v1_hook_retry_plan swr_v1_hook_retry_interrupt(uint32_t phase, int64_t result, bool success, bool interrupted);
uint32_t swr_v1_hook_bound(uint32_t event, uint32_t read, uint32_t write, bool read_bound, bool write_bound);
uint32_t swr_v1_hook_socket_status(bool closed, bool close_wait);
uint32_t swr_v1_hook_check_result(int64_t result, bool has_error);
uint32_t swr_v1_hook_event_name(uint32_t event, uint32_t read, uint32_t write, bool read_bound, bool write_bound);
double swr_v1_hook_timeval(double seconds, double micros);
uint32_t swr_v1_hook_timeout_action(double timeout, double startup);
typedef struct { double remaining; bool expired; } swr_v1_hook_timeout_plan;
swr_v1_hook_timeout_plan swr_v1_hook_timeout_remaining(double timeout, double elapsed, double minimum);
typedef struct { uint32_t flags; bool conflict; } swr_v1_hook_curl_plan;
swr_v1_hook_curl_plan swr_v1_hook_curl_flags(uint32_t flags, uint32_t native_flag, uint32_t php_flag);
enum swr_hook_async_action { SWR_HOOK_ASYNC_REJECT = 0, SWR_HOOK_ASYNC_YIELD = 1, SWR_HOOK_ASYNC_COMPLETE = 2, SWR_HOOK_ASYNC_CANCEL = 3, SWR_HOOK_ASYNC_RESUME = 4 };
int32_t swr_v1_hook_async_action(uint32_t phase, bool cancellable, bool success);
int32_t swr_v1_hook_dns_error(int32_t error, int32_t asynchronous_timeout, int32_t resolve_timeout);
double swr_v1_hook_sleep_timeout(double seconds, double minimum);
/* Socket::recv_packet after its availability check, read timer and get_read_buffer.
   buffer is the read buffer: swoole::String's leading fields. fail: 0 no package
   length, 1 too large (warning naming the length), 2 no EOF within the maximum. */
typedef struct { size_t length, size; int64_t offset; char *str; } swr_v1_hook_read_buffer;
typedef struct {
    void *context;
    swr_v1_hook_read_buffer *buffer;
    bool length_check, eof_check;
    const char *eof;
    uint8_t eof_len;
    char length_type;
    uint8_t length_size;
    uint16_t length_offset;
    uint32_t max_length;
    ssize_t (*recv)(void *, char *, size_t);
    ssize_t (*recv_all)(void *, char *, size_t);
    ssize_t (*package_length)(void *, const char *, uint32_t, uint32_t *header_len);
    void (*extend)(void *, size_t);
    void (*reduce)(void *, int64_t);
    void (*fail)(void *, uint32_t kind, ssize_t length);
    bool (*timed_out)(void *);
} swr_v1_hook_packet_ops;
ssize_t swr_v1_hook_recv_packet(const swr_v1_hook_packet_ops *ops);
/* Socket::readv_all/writev_all after the availability check and the timer's creation.
   wait installs barrier (called with barrier_state) and runs timer.start() && wait_event. */
typedef bool (*swr_v1_hook_barrier)(void *barrier_state);
typedef struct {
    void *context;
    ssize_t (*transfer)(void *, bool first);
    bool (*would_block)(void *);
    size_t (*remaining)(void *);
    void (*fail)(void *);
    bool (*wait)(void *, swr_v1_hook_barrier barrier, void *barrier_state);
    void (*check)(void *, ssize_t);
} swr_v1_hook_vector_ops;
ssize_t swr_v1_hook_vector_all(const swr_v1_hook_vector_ops *ops);
/* The coroutine Socket's connection state, Rust-owned behind an opaque handle (#439). */
typedef struct swr_v1_hook_socket_state swr_v1_hook_socket_state;
typedef struct { bool connected, read, write; } swr_v1_hook_socket_flags_t;
swr_v1_hook_socket_state *swr_v1_hook_socket_state_new(void);
void swr_v1_hook_socket_state_free(swr_v1_hook_socket_state *state);
swr_v1_hook_socket_flags_t swr_v1_hook_socket_flags(const swr_v1_hook_socket_state *state);
void swr_v1_hook_socket_set_flags(swr_v1_hook_socket_state *state, swr_v1_hook_socket_flags_t flags);
void swr_v1_hook_socket_connect(swr_v1_hook_socket_state *state);
/* Socket::cancel/close. release marks the descriptor closed and runs the destructor
   callback once; the socket may be gone afterwards. resume wakes the coroutine bound
   to the event (read or write). */
typedef struct {
    void *context;
    swr_v1_hook_socket_state *state;
    uint32_t read, write;
    int32_t close_wait_error;
    bool (*closed)(void *);
    void (*shutdown)(void *);
    bool (*bound)(void *, uint32_t event);
    void (*set_err)(void *, int32_t);
    void (*resume)(void *, uint32_t event);
    void (*close_wait)(void *);
    void (*release)(void *);
} swr_v1_hook_socket_ops;
bool swr_v1_hook_cancel(const swr_v1_hook_socket_ops *ops, uint32_t event);
bool swr_v1_hook_close(const swr_v1_hook_socket_ops *ops);
/* Socket::shutdown(how) after set_err(0): 0, or the error to set. closed is is_closed();
   ssl_shutdown (null without TLS) closes the session first, with context; syscall is shutdown(2). */
int32_t swr_v1_hook_shutdown(int (*syscall)(int, int), int32_t fd, int32_t how, bool closed, swr_v1_hook_socket_state *state,
                             void (*ssl_shutdown)(void *), void *context);
int32_t swr_v1_hook_connect_action(int32_t result, bool interrupted, bool in_progress);
bool swr_v1_hook_connect_option(int32_t result, int32_t error);
int32_t swr_v1_hook_liveness_error(bool alive, int32_t error, int32_t reset);
#ifdef __cplusplus
}
// Callables stay on the native stack. Rust returns before every IO, errno
// classifier, timer operation or coroutine suspension; exceptions remain native.
template <class IO, class Classify, class Start, class Wait>
static inline int64_t swr_hook_retry(IO io, Classify classify, Start start, Wait wait, int interrupt_errno = 0) {
    int64_t result = io();
    uint32_t phase = 1;
    bool success = false;
    for (;;) {
        auto plan = swr_v1_hook_retry_interrupt(phase, result, success,
            interrupt_errno != 0 && phase == 1 && result < 0 && errno == interrupt_errno);
        phase = plan.phase;
        switch (plan.action) {
        case SWR_HOOK_RETRY_IO: result = io(); break;
        case SWR_HOOK_RETRY_CLASSIFY: success = classify(); break;
        case SWR_HOOK_RETRY_TIMER: success = start(); break;
        case SWR_HOOK_RETRY_WAIT: success = wait(); break;
        default: return result;
        }
    }
}
static_assert(sizeof(swr_v1_hook_curl_plan) == 8, "curl plan ABI");
static_assert(sizeof(swr_v1_hook_timeout_plan) == 16, "timeout plan ABI");
static_assert(sizeof(swr_v1_hook_retry_plan) == 8, "retry cursor ABI");
static_assert(sizeof(swr_v1_hook_wait_plan) == 16, "wait cursor ABI");
static_assert(sizeof(swr_v1_hook_event_plan) == 8, "event waiter ABI");
static_assert(sizeof(swr_v1_hook_transfer_plan) == 16, "transfer ABI");
static_assert(sizeof(swr_v1_hook_completion_plan) == 16, "completion ABI");
#endif
#endif
