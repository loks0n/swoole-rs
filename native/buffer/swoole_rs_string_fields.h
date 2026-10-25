#ifndef SWOOLE_RS_STRING_FIELDS_H
#define SWOOLE_RS_STRING_FIELDS_H
#include "swoole_rs_string.h"
#include <sys/types.h>
#ifdef __cplusplus
namespace swoole { struct Allocator; }
typedef const swoole::Allocator *swr_string_allocator_token;
extern "C" {
#else
struct swr_native_allocator;
typedef const struct swr_native_allocator *swr_string_allocator_token;
#endif
/* The additive raw-field ABI is available only on Unix LP64.
 * Other targets retain the complete existing default String APIs. */
#if defined(__LP64__) && (defined(__unix__) || defined(__APPLE__))
/* Layout witness ONLY: never form an alternate record lvalue over String. */
typedef struct {
    size_t length, size;
    off_t offset;
    char *str;
    swr_string_allocator_token allocator;
} swr_string_fields_schema;
typedef struct {
    swr_v1_string_compat_cursor edit;
    swr_string_allocator_token allocator;
    uint8_t *owner;
    size_t requested;
    uint32_t allocation, phase, after;
} swr_v1_string_fields_cursor;
typedef struct {
    swr_string_allocator_token allocator;
    uint8_t *pointer;
    size_t requested;
    uint32_t action;
} swr_v1_string_fields_effect;
enum { SWR_FIELDS_INIT, SWR_FIELDS_ALLOC, SWR_FIELDS_RESERVE, SWR_FIELDS_EDIT,
       SWR_FIELDS_MOVE, SWR_FIELDS_OWNERSHIP, SWR_FIELDS_CLEAR, SWR_FIELDS_RELEASE,
       SWR_FIELDS_GROW, SWR_FIELDS_REDUCE, SWR_FIELDS_BYTES };
enum { SWR_FIELDS_DONE, SWR_FIELDS_DEFAULT, SWR_FIELDS_MALLOC, SWR_FIELDS_REALLOC, SWR_FIELDS_FREE };
/* Actual String/subobject provenance and authorized member windows required.
 * No whole-record reference/copy, Native field publication, callback or ownership
 * transfer to Rust. Source is const; only the move source may be modified. */
int32_t swr_v1_string_fields_step(swr_v1_string_fields_cursor *, void *, const void *, void *,
    uint32_t, size_t, swr_string_allocator_token, const swr_v1_string_edit *,
    swr_string_allocator_token, uint8_t *, swr_v1_string_fields_effect *);
#endif /* Unix LP64 additive ABI */
#ifdef __cplusplus
}
#endif
#if defined(SWOOLE_RS_STRING_DIRECT_FIELDS) && SWOOLE_RS_STRING_DIRECT_FIELDS
#if !defined(SWOOLE_RS_BUFFER) || !SWOOLE_RS_BUFFER
#error "String direct fields requires Rust Buffer"
#endif
/* Qualified schema is arm64 Darwin LP64 with the standard signed64 off_t ABI.
 * Linux and every other target remain refused pending actual target proof. */
#if !defined(__APPLE__) || !defined(__aarch64__) || !defined(__LP64__)
#error "String direct fields target schema is not qualified"
#endif
#if !defined(__apple_build_version__) || __apple_build_version__ != 21000101
#error "String direct fields Native compiler schema is not qualified"
#endif
#endif
#endif
