/* SPDX-License-Identifier: Apache-2.0 */
#ifndef SWOOLE_RS_OSSUPPORT_H
#define SWOOLE_RS_OSSUPPORT_H
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <sys/types.h>
#ifdef __cplusplus
extern "C" {
#endif
/* The process-wide async thread pool. Event tokens are native AsyncEvent
 * pointers: native runs, sends and frees them through the hooks. */
typedef struct swr_v1_os_pool swr_v1_os_pool;
typedef struct {
    void (*thread_init)(void);
    void (*thread_clean)(void);
    void (*execute)(uintptr_t event);
    void (*retire)(uintptr_t key);
    void (*spawn_failed)(void);
} swr_v1_os_pool_hooks;
const swr_v1_os_pool *swr_v1_os_pool_acquire(swr_v1_os_pool_hooks hooks, size_t cpu, size_t core,
                                             size_t workers, double wait, double idle);
void swr_v1_os_pool_release(const swr_v1_os_pool *pool);
size_t swr_v1_os_pool_task_id(const swr_v1_os_pool *pool);
void swr_v1_os_pool_dispatch(const swr_v1_os_pool *pool, uintptr_t event);
bool swr_v1_os_pool_join(const swr_v1_os_pool *pool, uintptr_t key);
size_t swr_v1_os_pool_worker_num(const swr_v1_os_pool *pool);
size_t swr_v1_os_pool_queue_size(const swr_v1_os_pool *pool);
void swr_v1_os_pool_notify_one(const swr_v1_os_pool *pool);
/* File IO. Each call returns right after a failing syscall, errno intact, so
 * native logs the upstream warning. */
typedef struct { size_t done; bool failed; } swr_v1_os_file_io;
swr_v1_os_file_io swr_v1_os_file_write_all(int fd, bool append, const void *data, size_t length);
swr_v1_os_file_io swr_v1_os_file_read_all(int fd, void *buf, size_t length);
ssize_t swr_v1_os_file_read_line(int fd, void *buf, size_t n);
/* size, or -1 with the error to publish (errno or EISDIR). */
typedef struct { int64_t size; int error; } swr_v1_os_file_size_t;
swr_v1_os_file_size_t swr_v1_os_file_size(int fd);
/* warn: copy fallback 1 pread, 2 write; kqueue sendfile 1 sendfile. */
typedef struct { ssize_t result; uint32_t warn; } swr_v1_os_sendfile_t;
swr_v1_os_sendfile_t swr_v1_os_sendfile_copy(int out_fd, int in_fd, off_t *offset, size_t size);
#if defined(__APPLE__) || defined(__FreeBSD__)
swr_v1_os_sendfile_t swr_v1_os_sendfile(int out_fd, int in_fd, off_t *offset, size_t size);
#endif
size_t swr_v1_os_random_bytes(void *buf, size_t size);
int32_t swr_v1_os_permissions(int32_t perms);
int32_t swr_v1_os_queue_flags(int32_t flags, bool blocking, int32_t nowait);
int32_t swr_v1_os_queue_error(bool interrupted, bool again);
#ifdef __cplusplus
}
static_assert(sizeof(uintptr_t) == sizeof(void *), "opaque token width");
#endif
#endif
