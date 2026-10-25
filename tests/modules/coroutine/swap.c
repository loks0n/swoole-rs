/* Typed descriptors only; no function/coroutine/context is ever invoked. */
#include "swoole_rs_coroutine.h"
#include <assert.h>
#include <stdalign.h>
static void identity_only(void *task) { (void) task; }
int main(void) {
    _Static_assert(sizeof(swr_v1_coroutine_swap_callback)==sizeof(swr_v1_coroutine_swap_function),"typed function pointer size");
    _Static_assert(alignof(swr_v1_coroutine_swap_callback)==alignof(swr_v1_coroutine_swap_function),"typed function pointer alignment");
    unsigned char token=1;
    swr_v1_coroutine_swap_callback callback;
    for (unsigned op=1;op<=4;op++) {
        if (op==3) continue;
        for (unsigned present=0;present<=1;present++) {
            swr_v1_coroutine_swap_publish(&callback,present?identity_only:0);
            for (unsigned has_task=0;has_task<=1;has_task++) {
                swr_v1_coroutine_identity task={has_task?&token:0};
                for (unsigned bailout=0;bailout<=1;bailout++) {
                    swr_v1_coroutine_status status={0,-2};
                    swr_v1_coroutine_dispatch_result result=swr_v1_coroutine_dispatch(&status,op,&callback,&task,bailout);
                    int proceed=op!=1 || !bailout;
                    int admitted=proceed && present && has_task;
                    assert(result.function==(admitted?identity_only:0));
                    assert(result.task==(admitted?&token:0));
                    assert(status.state==(!proceed?0:op==2?1:op==4?3:2));
                    assert(status.code==(op==2?0:-2));
                }
            }
        }
    }
    assert(token==1);
    return 0;
}
