#ifndef SWOOLE_RS_UTILITIES_H
#define SWOOLE_RS_UTILITIES_H
#include <stdint.h>
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Complete callback-free macro programs. Context is unique during each call;
 * no fact, argument, buffer, global or callback is retained by Rust.
 * Operations0..9: info,notice,warning,debug,trace,sys_notice,sys_warning,
 * error_log,error,sys_error. Actions0..7: done,publish,threshold,mask,ignored,
 * format,put,exit. Facts only answer the immediately preceding action.
 * unsigned_width0=signed,32/64=original usual unsigned integer comparison. */
struct SwrLogFrontdoor { uint32_t phase, admitted; };
struct SwrLogAction { uint32_t action; int32_t level; };
struct SwrLogAction swr_v2_utils_log_frontdoor_step(struct SwrLogFrontdoor *, uint32_t, int64_t, int64_t, uint32_t, uint64_t);
/* Whole hex record sequence. Native effects write actual row arrays, classify
 * fresh original promoted char and return exact sprintf counts after Rust returns.
 * Actions:0done1header2hex-format3ctype4text-byte5text-dot6row7footer. */
struct SwrLogHex { uint32_t phase; size_t offset, index, hex_length, text_length; };
uint32_t swr_v2_utils_log_hex_step(struct SwrLogHex *, size_t, int32_t);
/* LP64 arithmetic. algorithm: PHP=0, Jenkins=1, Austin=2; signed_char is host char semantics. */
uint64_t swr_v1_utils_hash(const uint8_t *, size_t, uint32_t algorithm, uint8_t signed_char);
/* Native-compatible aligned shared u32 atomic, native release store remains outside Rust. */
void swr_v1_utils_spinlock(uint32_t *, uint32_t cpus, uint32_t backoff_limit);
#ifdef HAVE_FUTEX
/* Futex wait/wake on a shared aligned native u32 atomic.
 * Caller owns lifetime; no callback or allocation; preserves native errno. */
int32_t swr_v1_utils_wait(uint32_t *, double timeout);
int32_t swr_v1_utils_wakeup(uint32_t *, int32_t n);
#endif
/* Borrowed bytes and independent aligned outputs; returns a substring span, never allocates. */
int32_t swr_v1_utils_pretty_range(const uint8_t *, size_t, uint8_t strip, size_t *, size_t *);
/* Logging enum policy, returned strings are immutable static NUL-terminated storage. */
int32_t swr_v1_utils_log_level(int32_t);
const char *swr_v1_utils_log_label(int32_t);
const char *swr_v1_utils_log_rotation(int32_t);
/* Exact Logger::put line, signed printf precision; no callback/allocation.
 * Capacity<=INT_MAX; null output iff zero capacity; inputs/output disjoint. */
size_t swr_v1_utils_log_line(uint8_t *, size_t, const uint8_t *, int32_t, uint8_t,
                           int32_t, int32_t, int32_t, const uint8_t *, int32_t);
/* Exact microsecond suffix, same output bounds and count convention. */
size_t swr_v1_utils_log_micros(uint8_t *, size_t, int64_t);
/* Callback-free logger redirect sequencing. Initialize phase=0. All descriptor
 * operations, field updates and diagnostics execute natively between steps. */
enum SwrUtilsRedirectAction {
    SWR_UTILS_REDIRECT_INVALID = 0, SWR_UTILS_REDIRECT_DUP_OUT = 1,
    SWR_UTILS_REDIRECT_DUP_ERR = 2, SWR_UTILS_REDIRECT_ENABLE = 3,
    SWR_UTILS_REDIRECT_RESTORE_OUT = 4, SWR_UTILS_REDIRECT_RESTORE_ERR = 5,
    SWR_UTILS_REDIRECT_CLOSE_OUT = 6, SWR_UTILS_REDIRECT_CLOSE_ERR = 7,
    SWR_UTILS_REDIRECT_DONE = 8, SWR_UTILS_REDIRECT_NO_FILE = 20,
    SWR_UTILS_REDIRECT_ALREADY = 21, SWR_UTILS_REDIRECT_NOT_ENABLED = 22,
    SWR_UTILS_REDIRECT_DUP_OUT_FAILED = 23, SWR_UTILS_REDIRECT_DUP_ERR_FAILED = 24,
    SWR_UTILS_REDIRECT_RESTORE_OUT_FAILED = 25, SWR_UTILS_REDIRECT_RESTORE_ERR_FAILED = 26
};
uint32_t swr_v1_utils_redirect_step(uint32_t *phase, uint8_t enable, uint8_t opened,
                                     uint8_t redirected, int32_t previous_result);
/* Logger file operations open=0, close=1, reopen=2. Scalar facts only; phase=0.
 * All IO, allocation, warning and field writes execute after Rust returns. */
enum SwrUtilsLogFileAction {
    SWR_UTILS_LOG_FILE_INVALID = 0, SWR_UTILS_LOG_FILE_DONE = 1,
    SWR_UTILS_LOG_FILE_CLOSE = 2, SWR_UTILS_LOG_FILE_ASSIGN_PATH = 3,
    SWR_UTILS_LOG_FILE_ROTATE_PATH = 4, SWR_UTILS_LOG_FILE_PLAIN_PATH = 5,
    SWR_UTILS_LOG_FILE_OPEN = 6, SWR_UTILS_LOG_FILE_OPENED = 7,
    SWR_UTILS_LOG_FILE_FAILED = 8, SWR_UTILS_LOG_FILE_SAVE_PATH = 9,
    SWR_UTILS_LOG_FILE_REOPEN_SAVED = 10, SWR_UTILS_LOG_FILE_REDIRECT = 11
};
uint32_t swr_v1_utils_log_file_step(uint32_t *phase, uint32_t operation, uint8_t opened,
                                  int32_t rotation, uint8_t redirected, int32_t descriptor);
/* Caller phase=0; refreshed Logger facts, no retained state or native effects. */
enum SwrUtilsLogPutAction {
    SWR_UTILS_LOG_PUT_INVALID = 0, SWR_UTILS_LOG_PUT_DONE = 1,
    SWR_UTILS_LOG_PUT_DATE = 2, SWR_UTILS_LOG_PUT_ROTATE = 3,
    SWR_UTILS_LOG_PUT_MICROS = 4, SWR_UTILS_LOG_PUT_IDENTITY = 5,
    SWR_UTILS_LOG_PUT_FORMAT = 6, SWR_UTILS_LOG_PUT_LOCK = 7,
    SWR_UTILS_LOG_PUT_FILE_LOCK = 8, SWR_UTILS_LOG_PUT_WRITE = 9,
    SWR_UTILS_LOG_PUT_FLUSH = 10, SWR_UTILS_LOG_PUT_FILE_UNLOCK = 11,
    SWR_UTILS_LOG_PUT_UNLOCK = 12, SWR_UTILS_LOG_PUT_BACKTRACE = 13,
    SWR_UTILS_LOG_PUT_SKIP = 14
};
/* Observe only the corresponding field in these caller-owned phases. */
enum SwrUtilsLogPutObservationPhase {
    SWR_UTILS_LOG_PUT_FILTER_PHASE = 0, SWR_UTILS_LOG_PUT_ROTATION_PHASE = 1,
    SWR_UTILS_LOG_PUT_MICROS_PHASE = 2, SWR_UTILS_LOG_PUT_FILE_LOCK_PHASE = 6,
    SWR_UTILS_LOG_PUT_FILE_UNLOCK_PHASE = 9, SWR_UTILS_LOG_PUT_BACKTRACE_PHASE = 11
};
uint32_t swr_v1_utils_log_put_step(uint32_t *phase, int32_t level, int32_t threshold,
                                 int32_t rotation, uint8_t microseconds, uint8_t opened, uint8_t backtrace);
/* Complete emission controller; frozen put_step remains unchanged. Native
 * rotation scope must finish (including temporary string destruction) before
 * entering micros phase. No Rust frame spans comparison/locks/identity effects. */
enum SwrUtilsLogEmitAction {
    SWR_UTILS_LOG_EMIT_ROTATION_LOCK = 15, SWR_UTILS_LOG_EMIT_ROTATION_REOPEN = 16,
    SWR_UTILS_LOG_EMIT_ROTATION_UNLOCK = 17, SWR_UTILS_LOG_EMIT_PROCESS_ID = 18,
    SWR_UTILS_LOG_EMIT_WORKER_SYMBOL = 19
};
enum SwrUtilsLogEmitObservationPhase {
    SWR_UTILS_LOG_EMIT_PATH_PHASE = 14, SWR_UTILS_LOG_EMIT_FORMAT_PHASE = 4
};
uint32_t swr_v1_utils_log_emit_step(uint32_t *phase, int32_t level, int32_t threshold,
                                  int32_t rotation, uint8_t microseconds, uint8_t opened,
                                  uint8_t backtrace, uint8_t path_changed,
                                  uint8_t acquired, int32_t worker_pid);
/* Configuration operations reset=0/date=1/stream=2, exclusive phase starts0.
 * Native effects occur after return. Defaults output needed only for reset;
 * static date-format pointer is immutable. Public Logger layout is unchanged. */
struct SwrUtilsLogDefaults {
    const char *date_format;
    int32_t rotation, level;
    uint8_t microseconds;
};
enum SwrUtilsLogConfigAction {
    SWR_UTILS_LOG_CONFIG_INVALID = 0, SWR_UTILS_LOG_CONFIG_DONE = 1,
    SWR_UTILS_LOG_CONFIG_RESET = 2, SWR_UTILS_LOG_CONFIG_FORMAT_DATE = 3,
    SWR_UTILS_LOG_CONFIG_REJECT_DATE = 4, SWR_UTILS_LOG_CONFIG_ASSIGN_DATE = 5,
    SWR_UTILS_LOG_CONFIG_CLOSE = 6, SWR_UTILS_LOG_CONFIG_ASSIGN_STREAM = 7
};
uint32_t swr_v1_utils_log_config_step(uint32_t *phase, uint32_t operation,
                                    uint8_t opened, size_t formatted,
                                    struct SwrUtilsLogDefaults *defaults);
/* Selected Logger state ABI2: sole owned logical/string storage. Native FILE,
 * descriptors and mutex remain outside Rust. All effects follow return.
 * Handles are single-owner, live until destroy; configuration is quiescent.
 * Text pointers remain valid until the corresponding mutation or destruction.
 * put/reopen retain native locking; no Rust reference spans a native effect.
 * Mutations publish complete replacements only. Map status to native exceptions
 * after return; exact allocation topology/failure parity remains unqualified. */
struct SwrUtilsLogState;
enum SwrUtilsLogStateStatus {
    SWR_UTILS_STATE_OK = 0, SWR_UTILS_STATE_LENGTH = 1,
    SWR_UTILS_STATE_CAPACITY = 2, SWR_UTILS_STATE_ALLOCATION = 3,
    SWR_UTILS_STATE_INVALID = 4
};
enum SwrUtilsLogStateScalar {
    SWR_UTILS_STATE_OPENED = 0, SWR_UTILS_STATE_REDIRECTED = 1,
    SWR_UTILS_STATE_BACKTRACE = 2, SWR_UTILS_STATE_LEVEL = 3,
    SWR_UTILS_STATE_MICROS = 4, SWR_UTILS_STATE_ROTATION = 5
};
enum SwrUtilsLogStateText {
    SWR_UTILS_STATE_FILE = 0, SWR_UTILS_STATE_REAL_FILE = 1, SWR_UTILS_STATE_DATE = 2
};
uint32_t swr_v1_utils_log_state_create(size_t native_max, struct SwrUtilsLogState **);
void swr_v1_utils_log_state_destroy(struct SwrUtilsLogState *);
int32_t swr_v1_utils_log_state_scalar_get(const struct SwrUtilsLogState *, uint32_t field);
uint32_t swr_v1_utils_log_state_scalar_set(const struct SwrUtilsLogState *, uint32_t field, int32_t value);
const char *swr_v1_utils_log_state_text_get(const struct SwrUtilsLogState *, uint32_t field);
/* input is readable length bytes (null iff length0), may alias current text. */
uint32_t swr_v1_utils_log_state_text_set(const struct SwrUtilsLogState *, uint32_t field, const uint8_t *input, size_t length);
uint32_t swr_v1_utils_log_state_text_copy(const struct SwrUtilsLogState *, uint32_t source, uint32_t target);
void swr_v1_utils_log_state_reset(const struct SwrUtilsLogState *);
void swr_v1_utils_log_state_clear(const struct SwrUtilsLogState *, uint8_t failed_open);
uint32_t swr_v1_utils_log_state_file_step(const struct SwrUtilsLogState *, uint32_t *phase, uint32_t operation, int32_t descriptor);
uint32_t swr_v1_utils_log_state_redirect_step(const struct SwrUtilsLogState *, uint32_t *phase, uint8_t enable, int32_t result);
uint32_t swr_v1_utils_log_state_config_step(const struct SwrUtilsLogState *, uint32_t *phase, uint32_t operation, size_t formatted);
uint32_t swr_v1_utils_log_state_emit_step(const struct SwrUtilsLogState *, uint32_t *phase, int32_t level,
                                        uint8_t path_changed, uint8_t acquired, int32_t worker_pid);
/* Scoped Rust filename owner. Operation0 captures logical C filename before
 * close; operation1 captures external binary file bytes before calendar effects.
 * Inputs are copied; no Rust frame survives native effects. output starts null;
 * reserve/owner allocation are fallible and publish only a completed value.
 * get borrows until destroy/adopt. adopt consumes on success only and transfers
 * bytes to resolved state without another allocation; caller quiescence applies.
 * emit compares the value with fresh resolved C filename only at phase14.
 * Native RAII retains scope; exact allocation/exception topology is unqualified. */
struct SwrUtilsLogPath;
uint32_t swr_v1_utils_log_path_create(const struct SwrUtilsLogState *, uint32_t operation,
    const uint8_t *file, size_t length, struct SwrUtilsLogPath **);
/* Complete captured file+dot+date after calendar return, atomically on success. */
uint32_t swr_v1_utils_log_path_rotate(struct SwrUtilsLogPath *, const uint8_t *date, size_t date_length);
const char *swr_v1_utils_log_path_get(const struct SwrUtilsLogPath *, size_t *length);
void swr_v1_utils_log_path_destroy(struct SwrUtilsLogPath *);
uint32_t swr_v1_utils_log_path_adopt(const struct SwrUtilsLogState *, struct SwrUtilsLogPath *);
uint32_t swr_v1_utils_log_path_emit_step(const struct SwrUtilsLogState *, uint32_t *phase,
    int32_t level, const struct SwrUtilsLogPath *, uint8_t acquired, int32_t worker_pid);
/* Additive complete inline publication ABI; all v1 declarations stay frozen.
 * Cursor/range are caller-owned and quiescent. ltrim length0 does not read the
 * cursor slot; rtrim length0 performs no access. Defined host ctype inputs only.
 * Writes/pointer progression occur at original per-byte boundaries in Rust. */
size_t swr_v2_utils_ltrim(char **cursor, size_t length, uint8_t signed_char);
size_t swr_v2_utils_rtrim(char *data, size_t length, uint8_t signed_char);
struct SwrUtilsSearchResult {
    const char *pointer;
    ptrdiff_t offset;
    uint32_t needle_length;
};
/* Search0/1 binary/libc casefold;2 discovers original C-needle uint32 length.
 * Initialized spans and nonempty needle; reverse length>=needle length.
 * Pointer preserves input provenance, offset-1/null on miss. No retention.
 * Native debug assertion effects follow return; invalid needle/order excluded. */
struct SwrUtilsSearchResult swr_v2_utils_search(const char *, size_t,
    const char *, uint32_t needle_length, uint8_t mode);
/* Borrowed inline byte policy; search modes binary=0, libc casefold=1, reverse=2. */
size_t swr_v1_utils_trim(const uint8_t *, size_t, uint8_t right, uint8_t signed_char);
ptrdiff_t swr_v1_utils_find(const uint8_t *, size_t, const uint8_t *, size_t, uint8_t mode);
/* C equality=0/1 (plain/casefold), C prefix=2/3, binary prefix=4/suffix=5.
 * C modes preserve early NUL; borrowed compared ranges only, no retention. */
uint8_t swr_v1_utils_compare(const uint8_t *, size_t, const uint8_t *, size_t, uint8_t mode);
ptrdiff_t swr_v1_utils_partition(const uint8_t *, size_t, uint8_t separator, uint8_t before);
/* Exclusive mutable char range; native tolower locale/promotions, no retention.
 * Nonpositive length performs no access. Original undefined ctype inputs excluded. */
void swr_v1_utils_lowercase(uint8_t *, int32_t length, uint8_t signed_char);
#ifdef __cplusplus
}
#include <type_traits>
#include <utility>
namespace swoole_rs_utilities {
struct LogFacts { int64_t first, second; uint32_t unsigned_width; uint64_t high; };
inline LogFacts log_facts(int64_t first, int64_t second) { return {first, second, 0, 0}; }
// ADL detects enum operator overloads; classes always take the exact external
// expression path. Neither type inspection nor common_type evaluates operands.
template<class T> auto log_external_compare(int)
    -> decltype(operator>=(std::declval<T>(), std::declval<int>()), std::true_type{});
template<class> auto log_external_compare(...) -> std::false_type;
template<class T> struct LogNumericLevel {
    using Plain = typename std::remove_cv<typename std::remove_reference<T>::type>::type;
    static constexpr bool value =
        (std::is_arithmetic<Plain>::value || std::is_enum<Plain>::value
#ifdef __SIZEOF_INT128__
         || std::is_same<Plain, __int128>::value || std::is_same<Plain, unsigned __int128>::value
#endif
        ) && !decltype(log_external_compare<T>(0))::value;
};
// Host floating >= is an external ABI/FENV primitive, including long double.
// It executes only after Rust requests the operand observation, without any
// Rust frame or borrow spanning its floating exceptions/rounding environment.
template<class Common> inline typename std::enable_if<std::is_floating_point<Common>::value, LogFacts>::type
log_numeric_facts(Common value, int threshold) {
    return {value >= threshold ? 1 : 0, threshold, 256, 0};
}
template<class Common> inline typename std::enable_if<!std::is_floating_point<Common>::value, LogFacts>::type
log_numeric_facts(Common value, int threshold) {
    uint64_t high = 0;
    uint32_t kind = std::is_unsigned<Common>::value ? uint32_t(sizeof(Common) * 8) : 0;
#ifdef __SIZEOF_INT128__
    if (sizeof(Common) > 8) {
        high = static_cast<uint64_t>(static_cast<unsigned __int128>(value) >> 64);
        kind = std::is_signed<Common>::value ? 129 : 128;
        // Some standard libraries do not classify compiler extended integers.
        if (std::is_same<Common, __int128>::value) kind = 129;
    }
#endif
    return {static_cast<int64_t>(value), threshold, kind, high};
}
template<class Level> inline typename std::enable_if<LogNumericLevel<Level &&>::value, LogFacts>::type
log_level_facts(Level &&value, int threshold) {
    using Plain = typename std::remove_reference<Level>::type;
    using Common = typename std::common_type<Plain, int>::type;
    return log_numeric_facts<Common>(static_cast<Common>(value), threshold);
}
// Unexecuted numeric arm must remain well-formed for noncopyable user operands.
template<class Level> inline typename std::enable_if<!LogNumericLevel<Level &&>::value, LogFacts>::type
log_level_facts(Level &&, int) { return {}; }
inline bool log_numeric_admit(LogFacts facts) {
    SwrLogFrontdoor state = {2, 0};
    return swr_v2_utils_log_frontdoor_step(&state, 7, facts.first, facts.second,
                                           facts.unsigned_width, facts.high).action == 4;
}
inline bool log_ignored_result(bool ignored) {
    SwrLogFrontdoor state = {8, 0};
    return swr_v2_utils_log_frontdoor_step(&state, 7, ignored, 0, 0, 0).action == 5;
}
inline LogFacts log_complete_condition(bool accepted) { return {accepted, 0, 257, 0}; }
/* Bare-if macros split the pure guard from the fixed post-format continuation.
 * No user argument executes inside a helper/lambda, preserving __func__ and the
 * caller's function scope. Native && only dispatches the requested mask fact. */
inline bool log_frontdoor_admit(uint32_t operation, int64_t threshold) {
    SwrLogFrontdoor state = {};
    (void) swr_v2_utils_log_frontdoor_step(&state, operation, 0, 0, 0, 0);
    const SwrLogAction next = swr_v2_utils_log_frontdoor_step(&state, operation, 0, threshold, 0, 0);
    return next.action == 3 || next.action == 5;
}
inline bool log_frontdoor_mask(int64_t mask, int64_t flags) {
    SwrLogFrontdoor state = {3, 0};
    return swr_v2_utils_log_frontdoor_step(&state, 4, mask, flags, 0, 0).action == 5;
}
}
#endif
#endif
