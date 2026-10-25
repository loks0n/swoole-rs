#ifndef SWOOLE_RS_FRAMING_H
#define SWOOLE_RS_FRAMING_H
#ifndef SWOOLE_RS_FRAMING
#error "Framing overlay requires --enable-swoole-rs-framing"
#endif
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct { uint32_t mode, phase, head, recv; int64_t packet; uint32_t again; } SwrFramingState;
typedef struct {
    size_t len, cap; int64_t offset, result; const uint8_t *data, *eof;
    uint32_t eof_len, max, length_offset, page, flags;
} SwrFramingSnapshot;
typedef struct { uint32_t kind; int32_t status; uint64_t value; } SwrFramingAction;
typedef struct { const uint8_t *data; size_t len; } SwrFramingSpan;
SwrFramingAction swr_v1_framing_step(SwrFramingState *, const SwrFramingSnapshot *);
size_t swr_v1_framing_width(uint8_t);
int32_t swr_v1_framing_unpack(uint8_t, const uint8_t *, size_t, int64_t *);
uint64_t swr_v1_framing_hton64(uint64_t);
int32_t swr_v1_framing_default(uint8_t, const uint8_t *, size_t, uint32_t offset, uint32_t size, uint32_t body_offset, int64_t *);
size_t swr_v1_framing_mime_count(void);
uint8_t swr_v1_framing_mime_entry(size_t, SwrFramingSpan *, SwrFramingSpan *);
SwrFramingSpan swr_v1_framing_mime_fallback(void);
/* Borrowed initialized filename. Returns last-dot successor (or0), bounded by
 * length, before native allocation; SIZE_MAX for invalid input extent. */
size_t swr_v1_framing_mime_suffix_offset(const uint8_t *, size_t);
size_t swr_v1_framing_mime_suffix(const uint8_t *, size_t, uint8_t *, size_t, uint8_t native_char_signed);
#ifdef __cplusplus
}
#endif
#endif
