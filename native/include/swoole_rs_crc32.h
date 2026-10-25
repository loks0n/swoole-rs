#ifndef SWOOLE_RS_CRC32_H
#define SWOOLE_RS_CRC32_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* IEEE CRC32, initial/final XOR 0xffffffff; null input only at zero length. */
uint32_t swr_v1_crc32(const uint8_t *input, size_t length);
#ifdef __cplusplus
}
#endif
#endif
