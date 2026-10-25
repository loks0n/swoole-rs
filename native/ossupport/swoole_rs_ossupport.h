/* SPDX-License-Identifier: Apache-2.0 */
#ifndef SWOOLE_RS_OSSUPPORT_H
#define SWOOLE_RS_OSSUPPORT_H
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct { size_t core; size_t workers; double wait; double idle; } swr_v1_os_pool_config_t;
swr_v1_os_pool_config_t swr_v1_os_pool_config(size_t cpu, size_t core, size_t workers, double wait, double idle);
size_t swr_v1_os_pool_expand(size_t waiting, size_t threads, size_t workers, double threshold, double age);
int32_t swr_v1_os_event_action(bool handler, bool canceled);
int32_t swr_v1_os_worker_action(bool event, bool handler, bool canceled, bool timeout, size_t closing);
int32_t swr_v1_os_fs_error(int64_t result, bool retry);
int32_t swr_v1_os_content(uint64_t length, uint64_t maximum);
/* Native initial String allocation precedes first call. Exclusive zeroed state.
 * 1 native read, 2 native grow(last positive result) THEN fresh native read,
 * 0 return accumulated String, UINT32_MAX invalid. No pointers retained. */
typedef struct { uint32_t phase; } swr_v1_os_read_content_state;
uint32_t swr_v1_os_read_content_next(swr_v1_os_read_content_state *state, int64_t result);
/* Exclusive zeroed synchronous stack state, no native pointer retained.
 * 0 null, 1 native stat, 2 lazy native maximum observation, 3 open warning/null,
 * 4 empty log/null, 5 large log/null, 6 native allocation/read/finalize/return.
 * Supply ready initially, signed size after 1, maximum after 2. UINT32_MAX invalid. */
typedef struct { uint32_t phase; int64_t size; } swr_v1_os_file_content_state;
uint32_t swr_v1_os_file_content_next(swr_v1_os_file_content_state *state,
                                   bool ready, int64_t size, uint64_t maximum);
/* Zeroed exclusive stack cursor; native performs IO/warning after Rust returns.
 * Keep length fixed; action 1 supplies result/retry to the next call.
 * 0 return completed, 1 native IO, 2 native warning then return, UINT32_MAX invalid. */
typedef struct { size_t completed; uint32_t phase; } swr_v1_os_file_io_state;
uint32_t swr_v1_os_file_io_next(swr_v1_os_file_io_state *state, size_t length,
                              int64_t result, bool retry);
/* 0 = return size, 1 = preserve errno, 2 = publish EISDIR. */
int32_t swr_v1_os_file_size_action(bool fstat_succeeded, uint64_t mode, uint64_t type_mask, uint64_t regular_type);
/* Nonpositive read result: action 0 returns length without reading data.
 * Positive initialized prefix <= PTRDIFF_MAX: action 1 writes buf[length]=0,
 * then seeks to original_offset + length + extra, in that order, after return.
 * extra is 1 only for no terminator. No pointer or borrow is retained. */
typedef struct { int64_t length; uint32_t action; uint32_t extra; } swr_v1_os_file_line_result_t;
swr_v1_os_file_line_result_t swr_v1_os_file_line_result(const unsigned char *data, int64_t read_result);
size_t swr_v1_os_line_end(const unsigned char *data, size_t length);
int32_t swr_v1_os_permissions(int32_t perms);
int32_t swr_v1_os_queue_flags(int32_t flags, bool blocking, int32_t nowait);
int32_t swr_v1_os_queue_error(bool interrupted, bool again);
bool swr_v1_os_random_error(int64_t result, bool interrupted, bool again);
/* Zeroed exclusive stack cursor; fixed size, native result/transient flag.
 * 0 return completed, 1 native getrandom, UINT32_MAX invalid. Zero repeats. */
typedef struct { size_t completed; uint32_t phase; } swr_v1_os_random_bytes_state;
uint32_t swr_v1_os_random_bytes_next(swr_v1_os_random_bytes_state *state,
                                  size_t size, int64_t result, bool retry);
int32_t swr_v1_os_sendfile_action(int64_t result, bool interrupted);
/* Exclusive zeroed stack cursor; size/capacity fixed; no native pointers retained. */
typedef struct { size_t amount; int64_t result; uint32_t phase; } swr_v1_os_sendfile_fallback_state;
enum swr_v1_os_sendfile_fallback_action {
    SWR_OS_FALLBACK_DONE = 0, SWR_OS_FALLBACK_READ = 1, SWR_OS_FALLBACK_WRITE = 2,
    SWR_OS_FALLBACK_WARN_READ = 3, SWR_OS_FALLBACK_WARN_WRITE = 4, SWR_OS_FALLBACK_ADVANCE = 5
};
uint32_t swr_v1_os_sendfile_fallback_next(swr_v1_os_sendfile_fallback_state *state,
                                       size_t size, size_t capacity, int64_t observed);
typedef struct swr_v1_os_queue swr_v1_os_queue;
typedef struct { uintptr_t token; bool present; } swr_v1_os_queue_item;
swr_v1_os_queue *swr_v1_os_queue_create(void);
void swr_v1_os_queue_destroy(swr_v1_os_queue *queue);
bool swr_v1_os_queue_push(swr_v1_os_queue *queue, uintptr_t token);
swr_v1_os_queue_item swr_v1_os_queue_pop(swr_v1_os_queue *queue);
swr_v1_os_queue_item swr_v1_os_queue_front(const swr_v1_os_queue *queue);
size_t swr_v1_os_queue_count(const swr_v1_os_queue *queue);
#ifdef __cplusplus
}
static_assert(sizeof(uintptr_t) == sizeof(void *), "opaque token width");
#endif
#endif
