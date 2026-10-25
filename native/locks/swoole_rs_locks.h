#ifndef SWOOLE_RS_LOCKS_H
#define SWOOLE_RS_LOCKS_H
#ifndef SWOOLE_RS_LOCKS
#error "Locks overlay requires --enable-swoole-rs-locks"
#endif
#if defined(__APPLE__)
#include <TargetConditionals.h>
#if !TARGET_OS_OSX
#error "Rust locks require validated macOS or Linux platform contracts"
#endif
#elif !defined(__linux__) || defined(__ANDROID__)
#error "Rust locks require validated macOS or Linux platform contracts"
#endif
#include <stdint.h>
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
/* kind is pinned Lock::Type: RW=1, mutex=3, spin=5. Caller supplies size/alignment. */
size_t swr_v1_locks_size(int32_t kind);
size_t swr_v1_locks_align(int32_t kind);
int32_t swr_v1_locks_init(void *, int32_t kind, int32_t shared);
int32_t swr_v1_locks_lock(void *, int32_t kind, int32_t operation, int32_t timeout_msec, uint32_t capabilities);
int32_t swr_v1_locks_unlock(void *, int32_t kind);
void swr_v1_locks_destroy(void *, int32_t kind);
/* operation: load=0, store=1, add-fetch=2, sub-fetch=3, CAS=4. */
uint32_t swr_v1_locks_atomic32(uint32_t *, uint32_t operation, uint32_t value, uint32_t expected);
int64_t swr_v1_locks_atomic64(int64_t *, uint32_t operation, int64_t value, int64_t expected);
void swr_v1_locks_barrier_init(uint32_t *count, uint32_t *arrived, uint32_t parties);
void swr_v1_locks_barrier_wait(uint32_t *count, uint32_t *arrived);
int32_t swr_v1_locks_pthread_barrier(void *, size_t, void *, size_t, uint32_t operation, int32_t shared, uint32_t parties);
/* Futex wait/wake (Linux only); non-futex builds use upstream's C++ registry. */
int32_t swr_v1_locks_wait(uint32_t *, double timeout);
int32_t swr_v1_locks_wakeup(uint32_t *, int32_t count);
int32_t swr_v1_locks_coroutine_try(uint32_t *, uintptr_t held_cookie, int64_t held_cid, uintptr_t current_cookie, int64_t current_cid, uint8_t blocking);
int32_t swr_v1_locks_coroutine_release(uint32_t *);
double swr_v1_locks_coroutine_backoff(double second, double initial, double maximum);
#ifdef __cplusplus
}
#endif
#endif

