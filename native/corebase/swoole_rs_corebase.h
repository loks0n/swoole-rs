/* SPDX-License-Identifier: Apache-2.0 */
#ifndef SWOOLE_RS_COREBASE_H
#define SWOOLE_RS_COREBASE_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
int32_t swr_v1_corebase_type_size(uint8_t kind);
/* Native facades retain their original positive-operand assertions. */
uint32_t swr_v1_corebase_gcd(uint32_t left, uint32_t right);
uint32_t swr_v1_corebase_lcm(uint32_t left, uint32_t right);
/* Success matches the representable decimal portion of std::stoi; native code
 * retains its exception path and publishes output only after success. */
uint8_t swr_v1_corebase_parse_stoi(const char *input, int32_t *output);
enum swr_v1_corebase_systemd_listen_fds_action {
    SWR_COREBASE_SYSTEMD_LISTEN_FDS_RETURN = 0,
    SWR_COREBASE_SYSTEMD_LISTEN_FDS_WARN_MISSING = 1,
    SWR_COREBASE_SYSTEMD_LISTEN_FDS_ERROR_LIMIT = 2
};
/* getenv, exception construction, and every warning/error side effect remain native. */
uint32_t swr_v1_corebase_systemd_listen_fds_action(uint8_t found, int32_t count, int32_t maximum);
/* Caller owns sufficient output for value's decimal bytes and NUL. */
int32_t swr_v1_corebase_itoa(char *output, long value);
/* Output is writable for capacity bytes; capacity >= sizeof(unsigned long)*8+1.
 * Returns first digit offset, or SIZE_MAX for invalid arguments. */
size_t swr_v1_corebase_radix(unsigned long value, uint32_t radix, uint8_t *output, size_t capacity);
/* Valid NUL-terminated input, disjoint writable parsed output. Original host
 * ctype input requirements apply. These direct libc parsers preserve original errno effects/order. */
/* Frozen target-default mode; native compiler char mode must match Rust. */
unsigned long swr_v1_corebase_hex(const char *input, size_t *parsed);
/* Actual native callers supply their compiler plain-char mode. */
unsigned long swr_v1_corebase_hex_mode(const char *input, size_t *parsed, uint8_t native_char_signed);
int32_t swr_v1_corebase_version(const char *left, const char *right);
/* Nonempty input is readable for length bytes; length <= PTRDIFF_MAX.
 * Returns prefix length; native std::string construction happens afterward. */
size_t swr_v1_corebase_dirname(const uint8_t *input, size_t length);
/* Stack-owned state; zero initialize once, keep state/output unchanged between
 * steps. No pointer retained; native IO occurs after return. Stop on !=1.
 * Return 0 done, 1 NUL-cut prefix ready, 2 path too long, 3 invalid arguments.
 * Input/output/state are disjoint; capacity <= PTRDIFF_MAX. */
struct swr_v1_corebase_mkdir_state {
    size_t length;
    size_t next;
};
int32_t swr_v1_corebase_mkdir_next(const uint8_t *input, size_t length, uint8_t *output,
                                 size_t capacity, struct swr_v1_corebase_mkdir_state *state);
/* Zeroed stack cursor, never a native owner/registry. Execute each returned
 * action after Rust returns, then supply a copied boolean when requested.
 * 0 finishes; UINT32_MAX rejects invalid cursor/operation. No retained pointer.
 * THREAD_INIT argument is main-thread bool; THREAD_CLEAN ignores it;
 * CLEAN argument is native hook-slot count. cursor.index selects hook slot.
 * FORK/FORK_EXEC use pinned native flags; after FORK_CALL, observed is
 * 0=failure, 1=child, 2=parent. Other observations are copied booleans.
 * Preserve operation/argument and stop on DONE/invalid. No Rust frame spans
 * fork or native allocation/callback.  */
struct swr_v1_corebase_lifecycle_state { uint32_t phase; uint32_t index; };
enum swr_v1_corebase_lifecycle_operation {
    SWR_COREBASE_THREAD_INIT = 1, SWR_COREBASE_THREAD_CLEAN = 2, SWR_COREBASE_CLEAN = 3,
    SWR_COREBASE_FORK = 4, SWR_COREBASE_FORK_EXEC = 5
};
enum swr_v1_corebase_lifecycle_action {
    SWR_COREBASE_DONE = 0, SWR_COREBASE_OBSERVE_BUFFER = 1,
    SWR_COREBASE_ALLOCATE_BUFFER = 2, SWR_COREBASE_BLOCK_SIGNALS = 3,
    SWR_COREBASE_PUBLISH_MAIN = 4, SWR_COREBASE_OBSERVE_TIMER = 5,
    SWR_COREBASE_FREE_TIMER = 6, SWR_COREBASE_OBSERVE_REACTOR = 7,
    SWR_COREBASE_FREE_REACTOR = 8, SWR_COREBASE_DELETE_BUFFER = 9,
    SWR_COREBASE_OBSERVE_HOOK = 10, SWR_COREBASE_DELETE_HOOK = 11,
    SWR_COREBASE_CLEAR_SIGNALS = 12, SWR_COREBASE_CLEAN_THREAD = 13,
    SWR_COREBASE_OBSERVE_LOGGER = 14, SWR_COREBASE_CLOSE_LOGGER = 15,
    SWR_COREBASE_DELETE_LOGGER = 16, SWR_COREBASE_DELETE_POOL = 17,
    SWR_COREBASE_RESET_GLOBAL = 18,
    SWR_COREBASE_OBSERVE_COROUTINE = 19, SWR_COREBASE_REJECT_COROUTINE = 20,
    SWR_COREBASE_OBSERVE_ASYNC = 21, SWR_COREBASE_REJECT_ASYNC = 22,
    SWR_COREBASE_FORK_CALL = 23, SWR_COREBASE_WARN_FORK = 24,
    SWR_COREBASE_SLEEP_RETRY = 25, SWR_COREBASE_REPLACE_POOL = 26,
    SWR_COREBASE_REOPEN_LOGGER = 27, SWR_COREBASE_FREE_FORK_REACTOR = 28,
    SWR_COREBASE_OBSERVE_AFTER_FORK = 29, SWR_COREBASE_CALL_AFTER_FORK = 30,
    SWR_COREBASE_EXEC_CALLBACK = 31, SWR_COREBASE_EXIT_CHILD = 32,
    SWR_COREBASE_FAILED_EXEC = 33,
    SWR_COREBASE_OBSERVE_INITIALIZED = 34, SWR_COREBASE_PUBLISH_INIT = 35,
    SWR_COREBASE_HOST_DEFAULTS = 36, SWR_COREBASE_ALLOCATE_LOGGER = 37,
    SWR_COREBASE_INIT_MAIN_THREAD = 38, SWR_COREBASE_LOG_DEFAULTS = 39,
    SWR_COREBASE_DEFAULT_SOCKETS = 40, SWR_COREBASE_QUERY_RLIMIT = 41,
    SWR_COREBASE_WARN_RLIMIT = 42, SWR_COREBASE_PUBLISH_RLIMIT = 43,
    SWR_COREBASE_TASK_TEMPLATE = 44, SWR_COREBASE_SIGNAL_FD = 45,
    SWR_COREBASE_BUG_MESSAGE = 46,
    SWR_COREBASE_OBSERVE_TASK_BYTE = 47, SWR_COREBASE_WARN_TASK_ABSOLUTE = 48,
    SWR_COREBASE_ACCESS_TASK = 49, SWR_COREBASE_MKDIR_TASK = 50,
    SWR_COREBASE_WARN_TASK_CREATE = 51, SWR_COREBASE_PUBLISH_TASK = 52,
    SWR_COREBASE_OBSERVE_TASK_LENGTH = 53, SWR_COREBASE_WARN_TASK_LONG = 54,
    SWR_COREBASE_REJECT_TASK = 55, SWR_COREBASE_ACCEPT_TASK = 56,
    SWR_COREBASE_QUERY_CPU = 57, SWR_COREBASE_PUBLISH_CPU_ONE = 58,
    SWR_COREBASE_QUERY_CPU_AGAIN = 59
};
uint32_t swr_v1_corebase_lifecycle_next(uint32_t operation,
    struct swr_v1_corebase_lifecycle_state *state, uint64_t observed, uint32_t argument);
/* Dedicated initialization entry: limit is native session-list size.
 * QUERY_CPU observation is sysconf(_SC_NPROCESSORS_ONLN) < 1. Native performs
 * the original one/two sysconf calls and stores the result. QUERY_RLIMIT
 * observation is (uint64_t(uint32_t(rlim_cur))<<1)|1 on success, zero on
 * failure; other observations are booleans. PUBLISH_RLIMIT reads cursor.index.
 * Same exclusive zeroed cursor/effect-after-return contract. */
uint32_t swr_v1_corebase_init_next(struct swr_v1_corebase_lifecycle_state *state,
                                uint64_t observed, uint32_t limit);
/* Task directory: zeroed exclusive cursor; copied observations are native at(0)
 * byte, access>=0 / mkdir success, then freshly published string length.
 * Native owns lock, IO, warning, format/assignment and exception effects.
 * Stop on ACCEPT_TASK/REJECT_TASK/UINT32_MAX; no Rust borrow spans effects. */
uint32_t swr_v1_corebase_task_tmp_next(struct swr_v1_corebase_lifecycle_state *state,
                                    uint64_t observed, uint32_t limit);
enum swr_v1_corebase_hook_add_action_kind {
    SWR_COREBASE_HOOK_CREATE_FRONT = 1,
    SWR_COREBASE_HOOK_CREATE_BACK = 2,
    SWR_COREBASE_HOOK_PUSH_FRONT = 3,
    SWR_COREBASE_HOOK_PUSH_BACK = 4
};
/* Native owns list allocation/publication and Callback copy/insertion effects. */
uint32_t swr_v1_corebase_hook_add_action(uint8_t list_present, int32_t push_back);
/* Random policy: exclusive zeroed per-call cursor, no RNG/fd/object ownership.
 * Run returned effects after Rust returns. Preserve mode/length/range; SYSTEM
 * flags freshly copy cached-fd-ready(1) and full-read(2); BUFFER/APPEND may
 * set FIRST_DRAW_READY(4) when the first native draw already occurred.
 * RETURN reads value; DRAW uses the fixed alphabet bound below. STORE_DRAW stores index/value BEFORE
 * the next draw. STORE_NUL/STORE_DONE store the final byte then terminate.
 * Stop on RETURN/FALLBACK/NUL/DONE/STORE_NUL/STORE_DONE/UINT32_MAX. Native exceptions never cross Rust.
 * Original defined SYSTEM range is max>min with no signed range-width overflow. */
struct swr_v1_corebase_random_state { uint32_t phase; int32_t value; size_t index; };
enum { SWR_COREBASE_RANDOM_DRAW_MAX = 61, SWR_COREBASE_RANDOM_FIRST_DRAW_READY = 4 };
enum swr_v1_corebase_random_mode {
    SWR_COREBASE_RANDOM_SYSTEM = 0, SWR_COREBASE_RANDOM_BUFFER = 1, SWR_COREBASE_RANDOM_APPEND = 2
};
enum swr_v1_corebase_random_action {
    SWR_COREBASE_RANDOM_OPEN = 1, SWR_COREBASE_RANDOM_READ = 2,
    SWR_COREBASE_RANDOM_FALLBACK = 3, SWR_COREBASE_RANDOM_WARN = 4,
    SWR_COREBASE_RANDOM_RETURN = 5, SWR_COREBASE_RANDOM_DRAW = 6,
    SWR_COREBASE_RANDOM_STORE_DRAW = 7, SWR_COREBASE_RANDOM_NUL = 8, SWR_COREBASE_RANDOM_DONE = 9,
    SWR_COREBASE_RANDOM_STORE_NUL = 10, SWR_COREBASE_RANDOM_STORE_DONE = 11
};
uint32_t swr_v1_corebase_random_next(struct swr_v1_corebase_random_state *state,
    uint32_t mode, uint32_t flags, size_t length, uint32_t random, int32_t min, int32_t max);
#ifdef __cplusplus
}
#endif
#endif
