#ifndef SWOOLE_RS_COROUTINE_REGISTRY_POLICY_H
#define SWOOLE_RS_COROUTINE_REGISTRY_POLICY_H
#include "swoole_rs_coroutine.h"
/* Additive module-local capsule. 1/210106/1: Apple libc++; 2/120200/1:
 * captured GCC12.2 GNU source candidate, not installed-image qualification. */
typedef struct swr_v1_coroutine_registry_policy { uint32_t family, version, abi; } swr_v1_coroutine_registry_policy;
#ifdef __cplusplus
extern "C" {
#endif
void swr_v1_coroutine_registry_clear(void *);
int32_t swr_v1_coroutine_registry_selected_insert(void **, long, uintptr_t, swr_v1_coroutine_registry_policy);
swr_v1_coroutine_creation_action swr_v1_coroutine_selected_create_step(
    swr_v1_coroutine_creation_cursor *, swr_v1_coroutine_scheduler *, swr_v1_coroutine_cid *, void **,
    uintptr_t, size_t, swr_v1_coroutine_registry_policy);
#ifdef __cplusplus
}
#endif
#endif
