#include "swoole_rs_coroutine.h"
#include <assert.h>
#include <stddef.h>
#ifdef __cplusplus
#define ABI_ASSERT static_assert
#else
#define ABI_ASSERT _Static_assert
#endif
ABI_ASSERT(offsetof(swr_v1_coroutine_registry_entry,cid)==0,"ID offset");
ABI_ASSERT(offsetof(swr_v1_coroutine_registry_entry,token)==sizeof(long),"token offset");
ABI_ASSERT(offsetof(swr_v1_coroutine_registry_entry,next)==sizeof(long)+sizeof(uintptr_t),"cursor offset");
int main(void) {
    void *owner=NULL;
    assert(swr_v1_coroutine_registry_count(owner)==0);
    assert(swr_v1_coroutine_registry_first(owner)==NULL);
    assert(swr_v1_coroutine_registry_insert(&owner,7,13)==0);
    const void *entry=swr_v1_coroutine_registry_find(owner,7);
    swr_v1_coroutine_registry_entry value=swr_v1_coroutine_registry_item(entry);
    assert(value.cid==7&&value.token==13&&value.next==NULL);
    assert(swr_v1_coroutine_registry_first(owner)==entry);
    assert(swr_v1_coroutine_registry_insert(&owner,8,0)==0);
    assert(swr_v1_coroutine_registry_count(owner)==2);
    assert(swr_v1_coroutine_registry_item(swr_v1_coroutine_registry_first(owner)).next==entry);
    swr_v1_coroutine_registry_remove(owner,7);
    assert(swr_v1_coroutine_registry_find(owner,7)==NULL);
    swr_v1_coroutine_registry_drop(&owner);
    assert(owner==NULL);
    swr_v1_coroutine_registry_drop(&owner);
    return 0;
}
