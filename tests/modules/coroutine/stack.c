#include "swoole_rs_coroutine.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
int main(void) {
    unsigned char storage[131073] = {0};
    swr_v1_context_stack_mark(storage, sizeof(storage));
    assert(swr_v1_context_stack_usage(storage, sizeof(storage)) == 65536);
    memset(storage, 0, sizeof(storage));
    assert(swr_v1_context_stack_usage(storage, sizeof(storage)) == 262144);
    puts("context-markers-c11:ok");
}
