// Optional replacement for pinned src/core/base64.cc. Caller ownership stays native.
#ifdef HAVE_CONFIG_H
#include "config.h"
#endif
#ifndef SWOOLE_RS_BASE64
#error "Base64 overlay requires --enable-swoole-rs-base64"
#endif
#include "swoole_base64.h"
#include "swoole_rs_base64.h"

namespace swoole {
size_t base64_encode(const unsigned char *input, size_t length, char *output) {
    return swr_v1_base64_encode(input, length, reinterpret_cast<uint8_t *>(output));
}
size_t base64_decode(const char *input, size_t length, char *output) {
    return swr_v1_base64_decode(reinterpret_cast<const uint8_t *>(input), length, reinterpret_cast<uint8_t *>(output));
}
}  // namespace swoole
