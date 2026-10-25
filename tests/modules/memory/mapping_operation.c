/* Actual C11/Cargo FFI ABI, initialized local backing and success effects only. */
#include "swoole_rs.h"
#include "swoole_rs_memory.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
_Static_assert(sizeof(swr_v2_memory_mapping_operation)==64,"mapping cursor ABI");
_Static_assert(sizeof(swr_v2_memory_mapping_effect)==32,"mapping effect ABI");
int main(void){
    assert(swr_v1_abi_version()==1&&(swr_v1_feature_bits()&64)==64);
    uint64_t arena[32];memset(arena,0xa5,sizeof(arena));
    swr_v2_memory_mapping_operation state={0};swr_v2_memory_mapping_effect effect={0};
    state.requested=64;state.flags=16;state.anonymous=1;state.anonymous_flags=32;
    assert(swr_v2_memory_mapping_step(&state,&effect)==1);
    assert(effect.action==SWR_MEMORY_MAPPING_MAP&&effect.size==72&&effect.flags==48&&effect.descriptor==-1);
    state.memory=(uint8_t *)arena;state.result=1;
    assert(swr_v2_memory_mapping_step(&state,&effect)==0);
    uint8_t *payload=effect.memory;assert(payload==(uint8_t *)arena+8&&arena[0]==72);
    for(size_t i=1;i<32;++i)assert(arena[i]==UINT64_C(0xa5a5a5a5a5a5a5a5));
    memset(&state,0,sizeof(state));state.kind=SWR_MEMORY_MAPPING_PROTECT;state.source=payload;state.flags=3;
    assert(swr_v2_memory_mapping_step(&state,&effect)==1&&effect.action==SWR_MEMORY_MAPPING_SET_PROTECTION);
    assert(effect.memory==arena&&effect.size==72&&effect.flags==3);state.result=0;
    assert(swr_v2_memory_mapping_step(&state,&effect)==0&&effect.result==0);
    memset(&state,0,sizeof(state));state.kind=SWR_MEMORY_MAPPING_RELEASE;state.source=payload;
    assert(swr_v2_memory_mapping_step(&state,&effect)==1&&effect.action==SWR_MEMORY_MAPPING_UNMAP);
    assert(effect.memory==arena&&effect.size==72);state.result=0;
    assert(swr_v2_memory_mapping_step(&state,&effect)==0);
    printf("{\"abi\":1,\"feature_bits\":%llu,\"c11_success_operations\":3,\"explicit_os_calls\":0,\"passed\":true}\n",(unsigned long long)swr_v1_feature_bits());
}
