#include "swoole_rs_coroutine.h"
#include <assert.h>
#include <stdalign.h>
#ifdef SWR_CHANNEL_FFI
extern uint32_t swr_v1_abi_version(void);
extern uint64_t swr_v1_feature_bits(void);
#endif
int main(void) {
#ifdef SWR_CHANNEL_FFI
    assert(swr_v1_abi_version()==1);
    assert(swr_v1_feature_bits()&(UINT64_C(1)<<15));
#endif
    _Static_assert(sizeof(swr_v1_coroutine_cid)==sizeof(long),"CID long size");
    _Static_assert(alignof(swr_v1_coroutine_cid)==alignof(long),"CID long alignment");
    swr_v1_coroutine_cid cid; /* raw publication, no prior read */
    swr_v1_coroutine_scheduler scheduler={65536,0,0,0,0};
    swr_v1_coroutine_creation_cursor cursor={0};
    swr_v1_coroutine_creation_action step=swr_v1_coroutine_create_step(&cursor,&scheduler,&cid,0);
    assert(step.action==SWR_CO_CREATE_INSERT && step.cid==1);
    assert(swr_v1_coroutine_cid_read(&cid)==1);
    step=swr_v1_coroutine_create_step(&cursor,&scheduler,&cid,0);
    assert(step.action==SWR_CO_CREATE_COUNT);
    step=swr_v1_coroutine_create_step(&cursor,&scheduler,&cid,7);
    assert(step.action==SWR_CO_CREATE_COUNT);
    step=swr_v1_coroutine_create_step(&cursor,&scheduler,&cid,5);
    assert(step.action==SWR_CO_CREATE_ACTIVATE && scheduler.peak_num==5);
    /* Terminal metadata only, no object/scheduler access or actual activation. */
    assert(swr_v1_coroutine_create_step(&cursor,0,0,0).action==SWR_CO_CREATE_DONE);
    return 0;
}
