#ifndef SWOOLE_RS_BASE64_H
#define SWOOLE_RS_BASE64_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Frozen borrowed-buffer ABI; preconditions and exact writes in core-abi-v1.md. */
size_t swr_v1_base64_encode(const uint8_t *input, size_t length, uint8_t *output);
size_t swr_v1_base64_decode(const uint8_t *input, size_t length, uint8_t *output);
#ifdef __cplusplus
}
#endif
#endif
