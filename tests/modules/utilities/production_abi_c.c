/* Ordinary C11 front door for a source-matched full production archive. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
extern uint32_t swr_v1_abi_version(void);
extern uint64_t swr_v1_feature_bits(void);
int main(int argc, char **argv) {
    assert(argc == 2);
    char *end = NULL;
    const uint64_t expected = strtoull(argv[1], &end, 10);
    assert(end != argv[1] && *end == 0);
    assert(swr_v1_abi_version() == 1);
    assert(swr_v1_feature_bits() == expected && (expected & 512));
    printf("{\"abi\":1,\"features\":%llu}\n", (unsigned long long) expected);
    return 0;
}
