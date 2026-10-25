// Deliberately invalid caller contracts: each must fail inside instrumented Rust.
// Run only as separate negative sanitizer witnesses, never as valid ABI inputs.
#include "swoole_rs_websocket.h"
#include <cstdio>
#include <cstring>
#include <memory>

int main(int argc, char **argv) {
    if (argc != 2 || (std::strcmp(argv[1], "key") && std::strcmp(argv[1], "payload"))) return 2;
    const bool short_key = !std::strcmp(argv[1], "key");
    auto data = std::make_unique<unsigned char[]>(short_key ? 1 : 7);
    auto key = std::make_unique<unsigned char[]>(short_key ? 3 : 4);
    swr_v1_ws_mask(data.get(), short_key ? 1 : 8, key.get());
    std::puts("UNEXPECTED_RETURN");
    return 0;
}
