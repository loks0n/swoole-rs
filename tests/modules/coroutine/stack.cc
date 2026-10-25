// Only actual marker algorithm fragments over initialized, ordinary byte storage.
// No Context construction, stack switching, native allocation effects or teardown.
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>
#include <sys/types.h>
#include "swoole_rs_coroutine.h"
#define SW_STRL(s) s, sizeof(s) - 1
#include "stack.inc"

static uint64_t checksum = 1469598103934665603ULL;
static size_t observations;
static void observe(uint64_t value) {
    checksum = (checksum ^ value) * 1099511628211ULL;
    ++observations;
}
int main() {
    for (size_t size : {size_t(0), size_t(1), size_t(32768), size_t(65535), size_t(65536),
                       size_t(65537), size_t(131071), size_t(131072), size_t(131073),
                       size_t(262144), size_t(1048576)}) {
        std::vector<unsigned char> bytes(size + 128, 0xa5);
        auto *stack = reinterpret_cast<char *>(bytes.data() + 64);
        Context context{stack, size};
        initialize(stack, size);
        for (auto byte : bytes) observe(byte);
        observe(context.get_stack_usage());
        for (size_t offset = START_OFFSET; offset <= size; offset *= 2) {
            for (size_t index : {size_t(0), sizeof(MAGIC_STRING) - 2}) {
                initialize(stack, size);
                stack[size - offset + sizeof(MAGIC_STRING) - 1 + index] ^= 1;
                observe(context.get_stack_usage());
            }
        }
        for (size_t i = 0; i < 64; ++i) {
            assert(bytes[i] == 0xa5 && bytes[size + 64 + i] == 0xa5);
        }
    }
    std::printf("{\"observations\":%zu,\"checksum\":%llu}\n", observations,
                static_cast<unsigned long long>(checksum));
}
