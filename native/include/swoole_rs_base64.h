/* Frozen borrowed-buffer ABI; preconditions and exact writes in core-abi-v1.md. */

#ifndef SWOOLE_RS_BASE64_H
#define SWOOLE_RS_BASE64_H

/* Generated from crates/base64 by cbindgen (tools/headers.sh); do not edit. */

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif // __cplusplus

size_t swr_v1_base64_encode(const uint8_t *input, size_t length, uint8_t *output);

size_t swr_v1_base64_decode(const uint8_t *input, size_t length, uint8_t *output);

#ifdef __cplusplus
}  // extern "C"
#endif  // __cplusplus

#endif  /* SWOOLE_RS_BASE64_H */
