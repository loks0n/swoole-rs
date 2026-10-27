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
typedef struct { uint32_t status; int32_t error; } swr_v1_process_affinity_outcome;
swr_v1_process_affinity_outcome swr_v1_process_worker_affinity(uint32_t worker_id, const int32_t *available, int32_t available_len, bool thread);
typedef struct { uint32_t status; int32_t error; int32_t fd; size_t read; } swr_v1_process_task_file_read_result;
swr_v1_process_task_file_read_result swr_v1_process_task_file_read(const char *path, uint8_t *buffer, size_t length, bool peek);
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
#ifdef __cplusplus
}
#endif
#endif
