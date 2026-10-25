#include "swoole_rs_coroutine.h"
#include <assert.h>
#include <stdio.h>

int main(void) {
    swr_v1_channel_tokens *owner = swr_v1_channel_tokens_new();
    assert(owner != NULL);
    assert(swr_v1_channel_tokens_push(owner, NULL) == 0);
    assert(swr_v1_channel_tokens_len(owner) == 1);
    void *value = owner;
    assert(swr_v1_channel_tokens_front(owner, &value) == 1 && value == NULL);
    swr_v1_channel_tokens *copy = swr_v1_channel_tokens_clone(owner);
    assert(copy != NULL);
    swr_v1_channel_tokens_remove(copy, NULL);
    assert(swr_v1_channel_tokens_len(copy) == 0);
    assert(swr_v1_channel_tokens_len(owner) == 1);
    swr_v1_channel_tokens_pop(owner);
    assert(swr_v1_channel_tokens_front(owner, &value) == 0);
    swr_v1_channel_tokens_free(copy);
    swr_v1_channel_tokens_free(owner);
    puts("channel-token-c11:ok");
}
