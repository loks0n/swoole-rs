/* C11 caller ABI only; effects are represented by primitive observations. */
#include "swoole_rs_coroutine.h"
#include <assert.h>
int main(void) {
    swr_v1_coroutine_entry_cursor cursor={1,0,0,0};
    assert(swr_v1_coroutine_entry_step(&cursor,0).action==0);
    assert(swr_v1_coroutine_entry_step(&cursor,1).action==3);
    swr_v1_coroutine_entry_action done=swr_v1_coroutine_entry_step(&cursor,17);
    assert(done.action==6 && done.result==17);
    assert(swr_v1_coroutine_entry_step(&cursor,0).result==17);
    return 0;
}
