#ifndef SWOOLE_RS_PHPCOLLECTIONS_H
#define SWOOLE_RS_PHPCOLLECTIONS_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Copied metadata only. No allocation, callback, native storage, Zend value or
 * suspension crosses these calls. Return before observing further native facts. */
uint32_t swr_v1_phpcollections_kind(int64_t);
uint8_t swr_v1_phpcollections_string_invalid(int64_t, int64_t);
uint8_t swr_v1_phpcollections_key_warning(size_t, size_t);
size_t swr_v1_phpcollections_count(intptr_t, size_t, size_t);
uint8_t swr_v1_phpcollections_clear_cell(uint8_t present, uint8_t is_null);
/* 0 missing row, 1 field, 2 full row. */
uint32_t swr_v1_phpcollections_get_action(uint8_t row, uint8_t field);
/* Fresh column/value metadata; 0 clear, 1 long, 2 double, 3 string.
 * initialize selects new-row absent/null clearing; updates convert null. */
uint32_t swr_v1_phpcollections_write_action(int64_t kind, uint8_t initialize, uint8_t present, uint8_t is_null);
double swr_v1_phpcollections_float_update(double value, double amount, uint8_t subtract);
/* Returns0 without writing on null output/undefined signed overflow domain. */
uint8_t swr_v1_phpcollections_integer_update(long value, long amount, uint8_t subtract, long *output);
/* Swoole\Coroutine\Channel (Rust): C++ lends the coroutine Channel's
 * operations; Rust registers the class and its zim_swoole_channel_coro_*
 * methods are the table's handlers. */
struct _zend_function_entry;
struct swr_v1_phpcollections_channel_ops {
    void *(*create)(size_t capacity);
    void (*destroy)(void *chan);
    uint8_t (*push)(void *chan, void *data, double timeout);
    void *(*pop)(void *chan, double timeout);
    void *(*pop_data)(void *chan);
    int32_t (*error)(void *chan);
    uint8_t (*close)(void *chan);
    size_t (*length)(void *chan);
    uint8_t (*is_empty)(void *chan);
    uint8_t (*is_full)(void *chan);
    size_t (*consumers)(void *chan);
    size_t (*producers)(void *chan);
    void (*unconstructed)(void);
};
void swr_v1_phpcollections_channel_minit(const struct _zend_function_entry *methods, int32_t module_number,
                                         uint8_t use_shortname,
                                         const struct swr_v1_phpcollections_channel_ops *ops);
/* Copied whole value-operation sequence.1 scalar read,2 array read,3 write.
 * Low byte first; row/Zend effects execute only after return. */
enum SwrCollectionValueAction {
    SWR_VALUE_FALSE=1, SWR_VALUE_READ_LONG=2, SWR_VALUE_READ_DOUBLE=3, SWR_VALUE_READ_STRING=4,
    SWR_VALUE_RETURN_LONG=5, SWR_VALUE_RETURN_DOUBLE=6, SWR_VALUE_RETURN_STRING=7,
    SWR_VALUE_ADD_LONG=8, SWR_VALUE_ADD_DOUBLE=9, SWR_VALUE_ADD_STRING=10, SWR_VALUE_ABORT=11,
    SWR_VALUE_CLEAR=12, SWR_VALUE_CONVERT_LONG=13, SWR_VALUE_CONVERT_DOUBLE=14, SWR_VALUE_CONVERT_STRING=15,
    SWR_VALUE_STORE_LONG=16, SWR_VALUE_STORE_DOUBLE=17, SWR_VALUE_STORE_STRING=18, SWR_VALUE_RELEASE_STRING=19
};
uint64_t swr_v1_phpcollections_value_plan(uint32_t operation, int64_t kind, uint8_t column,
    uint8_t initialize, uint8_t present, uint8_t is_null);
#ifdef __cplusplus
}
#endif
#endif
