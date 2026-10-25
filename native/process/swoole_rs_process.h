#ifndef SWOOLE_RS_PROCESS_H
#define SWOOLE_RS_PROCESS_H
#include <stdint.h>
#include <stdbool.h>
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
#ifdef __cplusplus
}
#endif
#endif
