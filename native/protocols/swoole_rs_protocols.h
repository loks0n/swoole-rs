#ifndef SWOOLE_RS_PROTOCOLS_H
#define SWOOLE_RS_PROTOCOLS_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Borrowed byte ranges; no allocation, callbacks, retained pointers or I/O. */
int64_t swr_v1_mqtt_frame_length(const uint8_t *, size_t);
typedef struct { uint8_t state, action, error, reply; } swr_socks_transition;
int32_t swr_v1_socks_transition(uint8_t state, uint8_t method, const uint8_t *, size_t, swr_socks_transition *);
int64_t swr_v1_socks_negotiate(uint8_t has_user, uint8_t *method, uint8_t *output, size_t capacity);
int64_t swr_v1_socks_auth(const uint8_t *user, size_t user_length, const uint8_t *password, size_t password_length, uint8_t *output, size_t capacity);
int64_t swr_v1_socks_connect(uint8_t address_type, const uint8_t *address, size_t length, uint16_t port, uint8_t *output, size_t capacity);
/* Factory:0 rejected,1 no credentials,2 both credentials; max250 each. */
int32_t swr_v1_socks_config(size_t user_length, size_t password_length);
/* Static borrowed string; never free. */
const char *swr_v1_socks_strerror(int32_t code);
/* -2 proxy host over480, otherwise frozen CONNECT result; destination length
 * is independent. Oversized proxy is checked before borrowed memory access. */
int64_t swr_v1_socks_domain_connect(size_t proxy_length, const uint8_t *destination,
                                   size_t length, uint16_t port, uint8_t *output, size_t capacity);
typedef struct { size_t offset, length; int32_t integer; uint32_t kind; } swr_resp_span;
/* All-zero state begins a borrowed walk. No callback/allocation in Rust.
 * 1 event,0 end,-1 invalid; invalid leaves state/span unchanged.
 * Event kind0 string parameter,1 integer,2 null,3 first string command. */
typedef struct { size_t position; int32_t length; uint8_t state; } swr_resp_cursor;
typedef struct { swr_resp_cursor cursor; uint8_t command_seen; } swr_resp_php_state;
int32_t swr_v1_resp_php_next(const uint8_t *, size_t, swr_resp_php_state *, swr_resp_span *, uint8_t *range);
/* Fixed64-byte NUL-terminated handler key; returns length,0 on invalid input.
 * Existing PHP raw-length validation remains native; empty input is allowed. */
size_t swr_v1_resp_handler_key(const uint8_t *, size_t, uint8_t *output64);
int64_t swr_v1_resp_parse(const uint8_t *, size_t, swr_resp_span *, size_t capacity);
/* Optional range byte reports signed-long overflow without touching native errno. */
int64_t swr_v1_resp_parse_range(const uint8_t *, size_t, swr_resp_span *, size_t capacity, uint8_t *range);
/* Single scan: writes a bounded prefix, returns full required count; -1 on error.
 * Unlike parse, output may be partially written on error. */
int64_t swr_v1_resp_scan(const uint8_t *, size_t, swr_resp_span *, size_t capacity, uint8_t *range);
size_t swr_v1_resp_format(uint8_t kind, const uint8_t *, size_t, int64_t integer, uint8_t *, size_t);
/* PHP reply wire fragments. Native conversions/allocations run outside Rust.
 * Prefix is complete header/inline bytes; body borrows the input's bounded
 * prefix; suffix_length is 0 or2 for CRLF. Kinds match PHP0/1/2/3/4/5/6,
 * plus8 string-map-key and9 unsigned-map-key. number carries integer bits/count.
 * present only controls status/error defaults. Output untouched on error. */
typedef struct {
    uint8_t prefix[32];
    uint32_t prefix_length;
    size_t body_length;
    uint32_t suffix_length;
} swr_resp_reply_parts;
int32_t swr_v1_resp_reply_parts(uint8_t kind, uint8_t present, uint64_t number,
                               const uint8_t *, size_t, swr_resp_reply_parts *);

typedef struct {
    uint8_t state;
    int32_t lines_total, lines_received, bytes_total, bytes_received, offset;
} swr_resp_request;
int32_t swr_v1_resp_receive(const uint8_t *, size_t length, size_t capacity, size_t maximum,
                          swr_resp_request *, uint8_t *set_offset);
int32_t swr_v1_resp_receive_range(const uint8_t *, size_t length, size_t capacity, size_t maximum,
                                swr_resp_request *, uint8_t *set_offset, uint8_t *range);
typedef struct { uint32_t remaining, offset, maximum, minimum; uint8_t flags, mode; } swr_bus_writer;
typedef struct { uint32_t offset, length; uint8_t flags, mode; } swr_bus_chunk;
int32_t swr_v1_bus_writer_init(uint32_t length, uint32_t maximum, uint32_t minimum,
                              uint8_t has_payload, uint8_t always, swr_bus_writer *);
int32_t swr_v1_bus_writer_next(const swr_bus_writer *, swr_bus_chunk *);
int32_t swr_v1_bus_writer_complete(swr_bus_writer *, uint8_t success, uint8_t reduce);
uint32_t swr_v1_bus_receive_step(uint16_t count, uint8_t end, uint16_t limit);
/* Opaque packet index. Tokens remain native-owned; no callback is invoked.
 * insert transfers membership only on 0; take/pop return removed tokens.
 * release refuses a nonempty index. at leaves id unchanged on failure. */
typedef struct swr_bus_pool swr_bus_pool;
swr_bus_pool *swr_v1_bus_pool_create(void);
swr_bus_pool *swr_v1_bus_pool_create_capacity(size_t capacity);
int32_t swr_v1_bus_pool_release(swr_bus_pool *);
size_t swr_v1_bus_pool_len(const swr_bus_pool *);
uintptr_t swr_v1_bus_pool_find(const swr_bus_pool *, uint64_t id);
/* Borrowed native lookup value, distinct from the owner token. */
uintptr_t swr_v1_bus_pool_find_value(const swr_bus_pool *, uint64_t id);
int32_t swr_v1_bus_pool_insert(swr_bus_pool *, uint64_t id, uintptr_t token);
uintptr_t swr_v1_bus_pool_take(swr_bus_pool *, uint64_t id);
uintptr_t swr_v1_bus_pool_pop(swr_bus_pool *);
uintptr_t swr_v1_bus_pool_at(const swr_bus_pool *, size_t index, uint64_t *id);
typedef struct { uint64_t id; uintptr_t token; } swr_bus_pool_entry;
int32_t swr_v1_bus_pool_insert_many(swr_bus_pool *, const swr_bus_pool_entry *, size_t length);
/* Parallel lookup values stay borrowed; success transfers all owner tokens.
 * Existing insert APIs use the owner token as the lookup value. */
int32_t swr_v1_bus_pool_insert_values(swr_bus_pool *, const swr_bus_pool_entry *, const uintptr_t *lookups, size_t length);
/* Snapshot borrows tokens; drain removes and transfers them. Both are bounded. */
size_t swr_v1_bus_pool_snapshot(const swr_bus_pool *, size_t start, swr_bus_pool_entry *, size_t capacity);
size_t swr_v1_bus_pool_drain(swr_bus_pool *, uintptr_t *, size_t capacity);
#ifdef __cplusplus
}
#endif
#endif
