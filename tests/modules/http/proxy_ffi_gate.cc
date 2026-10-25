// The actual Cargo HTTP-only FFI archive must expose the real operation without
// activating the Native Base64 feature. Ordinary credential input only.
#include "swoole_rs_http.h"
#include <cstring>
#include <iostream>
extern "C" uint64_t swr_v1_feature_bits();
int main() {
    const uint8_t user[] = "user", password[] = "password";
    swr_v1_http_proxy_text fields[]{{user, 4}, {password, 8}};
    uint8_t output[512]{}; size_t written = 0;
    if (swr_v1_feature_bits() != 256 ||
        swr_v2_http_proxy_authorization(fields, output, &written) != 0 ||
        written != 20 || std::memcmp(output, "dXNlcjpwYXNzd29yZA==", 21) != 0) return 1;
    std::cout << "{\"feature_bits\":256,\"authorization_passed\":true}\n";
}
