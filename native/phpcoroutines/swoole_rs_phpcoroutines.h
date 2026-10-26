#ifndef SWOOLE_RS_PHPCOROUTINES_H
#define SWOOLE_RS_PHPCOROUTINES_H
#include <stdint.h>
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
enum { SWR_CORO_CONTEXT_ACTIVE, SWR_CORO_CONTEXT_PARENT, SWR_CORO_CONTEXT_FALLBACK, SWR_CORO_CONTEXT_BY_ID };
enum { SWR_CORO_CONTEXT_NONE, SWR_CORO_CONTEXT_CURRENT, SWR_CORO_CONTEXT_LOOKUP, SWR_CORO_CONTEXT_MAIN };
uint32_t swr_v1_phpcoroutines_context_route(uint32_t, int64_t, uint8_t);
enum { SWR_CORO_QUERY_CONTEXT, SWR_CORO_QUERY_PARENT, SWR_CORO_QUERY_STACK };
enum { SWR_CORO_QUERY_DONE, SWR_CORO_QUERY_CURRENT, SWR_CORO_QUERY_BY_ID, SWR_CORO_QUERY_MISSING,
       SWR_CORO_QUERY_CHECK_DESTROYED, SWR_CORO_QUERY_DESTROYED, SWR_CORO_QUERY_HAS_OBJECT,
       SWR_CORO_QUERY_INIT_OBJECT, SWR_CORO_QUERY_PUBLISH, SWR_CORO_QUERY_FALSE, SWR_CORO_QUERY_LONG };
uint32_t swr_v1_phpcoroutines_context_query(uint32_t, uint32_t *, int64_t, int64_t);
typedef struct { uint32_t action; int32_t skip_last; } swr_phpcoroutines_trace_plan;
enum { SWR_CORO_TRACE_DONE, SWR_CORO_TRACE_CID, SWR_CORO_TRACE_SELF, SWR_CORO_TRACE_CONTEXT,
       SWR_CORO_TRACE_MISSING, SWR_CORO_TRACE_SWITCH, SWR_CORO_TRACE_TARGET, SWR_CORO_TRACE_RESTORE,
       SWR_CORO_TRACE_RETURN_PRESENCE, SWR_CORO_TRACE_FALSE };
swr_phpcoroutines_trace_plan swr_v1_phpcoroutines_trace(uint32_t *, int64_t, int64_t, uint8_t);


enum { SWR_CORO_SCHED_CLOCK, SWR_CORO_SCHED_ELAPSED, SWR_CORO_SCHED_ENABLE, SWR_CORO_SCHED_DISABLE, SWR_CORO_SCHED_RECORD };
uint8_t swr_v1_phpcoroutines_scheduler_policy(uint32_t, uint8_t, uint8_t, int64_t, int64_t, uint8_t);
typedef struct { int64_t cid; int64_t current_cid; size_t usage; uint32_t stage; } swr_phpcoroutines_stack_state;
enum { SWR_CORO_STACK_DONE, SWR_CORO_STACK_CID, SWR_CORO_STACK_CONTEXT, SWR_CORO_STACK_MISSING,
       SWR_CORO_STACK_CURRENT, SWR_CORO_STACK_SAVED, SWR_CORO_STACK_BYTES, SWR_CORO_STACK_NEXT };
uint32_t swr_v1_phpcoroutines_stack_step(swr_phpcoroutines_stack_state *, int64_t, size_t);
typedef struct { uint32_t index; uint32_t phase; uint8_t cli; } swr_phpcoroutines_bootstrap_state;
typedef struct { uint32_t action; uint32_t id; const char *name; size_t length; } swr_phpcoroutines_bootstrap_plan;
enum { SWR_CORO_BOOT_DONE, SWR_CORO_BOOT_CLASS, SWR_CORO_BOOT_SHORTNAME, SWR_CORO_BOOT_ALIAS,
       SWR_CORO_BOOT_COPY, SWR_CORO_BOOT_FIXUP, SWR_CORO_BOOT_CONSTANT, SWR_CORO_BOOT_PROPERTY,
       SWR_CORO_BOOT_CLI, SWR_CORO_BOOT_EFFECT };
swr_phpcoroutines_bootstrap_plan swr_v1_phpcoroutines_bootstrap(swr_phpcoroutines_bootstrap_state *, uint32_t, uint8_t, uint8_t);
typedef struct { uint64_t max_num; uint32_t hook_flags; uint8_t preemptive; uint8_t disable_deadlock; } swr_phpcoroutines_config_state;
enum { SWR_CORO_CONFIG_GET_MAX, SWR_CORO_CONFIG_SET_MAX, SWR_CORO_CONFIG_GET_HOOKS,
       SWR_CORO_CONFIG_SET_HOOKS, SWR_CORO_CONFIG_GET_PREEMPTIVE, SWR_CORO_CONFIG_SET_PREEMPTIVE,
       SWR_CORO_CONFIG_GET_DEADLOCK, SWR_CORO_CONFIG_SET_DEADLOCK };
uint64_t swr_v1_phpcoroutines_config(swr_phpcoroutines_config_state *, uint32_t, uint64_t);
typedef struct { int64_t init; int64_t waiting; int64_t running; int64_t end; } swr_phpcoroutines_fiber_states;
enum { SWR_CORO_FIBER_STATUS, SWR_CORO_FIBER_SWITCH, SWR_CORO_FIBER_TRY, SWR_CORO_FIBER_DESTROY };
enum { SWR_CORO_FIBER_DONE, SWR_CORO_FIBER_MAIN, SWR_CORO_FIBER_RUNNING, SWR_CORO_FIBER_STATE,
       SWR_CORO_FIBER_INIT, SWR_CORO_FIBER_SUSPENDED, SWR_CORO_FIBER_DEAD, SWR_CORO_FIBER_FATAL,
       SWR_CORO_FIBER_FROM_STATUS, SWR_CORO_FIBER_TO_STATUS, SWR_CORO_FIBER_NOTIFIED,
       SWR_CORO_FIBER_TEMP_INIT, SWR_CORO_FIBER_NOTIFY, SWR_CORO_FIBER_REFRESH_STATUS,
       SWR_CORO_FIBER_PUBLISH, SWR_CORO_FIBER_FROM_PRESENT, SWR_CORO_FIBER_TO_PRESENT,
       SWR_CORO_FIBER_SWITCH_NOTIFY, SWR_CORO_FIBER_DESTROY_PRESENT,
       SWR_CORO_FIBER_PUBLISH_DEAD, SWR_CORO_FIBER_DESTROY_SWITCH,
       SWR_CORO_FIBER_DESTROY_NOTIFY, SWR_CORO_FIBER_REFRESH_PRESENT,
       SWR_CORO_FIBER_FREE };
uint32_t swr_v1_phpcoroutines_fiber(uint32_t *, uint32_t, int64_t, const swr_phpcoroutines_fiber_states *);
typedef struct { uint32_t phase; int64_t flags; } swr_phpcoroutines_exit_state;
typedef struct { int64_t coroutine; int64_t server; uint32_t unused; uint32_t constant; } swr_phpcoroutines_exit_config;
typedef struct { uint32_t action; int64_t flags; } swr_phpcoroutines_exit_plan;
enum { SWR_CORO_EXIT_DONE, SWR_CORO_EXIT_CURRENT, SWR_CORO_EXIT_SERVER, SWR_CORO_EXIT_SERVER_STARTED,
       SWR_CORO_EXIT_LEGACY_BEGIN, SWR_CORO_EXIT_MODERN_BEGIN, SWR_CORO_EXIT_OPERAND,
       SWR_CORO_EXIT_CONSTANT, SWR_CORO_EXIT_VARIABLE, SWR_CORO_EXIT_NULL, SWR_CORO_EXIT_REFERENCE,
       SWR_CORO_EXIT_UNWRAP, SWR_CORO_EXIT_DUP, SWR_CORO_EXIT_THROW_LEGACY, SWR_CORO_EXIT_FLAGS,
       SWR_CORO_EXIT_LEGACY_STATUS, SWR_CORO_EXIT_MESSAGE, SWR_CORO_EXIT_THROW_MESSAGE,
       SWR_CORO_EXIT_THROW_DEFAULT, SWR_CORO_EXIT_STATUS_STRING, SWR_CORO_EXIT_STATUS_LONG,
       SWR_CORO_EXIT_ORIGINAL, SWR_CORO_EXIT_WRITE, SWR_CORO_EXIT_NATIVE };
swr_phpcoroutines_exit_plan swr_v1_phpcoroutines_exit(swr_phpcoroutines_exit_state *, const swr_phpcoroutines_exit_config *, uint32_t, int64_t);
typedef struct { uint32_t action; int64_t value; } swr_phpcoroutines_control_plan;
enum { SWR_CORO_CONTROL_DONE, SWR_CORO_CONTROL_TASK, SWR_CORO_CONTROL_COROUTINE,
       SWR_CORO_CONTROL_MISSING, SWR_CORO_CONTROL_FALSE, SWR_CORO_CONTROL_EXCEPTION,
       SWR_CORO_CONTROL_CLASS, SWR_CORO_CONTROL_CANCELED, SWR_CORO_CONTROL_ALLOCATE,
       SWR_CORO_CONTROL_PREVIOUS, SWR_CORO_CONTROL_LINK_PREVIOUS, SWR_CORO_CONTROL_SAVE_EXECUTOR,
       SWR_CORO_CONTROL_FILE, SWR_CORO_CONTROL_LINE, SWR_CORO_CONTROL_RESTORE_EXECUTOR,
       SWR_CORO_CONTROL_CANCEL_IGNORE, SWR_CORO_CONTROL_TRUE, SWR_CORO_CONTROL_CANCEL_RESULT,
       SWR_CORO_CONTROL_CID, SWR_CORO_CONTROL_TIMER, SWR_CORO_CONTROL_THROW_TIMEOUT, SWR_CORO_CONTROL_RELEASE_EXCEPTION,
       SWR_CORO_CONTROL_CLEAR_EXCEPTION, SWR_CORO_CONTROL_FATAL_EXCEPTION,
       SWR_CORO_CONTROL_CORE_COUNT, SWR_CORO_CONTROL_FATAL_PRESENCE,
       SWR_CORO_CONTROL_REACTOR_PRESENCE, SWR_CORO_CONTROL_REACTOR_BAILOUT,
       SWR_CORO_CONTROL_LIBRARY_PRESENCE, SWR_CORO_CONTROL_LIBRARY_DIAGNOSTIC,
       SWR_CORO_CONTROL_PRINT_DIAGNOSTIC, SWR_CORO_CONTROL_CLOSE_PRESENCE,
       SWR_CORO_CONTROL_CLOSE_CALLBACK, SWR_CORO_CONTROL_CLOSE_FREE, SWR_CORO_CONTROL_REQUEST_SHUTDOWN,
       SWR_CORO_CONTROL_CALLER_FUNCTION, SWR_CORO_CONTROL_CALLER_NAME,
       SWR_CORO_CONTROL_CALLER_DESTRUCTOR, SWR_CORO_CONTROL_CREATE_FATAL,
       SWR_CORO_CONTROL_CREATE_EFFECT, SWR_CORO_CONTROL_CREATE_LONG,
       SWR_CORO_CONTROL_AUTOLOAD_PRESENCE, SWR_CORO_CONTROL_AUTOLOAD_DESTROY,
       SWR_CORO_CONTROL_AUTOLOAD_FREE, SWR_CORO_CONTROL_AUTOLOAD_CLEAR,
       SWR_CORO_CONTROL_REQUEST_STOP, SWR_CORO_CONTROL_REACTOR_STOP,
       SWR_CORO_CONTROL_REACTOR_BAILOUT_PUBLISH, SWR_CORO_CONTROL_ZEND_BAILOUT };
enum { SWR_CORO_CONTROL_CANCEL, SWR_CORO_CONTROL_THROW, SWR_CORO_CONTROL_TIME_LIMIT,
       SWR_CORO_CONTROL_TIMEOUT_CALLBACK, SWR_CORO_CONTROL_CATCH,
       SWR_CORO_CONTROL_CATCH_RECOVER, SWR_CORO_CONTROL_DEADLOCK,
       SWR_CORO_CONTROL_CLOSE, SWR_CORO_CONTROL_CREATE_FRONTEND,
       SWR_CORO_CONTROL_REQUEST_SHUTDOWN_FRONTEND, SWR_CORO_CONTROL_BAILOUT };
swr_phpcoroutines_control_plan swr_v1_phpcoroutines_control(uint32_t *, uint32_t, int64_t, double);
/* Same ten-byte readable window required by pinned memcmp; no name length/scan. */
uint8_t swr_v1_phpcoroutines_create_destructor(const uint8_t *);
typedef struct { int64_t success, false_tag, php_resolver; } swr_phpcoroutines_scheduler_constants;
enum { SWR_CORO_SCHED_CONTROL_CALLBACK, SWR_CORO_SCHED_CONTROL_RESOLVER,
       SWR_CORO_SCHED_CONTROL_SHUTDOWN, SWR_CORO_SCHED_CONTROL_OPTIONS };
enum { SWR_CORO_SCHED_CONTROL_DONE, SWR_CORO_SCHED_CONTROL_CALL, SWR_CORO_SCHED_CONTROL_FATAL,
       SWR_CORO_SCHED_CONTROL_EXCEPTION_PRESENCE, SWR_CORO_SCHED_CONTROL_EXCEPTION,
       SWR_CORO_SCHED_CONTROL_RESULT, SWR_CORO_SCHED_CONTROL_TRUE, SWR_CORO_SCHED_CONTROL_FALSE,
       SWR_CORO_SCHED_CONTROL_RESOLVER_DTOR, SWR_CORO_SCHED_CONTROL_RESOLVER_FREE,
       SWR_CORO_SCHED_CONTROL_KEEP, SWR_CORO_SCHED_CONTROL_REMOVE, SWR_CORO_SCHED_CONTROL_RESOLVERS,
       SWR_CORO_SCHED_CONTROL_CACHE_PRESENCE, SWR_CORO_SCHED_CONTROL_CACHE_FREE,
       SWR_CORO_SCHED_CONTROL_CACHE_CLEAR, SWR_CORO_SCHED_CONTROL_OPTIONS_PRESENCE,
       SWR_CORO_SCHED_CONTROL_OPTIONS_DUP };
uint32_t swr_v1_phpcoroutines_scheduler_control(uint32_t *, uint32_t, int64_t,
    const swr_phpcoroutines_scheduler_constants *);
typedef struct { uint8_t running; } swr_phpcoroutines_interrupt_state;
typedef struct { uint32_t action; uint64_t value; } swr_phpcoroutines_interrupt_plan;
enum { SWR_CORO_INTERRUPT_START, SWR_CORO_INTERRUPT_STOP, SWR_CORO_INTERRUPT_CHILD, SWR_CORO_INTERRUPT_RECORD };
enum { SWR_CORO_INTERRUPT_DONE, SWR_CORO_INTERRUPT_VM_CAPTURE, SWR_CORO_INTERRUPT_THREAD_START,
       SWR_CORO_INTERRUPT_THREAD_JOIN, SWR_CORO_INTERRUPT_VM_STORE, SWR_CORO_INTERRUPT_SLEEP,
       SWR_CORO_INTERRUPT_CLOCK };
swr_phpcoroutines_interrupt_plan swr_v1_phpcoroutines_interrupt(swr_phpcoroutines_interrupt_state *, uint32_t *, uint32_t, uint8_t);
typedef struct { uint32_t stage; uintptr_t reserve; } swr_phpcoroutines_bounds_state;
typedef struct { uint32_t action; uintptr_t reserve; } swr_phpcoroutines_bounds_plan;
enum { SWR_CORO_BOUNDS_LIMIT, SWR_CORO_BOUNDS_BASE };
enum { SWR_CORO_BOUNDS_NULL = 1, SWR_CORO_BOUNDS_RESERVE, SWR_CORO_BOUNDS_HAS_CO,
       SWR_CORO_BOUNDS_LIMIT_POINTER, SWR_CORO_BOUNDS_BASE_POINTER };
swr_phpcoroutines_bounds_plan swr_v1_phpcoroutines_bounds(swr_phpcoroutines_bounds_state *, uint32_t, uint8_t, uintptr_t);
typedef struct { int64_t count, index; uint8_t pending; } swr_phpcoroutines_repeat_state;
uint8_t swr_v1_phpcoroutines_repeat(swr_phpcoroutines_repeat_state *);
enum { SWR_CORO_LIFECYCLE_DONE,
       SWR_CORO_LIFECYCLE_CTOR_INIT,
       SWR_CORO_LIFECYCLE_CTOR_FIBER,
       SWR_CORO_LIFECYCLE_CTOR_FIBER_INIT,
       SWR_CORO_LIFECYCLE_CTOR_FIBER_NONE,
       SWR_CORO_LIFECYCLE_CTOR_VM,
       SWR_CORO_LIFECYCLE_CTOR_CALLABLE,
       SWR_CORO_LIFECYCLE_CTOR_CALLABLE_COPY,
       SWR_CORO_LIFECYCLE_CTOR_CALLABLE_UNDEF,
       SWR_CORO_LIFECYCLE_CTOR_PERSIST,
       SWR_CORO_LIFECYCLE_CTOR_RETURN,
       SWR_CORO_LIFECYCLE_MAIN_TRACE,
       SWR_CORO_LIFECYCLE_MAIN_HOOK,
       SWR_CORO_LIFECYCLE_MAIN_HOOK_CALL,
       SWR_CORO_LIFECYCLE_MAIN_FIBER,
       SWR_CORO_LIFECYCLE_MAIN_USER_FUNCTION,
       SWR_CORO_LIFECYCLE_MAIN_NOTIFY,
       SWR_CORO_LIFECYCLE_MAIN_INVOKE,
       SWR_CORO_LIFECYCLE_MAIN_DEFER,
       SWR_CORO_LIFECYCLE_MAIN_DEFER_DRAIN,
       SWR_CORO_LIFECYCLE_DEFER_VALUE,
       SWR_CORO_LIFECYCLE_DEFER_PARAMS,
       SWR_CORO_LIFECYCLE_DEFER_INVOKE,
       SWR_CORO_LIFECYCLE_DEFER_WARN,
       SWR_CORO_LIFECYCLE_DEFER_EXCEPTION,
       SWR_CORO_LIFECYCLE_DEFER_BAILOUT,
       SWR_CORO_LIFECYCLE_DEFER_CLEAN,
       SWR_CORO_LIFECYCLE_DESTROY_HOOK,
       SWR_CORO_LIFECYCLE_DESTROY_HOOK_CALL,
       SWR_CORO_LIFECYCLE_DESTROY_OUTPUT,
       SWR_CORO_LIFECYCLE_DESTROY_SAVE_HEADERS,
       SWR_CORO_LIFECYCLE_DESTROY_ACTIVE,
       SWR_CORO_LIFECYCLE_DESTROY_END_OUTPUT,
       SWR_CORO_LIFECYCLE_DESTROY_RESTART_OUTPUT,
       SWR_CORO_LIFECYCLE_DESTROY_DEFER,
       SWR_CORO_LIFECYCLE_DESTROY_DEFER_DRAIN,
       SWR_CORO_LIFECYCLE_DESTROY_OBJECT,
       SWR_CORO_LIFECYCLE_DESTROY_OBJECT_RELEASE,
       SWR_CORO_LIFECYCLE_DESTROY_RESOURCES,
       SWR_CORO_LIFECYCLE_POST_DESTROY,
       SWR_CORO_LIFECYCLE_POST_EXCEPTION,
       SWR_CORO_LIFECYCLE_POST_BAILOUT,
       SWR_CORO_LIFECYCLE_REGISTER_CONTEXT,
       SWR_CORO_LIFECYCLE_REGISTER_OWNER,
       SWR_CORO_LIFECYCLE_REGISTER_ALLOCATE,
       SWR_CORO_LIFECYCLE_REGISTER_PUSH };
enum { SWR_CORO_LIFECYCLE_CTOR, SWR_CORO_LIFECYCLE_MAIN, SWR_CORO_LIFECYCLE_DEFER, SWR_CORO_LIFECYCLE_DESTROY, SWR_CORO_LIFECYCLE_POST, SWR_CORO_LIFECYCLE_REGISTER };
uint32_t swr_v1_phpcoroutines_lifecycle(uint32_t *, uint32_t, int64_t);
/* Rust-built step tables: native code steps with a load instead of a call. */
typedef struct { uint8_t action, next; } swr_phpcoroutines_step;
extern const swr_phpcoroutines_step swr_v1_phpcoroutines_lifecycle_table[6 * 16 * 2];
static inline uint32_t swr_coro_lifecycle_next(uint32_t *stage, uint32_t kind, int64_t observation) {
    if (kind >= 6 || *stage >= 16) {
        return SWR_CORO_LIFECYCLE_DONE;
    }
    const swr_phpcoroutines_step step = swr_v1_phpcoroutines_lifecycle_table[(kind * 16 + *stage) * 2 + (observation != 0)];
    *stage = step.next;
    return step.action;
}
typedef struct swr_phpcoroutines_join_owner swr_phpcoroutines_join_owner;
swr_phpcoroutines_join_owner *swr_v1_phpcoroutines_join_try_new(void);
uint8_t swr_v1_phpcoroutines_join_clone(const swr_phpcoroutines_join_owner *);
void swr_v1_phpcoroutines_join_drop(const swr_phpcoroutines_join_owner *);
uint8_t swr_v1_phpcoroutines_join_try_insert(const swr_phpcoroutines_join_owner *, uintptr_t);
uint8_t swr_v1_phpcoroutines_join_erase_empty(const swr_phpcoroutines_join_owner *, uintptr_t);
uint8_t swr_v1_phpcoroutines_join_empty(const swr_phpcoroutines_join_owner *);
uint8_t swr_v1_phpcoroutines_join_next(const swr_phpcoroutines_join_owner *, size_t *, uintptr_t *);
void swr_v1_phpcoroutines_join_release_membership(const swr_phpcoroutines_join_owner *);
void swr_v1_phpcoroutines_join_cancel(const swr_phpcoroutines_join_owner *);
uint8_t swr_v1_phpcoroutines_join_can_resume(const swr_phpcoroutines_join_owner *);
enum { SWR_CORO_TRANSFER_SAVE_VM, SWR_CORO_TRANSFER_RESTORE_VM,
       SWR_CORO_TRANSFER_SAVE_OUTPUT, SWR_CORO_TRANSFER_RESTORE_OUTPUT,
       SWR_CORO_TRANSFER_SAVE_BASIC, SWR_CORO_TRANSFER_RESTORE_BASIC,
       SWR_CORO_TRANSFER_SAVE_CONTEXT, SWR_CORO_TRANSFER_RESTORE_CONTEXT,
       SWR_CORO_TRANSFER_ON_YIELD, SWR_CORO_TRANSFER_ON_RESUME,
       SWR_CORO_TRANSFER_INTERRUPT_RESUME, SWR_CORO_TRANSFER_INTERRUPT_FUNCTION,
       SWR_CORO_TRANSFER_SAVE_VM_METADATA, SWR_CORO_TRANSFER_RESTORE_VM_METADATA };
enum { SWR_CORO_TRANSFER_DONE, SWR_CORO_TRANSFER_VM, SWR_CORO_TRANSFER_SILENCE_PRESENCE,
       SWR_CORO_TRANSFER_SILENCE, SWR_CORO_TRANSFER_STACK_LIMIT,
       SWR_CORO_TRANSFER_OUTPUT_PRESENCE, SWR_CORO_TRANSFER_OUTPUT,
       SWR_CORO_TRANSFER_CLEAR_OUTPUT, SWR_CORO_TRANSFER_LOCK_PRESENCE,
       SWR_CORO_TRANSFER_LOCK, SWR_CORO_TRANSFER_SERIALIZE_PRESENCE,
       SWR_CORO_TRANSFER_SERIALIZE, SWR_CORO_TRANSFER_UNSERIALIZE_PRESENCE,
       SWR_CORO_TRANSFER_UNSERIALIZE, SWR_CORO_TRANSFER_CALL_VM,
       SWR_CORO_TRANSFER_CALL_OUTPUT, SWR_CORO_TRANSFER_CALL_BASIC,
       SWR_CORO_TRANSFER_FIBER, SWR_CORO_TRANSFER_SAVE, SWR_CORO_TRANSFER_RESTORE,
       SWR_CORO_TRANSFER_RECORD, SWR_CORO_TRANSFER_CALLBACK_PRESENCE,
       SWR_CORO_TRANSFER_CALLBACK, SWR_CORO_TRANSFER_TRACE,
       SWR_CORO_TRANSFER_CO_PRESENCE, SWR_CORO_TRANSFER_CO_ENDED, SWR_CORO_TRANSFER_RESUME,
       SWR_CORO_TRANSFER_TASK_PRESENCE, SWR_CORO_TRANSFER_TASK_CO_PRESENCE,
       SWR_CORO_TRANSFER_SCHEDULABLE, SWR_CORO_TRANSFER_DEFER, SWR_CORO_TRANSFER_YIELD };
uint32_t swr_v1_phpcoroutines_transfer(uint32_t *, uint32_t, uint8_t, uint8_t);
extern const swr_phpcoroutines_step swr_v1_phpcoroutines_transfer_table[14 * 8 * 4];
static inline uint32_t swr_coro_transfer_next(uint32_t *stage, uint32_t kind, uint8_t observation, uint8_t stack_limit) {
    if (kind >= 14 || *stage >= 8) {
        return SWR_CORO_TRANSFER_DONE;
    }
    const swr_phpcoroutines_step step =
        swr_v1_phpcoroutines_transfer_table[((kind * 8 + *stage) * 2 + (observation != 0)) * 2 + (stack_limit != 0)];
    *stage = step.next;
    return step.action;
}
struct swr_phpcoroutines_scheduler_queue;
typedef struct { uint8_t started; } swr_phpcoroutines_scheduler_phase;
typedef swr_phpcoroutines_scheduler_phase swr_phpcoroutines_activation_state;
typedef struct { int value; } swr_phpcoroutines_error_cell;
typedef struct { long value; } swr_phpcoroutines_parent_cell;
typedef struct { int64_t value; } swr_phpcoroutines_clock_cell;
typedef struct {
    swr_phpcoroutines_scheduler_phase *silence, *scheduler;
    swr_phpcoroutines_error_cell *original, *temporary;
    swr_phpcoroutines_scheduler_phase *notified;
    swr_phpcoroutines_parent_cell *parent;
    swr_phpcoroutines_clock_cell *clock;
} swr_phpcoroutines_context_cells;
typedef struct { uint32_t action; int64_t value; } swr_phpcoroutines_metadata_plan;
enum { SWR_CORO_METADATA_BEGIN, SWR_CORO_METADATA_END, SWR_CORO_METADATA_SAVE,
       SWR_CORO_METADATA_RESTORE, SWR_CORO_METADATA_ENABLE, SWR_CORO_METADATA_DISABLE,
       SWR_CORO_METADATA_SCHEDULABLE, SWR_CORO_METADATA_PARENT, SWR_CORO_METADATA_SET_PARENT,
       SWR_CORO_METADATA_RECORD, SWR_CORO_METADATA_FIBER, SWR_CORO_METADATA_INIT_SCHEDULER,
       SWR_CORO_METADATA_INIT_FIBER };
enum { SWR_CORO_METADATA_DONE, SWR_CORO_METADATA_READ_ERROR, SWR_CORO_METADATA_WRITE_ERROR,
       SWR_CORO_METADATA_CLOCK, SWR_CORO_METADATA_FALSE, SWR_CORO_METADATA_TRUE };
swr_phpcoroutines_metadata_plan swr_v1_phpcoroutines_metadata(uint32_t *, uint32_t,
    const swr_phpcoroutines_context_cells *, int64_t, uint8_t);

enum { SWR_CORO_SCHED_PHASE_READ, SWR_CORO_SCHED_PHASE_START, SWR_CORO_SCHED_PHASE_STOP };
uint8_t swr_v1_phpcoroutines_scheduler_phase(swr_phpcoroutines_scheduler_phase *, uint32_t);
typedef struct swr_phpcoroutines_scheduler_queue swr_phpcoroutines_scheduler_queue;
typedef struct {
    uintptr_t token;
    uint64_t repetitions;
} swr_phpcoroutines_scheduler_task;
typedef struct { uint32_t next, output; } swr_phpcoroutines_method_cursor;
typedef struct { uint32_t done, slot, handler, flags; const char *name; } swr_phpcoroutines_method_plan;
swr_phpcoroutines_method_plan swr_v1_phpcoroutines_method(swr_phpcoroutines_method_cursor *, uint32_t, uint8_t, uint32_t, uint32_t);
enum { SWR_CORO_SCHED_SLOT_ABSENT, SWR_CORO_SCHED_SLOT_EMPTY, SWR_CORO_SCHED_SLOT_TASK };
uint8_t swr_v1_phpcoroutines_scheduler_prepare_slot(swr_phpcoroutines_scheduler_queue **);
uint8_t swr_v1_phpcoroutines_scheduler_try_push_slot(swr_phpcoroutines_scheduler_queue **, uintptr_t, int64_t);
uint32_t swr_v1_phpcoroutines_scheduler_next_slot(swr_phpcoroutines_scheduler_queue **, swr_phpcoroutines_scheduler_task *);
void swr_v1_phpcoroutines_scheduler_drop_slot(swr_phpcoroutines_scheduler_queue **);
swr_phpcoroutines_scheduler_queue *swr_v1_phpcoroutines_scheduler_new(void);
void swr_v1_phpcoroutines_scheduler_push(swr_phpcoroutines_scheduler_queue *, uintptr_t, int64_t);
uint8_t swr_v1_phpcoroutines_scheduler_pop(swr_phpcoroutines_scheduler_queue *, swr_phpcoroutines_scheduler_task *);
void swr_v1_phpcoroutines_scheduler_drop(swr_phpcoroutines_scheduler_queue *);
typedef struct swr_phpcoroutines_autoload_queue swr_phpcoroutines_autoload_queue;
swr_phpcoroutines_autoload_queue *swr_v1_phpcoroutines_autoload_new(void);
void swr_v1_phpcoroutines_autoload_push(swr_phpcoroutines_autoload_queue *, uintptr_t);
uint8_t swr_v1_phpcoroutines_autoload_pop(swr_phpcoroutines_autoload_queue *, uintptr_t *);
void swr_v1_phpcoroutines_autoload_drop(swr_phpcoroutines_autoload_queue *);
enum {
    SWR_CORO_CREATE_LIMIT = 1, SWR_CORO_CREATE_HANDLER, SWR_CORO_CREATE_INVALID_CACHE,
    SWR_CORO_CREATE_TYPE, SWR_CORO_CREATE_INVALID_TYPE, SWR_CORO_CREATE_ACTIVE,
    SWR_CORO_CREATE_ACTIVATE, SWR_CORO_CREATE_READY
};
uint32_t swr_v1_phpcoroutines_create(uint32_t *, uint64_t, uint64_t, uint8_t, uint8_t);
typedef struct { uint32_t index; uint32_t stage; } swr_phpcoroutines_option_state;
typedef struct { uint32_t action; const char *key; size_t key_length; int64_t value; } swr_phpcoroutines_option_plan;
enum {
    SWR_CORO_OPTION_DONE, SWR_CORO_OPTION_LOOKUP, SWR_CORO_OPTION_GET_MAX,
    SWR_CORO_OPTION_SET_MAX, SWR_CORO_OPTION_DEADLOCK, SWR_CORO_OPTION_HOOKS,
    SWR_CORO_OPTION_PREEMPTIVE, SWR_CORO_OPTION_STACK, SWR_CORO_OPTION_CHECK_RESOLVERS,
    SWR_CORO_OPTION_RESOLVERS, SWR_CORO_OPTION_WARN_RESOLVERS, SWR_CORO_OPTION_HAS_OPTIONS,
    SWR_CORO_OPTION_MERGE, SWR_CORO_OPTION_DUP
};
swr_phpcoroutines_option_plan swr_v1_phpcoroutines_options(swr_phpcoroutines_option_state *, int64_t, int64_t);
typedef struct {
    int32_t lock;
    int32_t append_mask;
    int32_t base_open;
    int32_t append_open;
    int32_t truncate_open;
} swr_phpcoroutines_file_config;
typedef struct {
    uint8_t accepted;
    int32_t lock;
    int32_t open;
} swr_phpcoroutines_file_plan;
swr_phpcoroutines_file_plan swr_v1_phpcoroutines_system_file(uint8_t, int64_t, const swr_phpcoroutines_file_config *);
uint8_t swr_v1_phpcoroutines_system_sleep(double, double);
enum { SWR_CORO_ADDRESS_READY, SWR_CORO_ADDRESS_EMPTY, SWR_CORO_ADDRESS_FAMILY };
uint32_t swr_v1_phpcoroutines_system_address(size_t, int64_t, int64_t, int64_t);
enum { SWR_CORO_RESULT_SLEEP, SWR_CORO_RESULT_READ, SWR_CORO_RESULT_WRITE,
       SWR_CORO_RESULT_HOST, SWR_CORO_RESULT_ADDRINFO, SWR_CORO_RESULT_STATVFS,
       SWR_CORO_RESULT_EXEC, SWR_CORO_RESULT_WAIT, SWR_CORO_RESULT_SIGNAL, SWR_CORO_RESULT_EVENT };
enum { SWR_CORO_RESULT_DONE, SWR_CORO_RESULT_FALSE, SWR_CORO_RESULT_BOOL, SWR_CORO_RESULT_LONG,
       SWR_CORO_RESULT_STRING, SWR_CORO_RESULT_ARRAY, SWR_CORO_RESULT_ITEM, SWR_CORO_RESULT_FIELD,
       SWR_CORO_RESULT_BUFFER, SWR_CORO_RESULT_WAIT_ANY, SWR_CORO_RESULT_WAIT_PID,
       SWR_CORO_RESULT_WARN_BUSY, SWR_CORO_RESULT_WARN_INVALID, SWR_CORO_RESULT_BUSY,
       SWR_CORO_RESULT_INVALID, SWR_CORO_RESULT_ERRNO, SWR_CORO_RESULT_EVENT_WAIT,
       SWR_CORO_RESULT_BAD_FD };
typedef struct { size_t index; uint8_t started; } swr_phpcoroutines_result_state;
typedef struct { uint32_t action; const char *key; size_t index; int64_t value; } swr_phpcoroutines_result_plan;
swr_phpcoroutines_result_plan swr_v1_phpcoroutines_system_complete(uint32_t, swr_phpcoroutines_result_state *, int64_t, size_t);

typedef struct { uint32_t index; uint8_t zero_async; } swr_phpcoroutines_stats_state;
typedef struct { uint32_t action; const char *key; size_t key_length; uint8_t zero; } swr_phpcoroutines_stats_plan;
enum { SWR_CORO_STATS_DONE, SWR_CORO_STATS_EVENT, SWR_CORO_STATS_SIGNAL, SWR_CORO_STATS_ASYNC,
       SWR_CORO_STATS_AIO_TASK, SWR_CORO_STATS_AIO_WORKER, SWR_CORO_STATS_AIO_QUEUE, SWR_CORO_STATS_STACK,
       SWR_CORO_STATS_COUNT, SWR_CORO_STATS_PEAK, SWR_CORO_STATS_LAST, SWR_CORO_STATS_IOURING,
       SWR_CORO_STATS_IO_TASK, SWR_CORO_STATS_IO_SQ, SWR_CORO_STATS_IO_WAITING };
swr_phpcoroutines_stats_plan swr_v1_phpcoroutines_stats(swr_phpcoroutines_stats_state *, uint8_t, uint8_t);
typedef struct { uint32_t stage; uint8_t created; } swr_phpcoroutines_configure_state;
typedef struct { uint32_t action; const char *key; size_t key_length; } swr_phpcoroutines_configure_plan;
enum { SWR_CORO_CONFIG_DONE, SWR_CORO_CONFIG_GLOBAL, SWR_CORO_CONFIG_COROUTINE,
       SWR_CORO_CONFIG_LOOKUP_NONNULL, SWR_CORO_CONFIG_EXPIRE, SWR_CORO_CONFIG_CAPACITY,
       SWR_CORO_CONFIG_LOOKUP_ANY, SWR_CORO_CONFIG_HAS_CACHE, SWR_CORO_CONFIG_FREE,
       SWR_CORO_CONFIG_CREATE, SWR_CORO_CONFIG_PUBLISH, SWR_CORO_CONFIG_HAS_REACTOR,
       SWR_CORO_CONFIG_INSTALL, SWR_CORO_CONFIG_REMOVE, SWR_CORO_CONFIG_CLEAR };
swr_phpcoroutines_configure_plan swr_v1_phpcoroutines_configure(swr_phpcoroutines_configure_state *, uint8_t);
typedef struct { uintptr_t identity; } swr_phpcoroutines_scheduler_callback_owner;
typedef struct { swr_phpcoroutines_configure_plan plan; uintptr_t identity; } swr_phpcoroutines_owned_configure_plan;
enum { SWR_CORO_CALLBACK_ASSERT = 18 };
typedef struct { uint32_t stage; uint8_t asserted; } swr_phpcoroutines_callback_control_state;
typedef struct { uint32_t action; uintptr_t identity; } swr_phpcoroutines_callback_control_plan;
swr_phpcoroutines_owned_configure_plan swr_v1_phpcoroutines_configure_owned(swr_phpcoroutines_configure_state *, swr_phpcoroutines_scheduler_callback_owner *, uint8_t, uintptr_t);
swr_phpcoroutines_callback_control_plan swr_v1_phpcoroutines_callback_control(swr_phpcoroutines_callback_control_state *, swr_phpcoroutines_scheduler_callback_owner *, uint32_t, int64_t, const swr_phpcoroutines_scheduler_constants *);

enum { SWR_CORO_ACTIVATE_DONE, SWR_CORO_ACTIVATE_ACTIVE, SWR_CORO_ACTIVATE_LIBRARY,
       SWR_CORO_ACTIVATE_LIBRARY_BOOL, SWR_CORO_ACTIVATE_LOAD, SWR_CORO_ACTIVATE_REACTOR,
       SWR_CORO_ACTIVATE_GLOBAL_PREEMPT, SWR_CORO_ACTIVATE_LOCAL_PREEMPT,
       SWR_CORO_ACTIVATE_INTERRUPT, SWR_CORO_ACTIVATE_MAIN, SWR_CORO_ACTIVATE_HOOK_FLAGS,
       SWR_CORO_ACTIVATE_HOOKS, SWR_CORO_ACTIVATE_UNSAFE, SWR_CORO_ACTIVATE_PUBLISH };
uint32_t swr_v1_phpcoroutines_activation(uint32_t *, uint8_t);
enum { SWR_CORO_AUTOLOAD_NULL, SWR_CORO_AUTOLOAD_CURRENT, SWR_CORO_AUTOLOAD_DIRECT,
       SWR_CORO_AUTOLOAD_DELETE, SWR_CORO_AUTOLOAD_INIT, SWR_CORO_AUTOLOAD_LOOKUP,
       SWR_CORO_AUTOLOAD_RECURSION, SWR_CORO_AUTOLOAD_WAITER, SWR_CORO_AUTOLOAD_OWNER };
uint32_t swr_v1_phpcoroutines_autoload_policy(uint32_t *, uint8_t);
swr_phpcoroutines_scheduler_queue *swr_v1_phpcoroutines_scheduler_try_new(void);
uint8_t swr_v1_phpcoroutines_scheduler_try_push(swr_phpcoroutines_scheduler_queue *, uintptr_t, int64_t);
swr_phpcoroutines_autoload_queue *swr_v1_phpcoroutines_autoload_try_new(void);
swr_phpcoroutines_autoload_queue *swr_v1_phpcoroutines_autoload_owner_try_new(uintptr_t);
uint8_t swr_v1_phpcoroutines_autoload_is_owner(const swr_phpcoroutines_autoload_queue *, uintptr_t);
uint8_t swr_v1_phpcoroutines_autoload_try_push(swr_phpcoroutines_autoload_queue *, uintptr_t);
typedef struct swr_phpcoroutines_defer_queue swr_phpcoroutines_defer_queue;
swr_phpcoroutines_defer_queue *swr_v1_phpcoroutines_defer_new(void);
uint8_t swr_v1_phpcoroutines_defer_push(swr_phpcoroutines_defer_queue *, uintptr_t);
uint8_t swr_v1_phpcoroutines_defer_pop(swr_phpcoroutines_defer_queue *, uintptr_t *);
void swr_v1_phpcoroutines_defer_drop(swr_phpcoroutines_defer_queue *);
typedef struct swr_phpcoroutines_yield_registry swr_phpcoroutines_yield_registry;
uint8_t swr_v1_phpcoroutines_yield_registry_try_put(swr_phpcoroutines_yield_registry **, int64_t, uintptr_t);
void swr_v1_phpcoroutines_yield_registry_put(swr_phpcoroutines_yield_registry **, int64_t, uintptr_t);
uint8_t swr_v1_phpcoroutines_yield_registry_take(swr_phpcoroutines_yield_registry *, int64_t, uintptr_t *);
void swr_v1_phpcoroutines_yield_registry_erase(swr_phpcoroutines_yield_registry *, int64_t);
void swr_v1_phpcoroutines_yield_registry_drop(swr_phpcoroutines_yield_registry *);
void swr_v1_phpcoroutines_yield_put(int64_t, uintptr_t);
uint8_t swr_v1_phpcoroutines_yield_take(int64_t, uintptr_t *);
void swr_v1_phpcoroutines_yield_erase(int64_t);
#ifdef __cplusplus
}
#endif
#endif
