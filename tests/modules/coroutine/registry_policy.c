/* Explicit Native policy custody, inert finite initialized records only. */
#include "swoole_rs_coroutine_registry_policy.h"
#include <assert.h>
#include <stddef.h>
#ifdef SWR_CHANNEL_FFI
extern uint32_t swr_v1_abi_version(void);
extern uint64_t swr_v1_feature_bits(void);
#endif
int main(void) {
#ifdef SWR_CHANNEL_FFI
    assert(swr_v1_abi_version()==1);
    assert(swr_v1_feature_bits()&(UINT64_C(1)<<15));
#endif
    _Static_assert(sizeof(swr_v1_coroutine_registry_policy)==12,"policy capsule size");
    _Static_assert(offsetof(swr_v1_coroutine_registry_policy,abi)==8,"policy capsule ABI offset");
    const swr_v1_coroutine_registry_policy policies[]={{1,210106,1},{2,120200,1}};
    const swr_v1_coroutine_registry_policy unknown={0,0,0};
    for(size_t p=0;p<2;++p) {
        void *owner=NULL;
        assert(swr_v1_coroutine_registry_selected_insert(&owner,7,0,unknown)==-4);
        assert(owner==NULL);
        assert(swr_v1_coroutine_registry_selected_insert(&owner,7,11,policies[p])==0);
        const void *identity=swr_v1_coroutine_registry_find(owner,7);
        assert(identity && swr_v1_coroutine_registry_lookup(owner,7)==11);
        assert(swr_v1_coroutine_registry_selected_insert(&owner,7,99,policies[1-p])==-4);
        assert(swr_v1_coroutine_registry_selected_insert(&owner,8,99,unknown)==-4);
        assert(swr_v1_coroutine_registry_count(owner)==1);
        assert(swr_v1_coroutine_registry_lookup(owner,7)==11);
        /* Frozen API on an existing owner honors its captured policy. */
        assert(swr_v1_coroutine_registry_insert(&owner,7,12)==0);
        assert(swr_v1_coroutine_registry_find(owner,7)==identity);
        assert(swr_v1_coroutine_registry_lookup(owner,7)==12);
        swr_v1_coroutine_registry_clear(owner);
        assert(swr_v1_coroutine_registry_selected_insert(&owner,8,0,policies[p])==0);
        swr_v1_coroutine_registry_drop(&owner);
        assert(owner==NULL);
        /* New selected creation: raw CID publication precedes registration. */
        swr_v1_coroutine_scheduler scheduler={65536,0,0,0,0};
        swr_v1_coroutine_creation_cursor cursor={0};
        swr_v1_coroutine_cid cid;
        swr_v1_coroutine_creation_action step=swr_v1_coroutine_selected_create_step(
            &cursor,&scheduler,&cid,&owner,9,0,policies[p]);
        assert(step.action==SWR_CO_CREATE_ACTIVATE);
        assert(cid.value==1 && scheduler.last_cid==1 && scheduler.peak_num==1);
        assert(swr_v1_coroutine_registry_lookup(owner,1)==9);
        assert(swr_v1_coroutine_selected_create_step(&cursor,NULL,NULL,NULL,0,0,unknown).action==SWR_CO_CREATE_DONE);
        swr_v1_coroutine_registry_drop(&owner);
    }
    void *owner=NULL;
    swr_v1_coroutine_scheduler scheduler={65536,17,0,4,1};
    swr_v1_coroutine_creation_cursor cursor={0};
    swr_v1_coroutine_cid cid;
    assert(swr_v1_coroutine_selected_create_step(&cursor,&scheduler,&cid,&owner,9,0,unknown).action==-4);
    assert(cid.value==18 && scheduler.last_cid==18 && scheduler.peak_num==4 && owner==NULL);
    assert(swr_v1_coroutine_selected_create_step(&cursor,NULL,NULL,NULL,0,0,unknown).action==SWR_CO_CREATE_DONE);
    return 0;
}
