#ifndef SWOOLE_RS_WEBSOCKET_H
#define SWOOLE_RS_WEBSOCKET_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Borrowed ranges and progressive output semantics: docs/abi-v1.md. */
int64_t swr_v1_ws_frame_length(const uint8_t *data, size_t length, uint32_t *header_length);
size_t swr_v1_ws_write_header(uint64_t payload_length, uint8_t opcode, uint8_t flags,
                            uint8_t *output, size_t capacity);
int32_t swr_v1_ws_mask(uint8_t *data, size_t length, const uint8_t *key);
#ifdef __cplusplus
}
#endif
#endif
