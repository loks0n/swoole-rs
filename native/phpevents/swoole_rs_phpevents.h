#ifndef SWOOLE_RS_PHPEVENTS_H
#define SWOOLE_RS_PHPEVENTS_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Inline opaque identity, pointer size/alignment; never a Zend/Callable payload.
 * Seed is write-only. Calls receive separate cells, never EventObject itself. */
typedef struct SwrPhpEventCallback { uintptr_t identity; } SwrPhpEventCallback;
enum SwrPhpEventCallbackMode {
    SWR_EVENT_CALLBACK_SEED=0, SWR_EVENT_CALLBACK_READ=1,
    SWR_EVENT_CALLBACK_WRITE=2, SWR_EVENT_CALLBACK_FREE=3
};
/* FREE returns1 for first destruction,2 for last: no reentry after last.
 * WRITE is observed freshly
 * after READ destruction. No slot clear is introduced. READ/WRITE return2. */
uint32_t swr_v1_phpevents_callbacks(uint32_t *phase, uint32_t mode,
    SwrPhpEventCallback *readable, SwrPhpEventCallback *writable,
    uintptr_t new_read, uintptr_t new_write, uintptr_t *identity);
/* Existing update actions, with persistent pair checks/publications internal.
 * Native constructs payloads, defers returned identity and performs backend work
 * only after return. A publication follows the completed Native deferral. */
uint32_t swr_v1_phpevents_update_owned(uint32_t *phase, int64_t events,
    int64_t observation, SwrPhpEventCallback *readable, SwrPhpEventCallback *writable,
    uintptr_t new_read, uintptr_t new_write, uintptr_t *identity);
enum SwrPhpEventInitAction {
    SWR_EVENT_INIT_ERROR=0, SWR_EVENT_INIT_OK=1, SWR_EVENT_INIT_CLI=2,
    SWR_EVENT_INIT_SERVER=3, SWR_EVENT_INIT_TASK_WORKER=4,
    SWR_EVENT_INIT_TASK_COROUTINE=5, SWR_EVENT_INIT_MANAGER=6,
    SWR_EVENT_INIT_REACTOR=7, SWR_EVENT_INIT_TRACE=8, SWR_EVENT_INIT_CREATE=9,
    SWR_EVENT_INIT_REGISTER_SHUTDOWN=10, SWR_EVENT_INIT_FRESH_REACTOR=11,
    SWR_EVENT_INIT_USER_CONDITION=12, SWR_EVENT_INIT_HAS_CONDITION=13,
    SWR_EVENT_INIT_SET_CONDITION=14, SWR_EVENT_INIT_WARN_CLI=15,
    SWR_EVENT_INIT_WARN_TASK=16, SWR_EVENT_INIT_WARN_MANAGER=17,
    SWR_EVENT_INIT_WARN_CREATE=18
};
uint32_t swr_v1_phpevents_reactor_init(uint32_t *phase, int64_t observation);
enum SwrPhpEventHandlerAction {
    SWR_EVENT_HANDLERS_DONE=0, SWR_EVENT_HANDLERS_CHECK_REACTOR=1,
    SWR_EVENT_HANDLERS_OBSERVE_READ=2, SWR_EVENT_HANDLERS_READ=3,
    SWR_EVENT_HANDLERS_WRITE=4, SWR_EVENT_HANDLERS_ERROR=5
};
uint32_t swr_v1_phpevents_handlers(uint32_t *phase, uint8_t observation);
enum SwrPhpEventLoopMode {
    SWR_EVENT_LOOP_WAIT=0, SWR_EVENT_LOOP_EXIT=1,
    SWR_EVENT_LOOP_DISPATCH=2, SWR_EVENT_LOOP_RSHUTDOWN=3
};
enum SwrPhpEventLoopAction {
    SWR_EVENT_LOOP_DONE=0, SWR_EVENT_LOOP_FALSE=1, SWR_EVENT_LOOP_TRUE=2,
    SWR_EVENT_LOOP_FATAL=3, SWR_EVENT_LOOP_REACTOR=4,
    SWR_EVENT_LOOP_IN_COROUTINE=5, SWR_EVENT_LOOP_IF_EXIT=6,
    SWR_EVENT_LOOP_BAILOUT=7, SWR_EVENT_LOOP_PREPARE_FLAGS=8,
    SWR_EVENT_LOOP_WAIT_NATIVE=9, SWR_EVENT_LOOP_WARN_WAIT=10,
    SWR_EVENT_LOOP_RESTORE_FLAGS=11, SWR_EVENT_LOOP_FREE=12,
    SWR_EVENT_LOOP_CLEAR_TIMERS=13, SWR_EVENT_LOOP_STOP=14,
    SWR_EVENT_LOOP_ONCE_ON=15, SWR_EVENT_LOOP_ONCE_OFF=16,
    SWR_EVENT_LOOP_WARN_COROUTINE=17, SWR_EVENT_LOOP_DEPRECATED=18,
    SWR_EVENT_LOOP_CORE_WAIT=19
};
uint32_t swr_v1_phpevents_loop(uint32_t *phase, uint32_t mode, int64_t observation);
typedef struct SwrPhpEventAlias {
    const char *method;
    size_t method_length;
    const char *function;
    size_t function_length;
} SwrPhpEventAlias;
/* Immutable static names, lengths exclude NUL; index outside0..10/null output
 * returns0 without writing. Native supplies aligned independent output storage. */
uint8_t swr_v1_phpevents_alias(size_t index, SwrPhpEventAlias *output);
/* Same static strings and legacy alias ABI; class ordering is selected by zero.
 * Native supplies actual Zend bits, Rust returns the required public|static flags.
 * handler selects only the frozen Native typed binding. Unknown/null => no write. */
typedef struct SwrPhpEventMethod {
    SwrPhpEventAlias alias;
    uint32_t handler;
    uint32_t flags;
} SwrPhpEventMethod;
uint8_t swr_v1_phpevents_catalogue(size_t index, uint8_t legacy_alias,
    uint32_t public_flag, uint32_t static_flag, SwrPhpEventMethod *output);
enum SwrPhpEventFdKind { SWR_EVENT_RESOURCE=0, SWR_EVENT_LONG=1,
    SWR_EVENT_OBJECT=2, SWR_EVENT_OTHER=3 };
enum SwrPhpEventFdAction {
    SWR_EVENT_FD_ERROR=0, SWR_EVENT_FD_RETURN=1,
    SWR_EVENT_FD_STREAM=2, SWR_EVENT_FD_CAST_STREAM=3,
    SWR_EVENT_FD_READ_FD=4, SWR_EVENT_FD_READ_LONG=5,
    SWR_EVENT_FD_CHECK_CO_SOCKET=6, SWR_EVENT_FD_CO_SOCKET_PROPERTY=7,
    SWR_EVENT_FD_CHECK_CLIENT=8, SWR_EVENT_FD_CLIENT_PROPERTY=9,
    SWR_EVENT_FD_CHECK_PROCESS=10, SWR_EVENT_FD_PROCESS_PROPERTY=11,
    SWR_EVENT_FD_CHECK_PHP_SOCKET=12, SWR_EVENT_FD_READ_SOCKET=13,
    SWR_EVENT_FD_CHECK_SOCKET_CLOSED=14, SWR_EVENT_FD_SOCKET_FD=15,
    SWR_EVENT_FD_CHECK_PROPERTY_PRESENT=16, SWR_EVENT_FD_CHECK_PROPERTY_LONG=17,
    SWR_EVENT_FD_PROPERTY_FD=18, SWR_EVENT_FD_WARN_RESOURCE=19,
    SWR_EVENT_FD_WARN_NEGATIVE=20, SWR_EVENT_FD_WARN_CLOSED=21,
    SWR_EVENT_FD_WARN_UNKNOWN=22
};
/* Phase0; copied kind/capability. ReadFd/ReadLong observations signed fd,
 * CastStream Zend status(SUCCESS0), other observations booleans. Native owns
 * all pointers/resources/casts and executes effects only after Rust returns. */
uint32_t swr_v1_phpevents_fd(uint32_t *phase, uint32_t kind,
                           uint8_t sockets, int64_t observation);
enum SwrPhpEventAddAction {
    SWR_EVENT_ADD_FALSE=0, SWR_EVENT_ADD_RETURN_FD=1,
    SWR_EVENT_ADD_CHECK_DUPLICATE=2, SWR_EVENT_ADD_CREATE_READ=3,
    SWR_EVENT_ADD_CREATE_WRITE=4, SWR_EVENT_ADD_ALLOCATE=5,
    SWR_EVENT_ADD_BACKEND_ADD=6, SWR_EVENT_ADD_PUBLISH=7,
    SWR_EVENT_ADD_WARN_UNKNOWN=8, SWR_EVENT_ADD_WARN_FD=9,
    SWR_EVENT_ADD_WARN_DUPLICATE=10, SWR_EVENT_ADD_WARN_EVENTS=11,
    SWR_EVENT_ADD_WARN_READ=12, SWR_EVENT_ADD_WARN_WRITE=13,
    SWR_EVENT_ADD_DELETE_READ=14, SWR_EVENT_ADD_WARN_ADD=15,
    SWR_EVENT_ADD_FREE_SOCKET=16, SWR_EVENT_ADD_FREE_OBJECT=17
};
/* Phase0, after native reactor check/descriptor conversion. Preserve event masks
 * READ512/WRITE1024. Observation duplicate/callback presence, then backend result.
 * Native owns authoritative map, payload, Socket and all cleanup/callbacks. */
uint32_t swr_v1_phpevents_add(uint32_t *phase, int32_t fd,
                            int64_t events, int64_t observation);
enum SwrPhpEventStreamAction {
    SWR_EVENT_STREAM_ERROR=0, SWR_EVENT_STREAM_RETURN=1,
    SWR_EVENT_STREAM_READ_STREAM=2, SWR_EVENT_STREAM_CAST=3,
    SWR_EVENT_STREAM_READ_FD=4, SWR_EVENT_STREAM_READ_ASYNC=5,
    SWR_EVENT_STREAM_READ_SOCKET=6, SWR_EVENT_STREAM_SOCKET_FD=7,
    SWR_EVENT_STREAM_SET_ASYNC=8, SWR_EVENT_STREAM_WARN_RESOURCE=9
};
/* Extended conversion: phase0 after native *async=0/type observation. Resource
 * and sockets are booleans; observations as in fd conversion. Native owns the
 * async output and evaluates its wrapper predicate only on successful cast. */
uint32_t swr_v1_phpevents_stream(uint32_t *phase, uint8_t resource,
                               uint8_t sockets, int64_t observation);
/* Sole metadata owner; no Socket/Zend pointer is dereferenced in Rust. All
 * shared access is serialized as for the original native unordered_map. */
typedef struct SwrPhpEventRegistry SwrPhpEventRegistry;
/* Fallible actual caller path:0 success,-1 null slot,-3 reservation refusal.
 * Native bad_alloc is raised only after return. No allocation failure is injected
 * by ordinary metadata controls; allocator topology remains independently open. */
int32_t swr_v1_phpevents_registry_try_insert(SwrPhpEventRegistry **slot, int32_t fd, uintptr_t value);
void swr_v1_phpevents_registry_insert(SwrPhpEventRegistry **slot, int32_t fd, uintptr_t value);
uint8_t swr_v1_phpevents_registry_contains(const SwrPhpEventRegistry *registry, int32_t fd);
uintptr_t swr_v1_phpevents_registry_get(const SwrPhpEventRegistry *registry, int32_t fd);
uint8_t swr_v1_phpevents_registry_erase(SwrPhpEventRegistry *registry, int32_t fd);
void swr_v1_phpevents_registry_drop(SwrPhpEventRegistry *registry);
enum SwrPhpEventUpdateAction {
    SWR_EVENT_UPDATE_FALSE=0, SWR_EVENT_UPDATE_TRUE=1,
    SWR_EVENT_UPDATE_CREATE_READ=2, SWR_EVENT_UPDATE_CREATE_WRITE=3,
    SWR_EVENT_UPDATE_NEW_READ=4, SWR_EVENT_UPDATE_OLD_READ=5,
    SWR_EVENT_UPDATE_DEFER_READ=6, SWR_EVENT_UPDATE_ASSIGN_READ=7,
    SWR_EVENT_UPDATE_NEW_WRITE=8, SWR_EVENT_UPDATE_OLD_WRITE=9,
    SWR_EVENT_UPDATE_DEFER_WRITE=10, SWR_EVENT_UPDATE_ASSIGN_WRITE=11,
    SWR_EVENT_UPDATE_VALIDATE_READ=12, SWR_EVENT_UPDATE_VALIDATE_WRITE=13,
    SWR_EVENT_UPDATE_BACKEND=14, SWR_EVENT_UPDATE_WARN_READ=15,
    SWR_EVENT_UPDATE_WARN_WRITE=16, SWR_EVENT_UPDATE_WARN_SET=17
};
/* Phase0 after native reactor/parser/descriptor/registry lookup. All callback
 * storage, native deferral/replacement and payload custody stay native. */
uint32_t swr_v1_phpevents_update(uint32_t *phase, int64_t events, int64_t observation);
enum SwrPhpEventQueryAction {
    SWR_EVENT_QUERY_FALSE=0, SWR_EVENT_QUERY_TRUE=1,
    SWR_EVENT_QUERY_REACTOR=2, SWR_EVENT_QUERY_PARSE=3,
    SWR_EVENT_QUERY_DESCRIPTOR=4, SWR_EVENT_QUERY_LOOKUP=5,
    SWR_EVENT_QUERY_REMOVED=6, SWR_EVENT_QUERY_EVENTS=7,
    SWR_EVENT_QUERY_WARN_UNKNOWN=8
};
/* Whole ordinary isset routing; phase0, signed fd/mask or boolean observations.
 * Native parser failure returns before next Rust call, all pointers stay native. */
uint32_t swr_v1_phpevents_query(uint32_t *phase, int64_t events, int64_t observation);
enum SwrPhpEventWriteAction {
    SWR_EVENT_WRITE_FALSE=0, SWR_EVENT_WRITE_TRUE=1,
    SWR_EVENT_WRITE_DESCRIPTOR=2, SWR_EVENT_WRITE_LOOKUP=3,
    SWR_EVENT_WRITE_REACTOR=4, SWR_EVENT_WRITE_BACKEND=5,
    SWR_EVENT_WRITE_WARN_EMPTY=6, SWR_EVENT_WRITE_WARN_UNKNOWN=7,
    SWR_EVENT_WRITE_WARN_MISSING=8
};
uint32_t swr_v1_phpevents_write(uint32_t *phase, size_t length, int64_t observation);
enum SwrPhpEventDeleteAction {
    SWR_EVENT_DELETE_FALSE=0, SWR_EVENT_DELETE_TRUE=1,
    SWR_EVENT_DELETE_REACTOR=2, SWR_EVENT_DELETE_PARSE=3,
    SWR_EVENT_DELETE_DESCRIPTOR=4, SWR_EVENT_DELETE_LOOKUP=5,
    SWR_EVENT_DELETE_DEFER=6, SWR_EVENT_DELETE_BACKEND=7,
    SWR_EVENT_DELETE_ERASE=8, SWR_EVENT_DELETE_INVALIDATE=9,
    SWR_EVENT_DELETE_FREE=10, SWR_EVENT_DELETE_WARN_READY=11,
    SWR_EVENT_DELETE_WARN_UNKNOWN=12
};
uint32_t swr_v1_phpevents_delete(uint32_t *phase, int64_t observation);
enum SwrPhpEventCycleAction {
    SWR_EVENT_CYCLE_FALSE=0, SWR_EVENT_CYCLE_TRUE=1,
    SWR_EVENT_CYCLE_FUTURE=2, SWR_EVENT_CYCLE_IDLE=3,
    SWR_EVENT_CYCLE_IS_NULL=4, SWR_EVENT_CYCLE_HAS_CALLBACK=5,
    SWR_EVENT_CYCLE_HAS_DATA=6, SWR_EVENT_CYCLE_DEFER=7,
    SWR_EVENT_CYCLE_CLEAR=8, SWR_EVENT_CYCLE_CREATE=9,
    SWR_EVENT_CYCLE_ASSIGN=10
};
uint32_t swr_v1_phpevents_cycle(uint32_t *phase, uint8_t before, uint8_t observation);
enum SwrPhpEventDispatchMode {
    SWR_EVENT_DISPATCH_READ=0, SWR_EVENT_DISPATCH_WRITE=1,
    SWR_EVENT_DISPATCH_DEFER=2, SWR_EVENT_DISPATCH_CYCLE=3
};
enum SwrPhpEventDispatchAction {
    SWR_EVENT_DISPATCH_DONE=0, SWR_EVENT_DISPATCH_OK=1,
    SWR_EVENT_DISPATCH_ERROR=2, SWR_EVENT_DISPATCH_WARN=3,
    SWR_EVENT_DISPATCH_CLEAR_OBJECT=4, SWR_EVENT_DISPATCH_DEFER_OBJECT=5,
    SWR_EVENT_DISPATCH_DELETE_EVENT=6, SWR_EVENT_DISPATCH_DELETE_CALLABLE=7
};
/* Native call has completed before phase0; mode/success constant. Never retain
 * native pointers or a Rust frame across callback/cleanup/GC/bailout/yield. */
uint32_t swr_v1_phpevents_dispatch(uint32_t *phase, uint32_t mode, uint8_t success);
#ifdef __cplusplus
}
#endif
#endif
