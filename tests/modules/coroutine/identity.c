/* Ordinary opaque pointer metadata only: no Coroutine/context/callback exists. */
#include "swoole_rs_coroutine.h"
#include <assert.h>
#include <stdalign.h>
int main(void) {
    _Static_assert(sizeof(swr_v1_coroutine_identity)==sizeof(void *),"pointer cell size");
    _Static_assert(alignof(swr_v1_coroutine_identity)==alignof(void *),"pointer cell alignment");
    unsigned char a=1,b=2,c=3;
    swr_v1_coroutine_identity current={&a},origin={0},task;
    swr_v1_coroutine_identity_publish(&task,&b);
    assert(swr_v1_coroutine_identity_read(&task)==&b);
    swr_v1_coroutine_identity_route(&current,&origin,&b,SWR_CO_IDENTITY_ENTER);
    assert(current.token==&b && origin.token==&a);
    swr_v1_coroutine_identity_publish(&origin,&c);
    swr_v1_coroutine_identity_route(&current,&origin,&b,SWR_CO_IDENTITY_LEAVE);
    assert(current.token==&c && origin.token==&c);
    swr_v1_coroutine_identity_publish(&task,0);
    assert(swr_v1_coroutine_identity_read(&task)==0);
    assert(a==1 && b==2 && c==3);
    return 0;
}
