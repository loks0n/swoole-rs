#ifndef SWOOLE_RS_BUFFER_H
#define SWOOLE_RS_BUFFER_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct swr_v1_buffer swr_v1_buffer;
typedef struct { const uint8_t *data; size_t length; } swr_v1_buffer_iovec;
typedef struct {
    uint32_t kind; /* 0: Rust data, 1: opaque native token */
    uint32_t length;
    uint32_t capacity;
    uint8_t *data;
    void *token;
} swr_v1_buffer_view;
enum {
    SWR_BUFFER_OK = 0, SWR_BUFFER_EMPTY = 1,
    SWR_BUFFER_INVALID = -1, SWR_BUFFER_OVERFLOW = -2,
    SWR_BUFFER_NOMEM = -3, SWR_BUFFER_PENDING_NATIVE = -4
};
int32_t swr_v1_buffer_create(uint32_t chunk_size, swr_v1_buffer **output);
int32_t swr_v1_buffer_release(swr_v1_buffer *buffer);
int32_t swr_v1_buffer_append(swr_v1_buffer *buffer, const uint8_t *data, size_t length);
int32_t swr_v1_buffer_appendv(swr_v1_buffer *buffer, const swr_v1_buffer_iovec *iov,
                            size_t count, uint64_t offset);
int32_t swr_v1_buffer_push_native(swr_v1_buffer *buffer, void *token);
int32_t swr_v1_buffer_front(const swr_v1_buffer *buffer, swr_v1_buffer_view *output);
int32_t swr_v1_buffer_pop(swr_v1_buffer *buffer, void **native_token);
int32_t swr_v1_buffer_stats(const swr_v1_buffer *buffer, uint32_t *length, size_t *count);
#ifdef __cplusplus
}
#endif
#endif
