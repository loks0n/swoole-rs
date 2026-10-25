/* SPDX-License-Identifier: Apache-2.0 */
#ifndef SWOOLE_RS_TIMER_RUNTIME_H
#define SWOOLE_RS_TIMER_RUNTIME_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Stateless LP64 clock/backend facade; no callback, allocation or errno change.
 * Native code retains clock acquisition, syscalls, signals and public layouts.
 * Original defined signed-arithmetic/conversion ranges remain the parity scope. */
typedef struct { int64_t seconds, fraction; } swr_timer_native_time;
/* manual=0, reactor=1, system=2; inputs are copied native booleans. */
uint32_t swr_v1_timer_backend(uint32_t manual, uint32_t reactor);
/* timeval microseconds; zero/negative disarm. */
swr_timer_native_time swr_v1_timer_system_interval(int64_t milliseconds);
/* timespec nanoseconds, truncation toward zero. */
swr_timer_native_time swr_v1_timer_realtime_split(int64_t nanoseconds);
/* Positive carry only, narrowed through native int before its int product;
 * do not normalize a negative result fraction upward. Signed native overflow
 * remains outside the parity scope. */
swr_timer_native_time swr_v1_timer_realtime_add(int64_t seconds, int64_t nanoseconds, int64_t milliseconds);
int64_t swr_v1_timer_relative_msec(int64_t absolute, int64_t base);
int64_t swr_v1_timer_rearm_after_add(int64_t current, int64_t delay);
/* Valid independent deadline output; 1 writes result, 0 leaves output unchanged. */
int32_t swr_v1_timer_delay_deadline(int64_t now, int64_t previous, int64_t delay, int64_t *deadline);
#ifdef __cplusplus
}
#endif
#endif
