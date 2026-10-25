/* Ordinary initialized foreign metadata only. No Coroutine or callable exists. */
#include "swoole_rs_coroutine.h"
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#ifdef SWR_CHANNEL_FFI
extern uint32_t swr_v1_abi_version(void);
extern uint64_t swr_v1_feature_bits(void);
#endif
struct record { uintptr_t prefix[3]; swr_v1_coroutine_identity origin; uintptr_t tail; };
static void *original_root(struct record *co) {
    while (co->origin.token) co = (struct record *)co->origin.token;
    return co;
}
int main(void) {
#ifdef SWR_CHANNEL_FFI
    assert(swr_v1_abi_version()==1); assert(swr_v1_feature_bits() & (UINT64_C(1)<<15));
#endif
    struct record records[192];
    size_t observations=0;
    for(size_t n=1;n<=192;n++) {
        for(size_t i=0;i<n;i++) {
            records[i].prefix[0]=101+i; records[i].prefix[1]=201+i; records[i].prefix[2]=301+i;
            records[i].origin.token=i?&records[i-1]:NULL; records[i].tail=401+i;
        }
        swr_v1_coroutine_identity current={&records[n-1]};
        swr_v1_coroutine_bailout_cursor cursor={NULL,0};
        swr_v1_coroutine_bailout_action step=swr_v1_coroutine_bailout_step(&cursor,&current,0,0);
        assert(step.action==1 && step.coroutine==&records[n-1]);
        /* No Native effect executes. Change initialized metadata between phases
           to witness saved current and fresh post-copy predecessor observation. */
        current.token=NULL;
        step=swr_v1_coroutine_bailout_step(&cursor,NULL,1,0);
        assert(step.action==3 && step.coroutine==&records[n-1]);
        if(n>3) records[n/2].origin.token=NULL;
        size_t offset=(size_t)((const unsigned char *)&records[n-1].origin-(const unsigned char *)&records[n-1]);
        assert(offset==offsetof(struct record,origin));
        step=swr_v1_coroutine_bailout_step(&cursor,NULL,0,offset);
        assert(step.action==4 && step.coroutine==original_root(&records[n-1]));
        assert(swr_v1_coroutine_bailout_step(&cursor,NULL,0,SIZE_MAX).action==5);
        for(size_t i=0;i<n;i++) {
            assert(records[i].prefix[0]==101+i && records[i].prefix[1]==201+i && records[i].prefix[2]==301+i);
            assert(records[i].tail==401+i); observations++;
        }
    }
    swr_v1_coroutine_identity empty={NULL};
    swr_v1_coroutine_bailout_cursor cursor={NULL,0};
    assert(swr_v1_coroutine_bailout_step(&cursor,&empty,0,SIZE_MAX).action==0);
    assert(swr_v1_coroutine_bailout_step(&cursor,NULL,0,SIZE_MAX).action==5);
    assert(observations==18528);
    return 0;
}
