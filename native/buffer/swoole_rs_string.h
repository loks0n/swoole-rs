#ifndef SWOOLE_RS_STRING_H
#define SWOOLE_RS_STRING_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct { uint8_t *data; size_t length, capacity; int64_t offset; } swr_v1_string_state;
/* Metadata-only ownership transitions; no pointer dereference or allocator call. */
enum { SWR_STRING_CLEAR, SWR_STRING_TAKE };
typedef struct { swr_v1_string_state state, owner; } swr_v1_string_transition_result;
int32_t swr_v1_string_transition(const swr_v1_string_state *, uint32_t, swr_v1_string_transition_result *);
/* Initial plan does not inspect source; reserve receives an independent live snapshot. */
enum { SWR_STRING_ALLOCATION_INITIAL, SWR_STRING_ALLOCATION_RESERVE };
typedef struct { size_t capacity; uint32_t action; } swr_v1_string_allocation_plan_result;
int32_t swr_v1_string_allocation_plan(uint32_t, const swr_v1_string_state *, size_t, size_t,
                                    swr_v1_string_allocation_plan_result *);
/* Full native ownership effect sequence; metadata is not cleared before free.
 * Operations dispose=0/copy assignment=1/move assignment=2; low-byte actions. */
enum { SWR_STRING_OWNER_DISPOSE, SWR_STRING_OWNER_COPY, SWR_STRING_OWNER_MOVE };
enum { SWR_STRING_OWNER_FREE=1, SWR_STRING_OWNER_DO_COPY=2, SWR_STRING_OWNER_DO_MOVE=3 };
typedef struct { uint8_t *owner; uint64_t actions; } swr_v1_string_ownership_plan_result;
int32_t swr_v1_string_ownership_plan(uint32_t operation, uint8_t same_object, uint8_t has_allocator,
                                  uint8_t *owner, swr_v1_string_ownership_plan_result *);
enum { SWR_STRING_RESERVE, SWR_STRING_APPEND, SWR_STRING_WRITE, SWR_STRING_REPEAT,
       SWR_STRING_REDUCE, SWR_STRING_POP, SWR_STRING_DROP, SWR_STRING_TERMINATE, SWR_STRING_COPY, SWR_STRING_APPEND_I32 };
typedef struct {
    uint32_t operation;
    const uint8_t *data;
    size_t length, count;
    int64_t offset;
    size_t alignment, page;
} swr_v1_string_edit;
typedef struct {
    size_t capacity, length;
    int64_t offset;
    size_t source_offset;
    uint32_t allocation; /* 0: none, 1: native malloc, 2: native realloc */
} swr_v1_string_plan;
/* Layouts of swoole::Allocator and swoole::String. */
typedef struct {
    void *(*malloc)(size_t);
    void *(*calloc)(size_t, size_t);
    void *(*realloc)(void *, size_t);
    void (*free)(void *);
} swr_v1_string_allocator;
typedef struct {
    size_t length, capacity;
    int64_t offset;
    uint8_t *data;
    const swr_v1_string_allocator *allocator;
} swr_v1_string_object;
/* One whole public String operation; existing prepare/apply stays frozen. */
int32_t swr_v1_string_edit_object(swr_v1_string_object *, const swr_v1_string_object *,
    const swr_v1_string_edit *, const swr_v1_string_allocator *, uint8_t **);
int32_t swr_v1_string_prepare(const swr_v1_string_state *, const swr_v1_string_edit *, swr_v1_string_plan *);
int32_t swr_v1_string_apply(swr_v1_string_state *, const swr_v1_string_edit *, const swr_v1_string_plan *, uint8_t *, uint8_t **);
int32_t swr_v1_string_edit_in_place(swr_v1_string_state *, const swr_v1_string_edit *, swr_v1_string_plan *, uint8_t **);
/* Only exact standard-libc-owned storage, after native checks all four function pointers. */
int32_t swr_v1_string_edit_system(swr_v1_string_state *, const swr_v1_string_edit *, uint8_t **);
int32_t swr_v1_string_append_in_place(uint8_t *, size_t *, size_t, const uint8_t *, size_t);
enum { SWR_STRING_CONTAINS, SWR_STRING_STARTS_WITH, SWR_STRING_ENDS_WITH, SWR_STRING_EQUALS };
typedef struct { size_t begin, length, advance; int64_t resume; size_t consumed; } swr_v1_string_split_step;
typedef struct { int64_t prefix; size_t advance; uint32_t pending; } swr_v1_string_split_cursor;
typedef struct {
    swr_v1_string_split_step step;
    swr_v1_string_split_cursor cursor;
    int64_t offset, value;
    size_t trace_value;
    uint32_t action, trace;
} swr_v1_string_split_plan_result;
int32_t swr_v1_string_split_plan(const uint8_t *, size_t, int64_t, const uint8_t *, size_t,
                                const swr_v1_string_split_cursor *, uint32_t, swr_v1_string_split_plan_result *);
/* Native formatting effects execute only after each independently copied step. */
enum { SWR_STRING_FORMAT_DONE, SWR_STRING_FORMAT_RESERVE, SWR_STRING_FORMAT_WRITE, SWR_STRING_FORMAT_COMMIT };
typedef struct { size_t capacity, offset, available, length, result; uint32_t action, next; } swr_v1_string_format_step_result;
int32_t swr_v1_string_format_step(uint32_t, size_t, size_t, size_t, size_t, uint32_t, size_t,
                               swr_v1_string_format_step_result *);
typedef struct { size_t capacity, offset; } swr_v1_string_format_plan_result;
enum { SWR_STRING_RANDOM_RESERVE=1, SWR_STRING_RANDOM_ENTROPY, SWR_STRING_RANDOM_OWNER,
       SWR_STRING_RANDOM_ENCODE, SWR_STRING_RANDOM_COPY, SWR_STRING_RANDOM_PUBLISH,
       SWR_STRING_RANDOM_FALSE, SWR_STRING_RANDOM_TRUE, SWR_STRING_RANDOM_FREE };
typedef struct { size_t capacity, encoded_capacity, length; uint64_t actions; } swr_v1_string_random_step_result;
int32_t swr_v1_string_random_step(uint32_t, size_t, size_t, size_t, size_t, uint32_t, size_t, size_t,
                                swr_v1_string_random_step_result *);
typedef struct { size_t capacity, encoded_capacity; } swr_v1_string_random_plan_result;
int32_t swr_v1_string_match(const uint8_t *, size_t, const uint8_t *, size_t, uint32_t);
int32_t swr_v1_string_range(size_t, size_t, size_t);
int32_t swr_v1_string_split_next(const uint8_t *, size_t, int64_t, int64_t, const uint8_t *, size_t, swr_v1_string_split_step *);
int32_t swr_v1_string_capacity(size_t, size_t, size_t, size_t *);
int32_t swr_v1_string_grow(size_t, size_t, size_t, size_t *, size_t *);
int32_t swr_v1_string_format_plan(size_t, size_t, size_t, uint32_t, size_t, swr_v1_string_format_plan_result *);
int32_t swr_v1_string_random_plan(size_t, size_t, size_t, uint32_t, size_t, size_t, swr_v1_string_random_plan_result *);
/* Nonnull output has twelve writable bytes; null returns zero. Count excludes NUL. */
size_t swr_v1_string_format_i32(int32_t, uint8_t *);
/* 0 appended; 1 needs native allocation without mutation; negative error. */
int32_t swr_v1_string_append_i32(uint8_t *, size_t *, size_t, int32_t);
#ifdef __cplusplus
}
#endif
#endif
