#ifndef SWOOLE_RS_PROCESS_H
#define SWOOLE_RS_PROCESS_H
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct { uint32_t action; bool callback_called; } swr_v1_process_exit_observation;
typedef struct { bool timed_out; bool update_timeout; int32_t timeout_msec; } swr_v1_process_exit_budget_result;
swr_v1_process_exit_observation swr_v1_process_worker_exit(bool can_exit, bool callback_present, bool callback_called);
swr_v1_process_exit_budget_result swr_v1_process_exit_budget(int32_t remaining, int32_t timeout_msec);
bool swr_v1_process_discard_data(bool present, bool closed, bool disable_notify, bool discard_timeout);
uint32_t swr_v1_process_task_action(bool pipe, bool shutdown, bool command);
uint32_t swr_v1_process_finish_error(bool pipe, bool no_reply);
int32_t swr_v1_process_result_flags(int32_t flags, bool callback, bool coroutine, int32_t callback_flag, int32_t coroutine_flag);
uint32_t swr_v1_process_reload_action(bool all, bool task);
uint32_t swr_v1_process_reload_kill(bool failed, bool no_child, bool no_process);
/* Manager::signal_handler action: 0 none, 1 stop, 2 reload all, 3 reload workers,
 * 4 read message, 5 force-kill if armed, 6 reopen logger. */
uint32_t swr_v1_process_manager_signal_action(int signo);
/* Server::worker_signal_handler action: 0 none, 1 terminate, 2 reopen logger. */
uint32_t swr_v1_process_worker_signal_action(int signo);
typedef struct { uint32_t status; int32_t error; } swr_v1_process_affinity_outcome;
swr_v1_process_affinity_outcome swr_v1_process_worker_affinity(uint32_t worker_id, const int32_t *available, int32_t available_len, bool thread);
typedef struct { uint32_t status; int32_t error; int32_t fd; size_t read; } swr_v1_process_task_file_read_result;
swr_v1_process_task_file_read_result swr_v1_process_task_file_read(const char *path, uint8_t *buffer, size_t length, bool peek);
/* Pack a task payload into EventData::data: inline when it fits in dest_cap, else a
 * temp file (from `template`, an mkstemp pattern) whose path+length land in dest as
 * a PacketTask. Native builds the header and sets info.len/flag from this. */
typedef struct { bool ok, tmpfile; size_t info_len; } swr_v1_process_task_pack_result;
swr_v1_process_task_pack_result swr_v1_process_task_pack(uint8_t *dest, size_t dest_cap, const uint8_t *data, size_t len, const char *template_);
/* Laid out as swoole::Signal. */
typedef struct { uintptr_t handler; uint16_t signo; bool activated; } swr_v1_signal_slot;
extern swr_v1_signal_slot swr_v1_signals[128];
typedef struct { uint32_t status; uintptr_t handler; } swr_v1_signal_lookup_result;
uintptr_t swr_v1_signal_set_action(int signo, uintptr_t func, bool restart, bool mask);
uintptr_t swr_v1_signal_set(int signo, uintptr_t handler, bool safety, void (*callback)(int), bool (*has_reactor)(void));
void swr_v1_signal_dispatch(void (*callback)(int));
swr_v1_signal_lookup_result swr_v1_signal_lookup(int signo);
bool swr_v1_signal_isset(int signo);
void swr_v1_signal_reset(void);
void swr_v1_signal_clear(void);
void swr_v1_signal_mask_all(bool block, bool *blocking_all);
typedef struct {
    void *(*current)(void);
    void (*signal_init)(void);
    void (*yield_for)(void *co, double timeout);
    void (*resume)(void *co);
    bool (*timed_out)(void *co);
} swr_v1_wait_coroutines;
typedef struct { int pid; bool timed_out; } swr_v1_waited;
swr_v1_waited swr_v1_wait_pid(int pid, int *status, int options, double timeout, const swr_v1_wait_coroutines *ops);
void swr_v1_wait_reap(int signo, void (*resume)(void *co));
size_t swr_v1_wait_count(void);
#ifdef __linux__
typedef struct { uint32_t status; int fd; int32_t error; } swr_v1_signalfd_created;
typedef struct { uint32_t status; uint32_t signo; uintptr_t handler; int32_t error; } swr_v1_signalfd_received;
void swr_v1_signalfd_init(void);
int swr_v1_signalfd_fd(void);
bool swr_v1_signalfd_owned(void);
uintptr_t swr_v1_signalfd_set(int signo, uintptr_t handler);
swr_v1_signalfd_created swr_v1_signalfd_create(void);
void swr_v1_signalfd_close(void);
bool swr_v1_signalfd_clear(void);
swr_v1_signalfd_received swr_v1_signalfd_receive(int fd);
#endif
/* Rust-owned worker lookup: pid -> native Worker* and category. Replaces
 * Server::get_worker_by_pid's event-worker scan and user-map branch and the
 * kill_event_workers / kill_user_workers loops. The handle lives on Server; native
 * registers a worker at spawn, unregisters at reap/detach. Task workers live in the
 * task pool, not here. */
#define SWR_WORKER_EVENT 1
#define SWR_WORKER_USER 2
typedef struct swr_v1_process_worker_registry swr_v1_process_worker_registry;
swr_v1_process_worker_registry *swr_v1_process_worker_registry_new(void);
void swr_v1_process_worker_registry_free(swr_v1_process_worker_registry *);
void swr_v1_process_worker_registry_register(swr_v1_process_worker_registry *, int pid, void *worker, int category);
bool swr_v1_process_worker_registry_unregister(swr_v1_process_worker_registry *, int pid);
void *swr_v1_process_worker_registry_lookup(const swr_v1_process_worker_registry *, int pid);
/* Send signo to every worker of category, then wait for each. kill_fn/wait_fn are
 * swoole_kill / swoole_waitpid; warn_fn reports a wait failure. */
void swr_v1_process_worker_registry_terminate(const swr_v1_process_worker_registry *, int category, int signo,
                                              int (*kill_fn)(int pid, int signo),
                                              int (*wait_fn)(int pid, int *status, int options),
                                              void (*warn_fn)(int pid));
/* Byte-exact mirror of swoole::Worker (include/swoole_process_pool.h), whose layout
 * Rust owns (crates/process/src/worker_record.rs). A static_assert in the process
 * patch locks sizeof/offsetof of swoole::Worker to this mirror, so a layout drift
 * fails the build rather than corrupting shared memory. The scalar process fields
 * (pid/status/type/id) migrate behind the accessors; pointer/atomic fields stay
 * C++-owned storage. See #629. */
typedef struct swr_v1_worker_record {
    int pid;
    uint32_t id;
    void *pool;
    void *queue;
    bool shared;
    bool redirect_stdout;
    bool redirect_stdin;
    bool redirect_stderr;
    uint8_t status;
    uint8_t kind;
    uint8_t msgqueue_mode;
    uint8_t child_process;
    uint32_t concurrency;
    int64_t start_time;
    int64_t dispatch_count;
    int64_t request_count;
    int64_t response_count;
    size_t coroutine_num;
    void *lock;
    void *pipe_object;
    void *pipe_master;
    void *pipe_worker;
    void *pipe_current;
    void *ptr;
} swr_v1_worker_record;
uint8_t swr_v1_worker_status(const swr_v1_worker_record *);
void swr_v1_worker_set_status(swr_v1_worker_record *, uint8_t status);
uint8_t swr_v1_worker_type(const swr_v1_worker_record *);
void swr_v1_worker_set_type(swr_v1_worker_record *, uint8_t kind);
int swr_v1_worker_pid(const swr_v1_worker_record *);
void swr_v1_worker_set_pid(swr_v1_worker_record *, int pid);
uint32_t swr_v1_worker_id(const swr_v1_worker_record *);
void swr_v1_worker_set_id(swr_v1_worker_record *, uint32_t id);
#ifdef __cplusplus
}
#endif
#endif
