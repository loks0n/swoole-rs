// Deliberately invalid caller: the out-of-bounds read must be reported in Rust.
#include <cstdlib>
#include "swoole_rs_utilities.h"
int main() {
    auto *bytes = static_cast<uint8_t *>(std::malloc(1));
    if (!bytes) return 2;
    bytes[0] = ' ';
    const auto count = swr_v1_utils_trim(bytes, 64, 0, 0);
    std::free(bytes);
    return count == 0 ? 3 : 0;
}
