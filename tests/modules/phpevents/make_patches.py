"""Generate the sole reserved overlay from the pinned reference without editing it."""
from pathlib import Path
import difflib,hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[3]
PIN='8e8c49915ca5f9dcb9ee654f9e336a9c88dd375e'
source=Path(sys.argv[1]);destination='ext-src/swoole_event.cc'
original=subprocess.check_output(['git','-C',str(source),'show',PIN+':'+destination],text=True)
selected=original.replace('#include "swoole_signal.h"','#include "swoole_signal.h"\n#ifdef SWOOLE_RS_PHPEVENTS\n#include "swoole_rs_phpevents.h"\n#include <new>\nstatic_assert(SW_EVENT_READ == 512 && SW_EVENT_WRITE == 1024 && SUCCESS == 0 && SW_OK == 0, "PHP Event scalar ABI");\nstatic uint32_t phpevents_fd_kind(zval *value) {\n    switch (Z_TYPE_P(value)) {\n    case IS_RESOURCE: return SWR_EVENT_RESOURCE;\n    case IS_LONG: return SWR_EVENT_LONG;\n    case IS_OBJECT: return SWR_EVENT_OBJECT;\n    default: return SWR_EVENT_OTHER;\n    }\n}\n#endif',1)
selected = selected.replace('    zend::Callable *readable_callback;\n    zend::Callable *writable_callback;',
    '#ifdef SWOOLE_RS_PHPEVENTS\n    SwrPhpEventCallback readable_callback;\n    SwrPhpEventCallback writable_callback;\n#else\n    zend::Callable *readable_callback;\n    zend::Callable *writable_callback;\n#endif', 1)
selected = selected.replace('    zend::Callable *writable_callback;\n#endif\n};',
    '    zend::Callable *writable_callback;\n#endif\n};\n#ifdef SWOOLE_RS_PHPEVENTS\n'
    'static_assert(sizeof(SwrPhpEventCallback) == sizeof(zend::Callable *) && alignof(SwrPhpEventCallback) == alignof(zend::Callable *), "Event callback cell ABI");\n'
    'struct EventObjectNativeLayout { zval zsocket; zend::Callable *readable_callback; zend::Callable *writable_callback; };\n'
    'static_assert(sizeof(EventObject) == sizeof(EventObjectNativeLayout) && alignof(EventObject) == alignof(EventObjectNativeLayout), "Event object ABI");\n'
    'static_assert(offsetof(EventObject, zsocket) == offsetof(EventObjectNativeLayout, zsocket) && offsetof(EventObject, readable_callback) == offsetof(EventObjectNativeLayout, readable_callback) && offsetof(EventObject, writable_callback) == offsetof(EventObjectNativeLayout, writable_callback), "Event object offsets");\n#endif', 1)
registry = r'''// M28 sole registry adapter: metadata is owned in Rust, pointees remain native.
class PhpeventsRegistry {
    SwrPhpEventRegistry *state = nullptr;
  public:
    ~PhpeventsRegistry() { swr_v1_phpevents_registry_drop(state); }
    bool contains(int fd) const { return swr_v1_phpevents_registry_contains(state, fd); }
    Socket *get(int fd) const {
        return reinterpret_cast<Socket *>(swr_v1_phpevents_registry_get(state, fd));
    }
    void insert(int fd, Socket *value) {
        if (swr_v1_phpevents_registry_try_insert(&state, fd, reinterpret_cast<uintptr_t>(value)) != 0) {
            throw std::bad_alloc(); // Native exception, after Rust returned.
        }
    }
    void erase(int fd) { swr_v1_phpevents_registry_erase(state, fd); }
};
static PhpeventsRegistry event_socket_map;
// End M28 sole registry adapter.'''
selected = selected.replace('static std::unordered_map<int, Socket *> event_socket_map;',
    '#ifdef SWOOLE_RS_PHPEVENTS\n' + registry + '\n#else\nstatic std::unordered_map<int, Socket *> event_socket_map;\n#endif', 1)
def replace_body(signature,body):
    global selected
    start=selected.index(signature);begin=selected.index('{',start)+1;end=begin;depth=1
    while depth:
        depth+=(selected[end]=='{')-(selected[end]=='}');end+=1
    old=selected[begin:end-1]
    selected=selected[:begin]+'\n#ifdef SWOOLE_RS_PHPEVENTS\n'+body+'\n#else'+old+'#endif\n'+selected[end-1:]
replace_body('static void event_object_free(void *data) {',r'''    auto *peo = static_cast<EventObject *>(data);
    uint32_t phase = 0;
    uintptr_t identity = 0;
    for (;;) {
        const auto action = swr_v1_phpevents_callbacks(&phase, SWR_EVENT_CALLBACK_FREE,
             &peo->readable_callback, &peo->writable_callback, 0, 0, &identity);
        delete reinterpret_cast<zend::Callable *>(identity);
        if (action == 2) { break; }
    }
    zval_ptr_dtor((&peo->zsocket));
    efree(peo);''')
replace_body('int php_swoole_reactor_init() {',r'''    uint32_t phase = 0;
    int64_t observation = 0;
    for (;;) {
        switch (swr_v1_phpevents_reactor_init(&phase, observation)) {
        case SWR_EVENT_INIT_OK: return SW_OK;
        case SWR_EVENT_INIT_CLI: observation = SWOOLE_G(cli); break;
        case SWR_EVENT_INIT_SERVER: observation = sw_server() != nullptr; break;
        case SWR_EVENT_INIT_TASK_WORKER: observation = sw_server()->is_task_worker(); break;
        case SWR_EVENT_INIT_TASK_COROUTINE: observation = sw_server()->task_enable_coroutine; break;
        case SWR_EVENT_INIT_MANAGER: observation = sw_server()->is_manager(); break;
        case SWR_EVENT_INIT_REACTOR:
        case SWR_EVENT_INIT_FRESH_REACTOR: observation = sw_reactor() != nullptr; break;
        case SWR_EVENT_INIT_TRACE: swoole_trace_log(SW_TRACE_PHP, "init reactor"); break;
        case SWR_EVENT_INIT_CREATE: observation = swoole_event_init(SW_EVENTLOOP_WAIT_EXIT); break;
        case SWR_EVENT_INIT_REGISTER_SHUTDOWN:
            php_swoole_register_shutdown_function("swoole_event_rshutdown"); break;
        case SWR_EVENT_INIT_USER_CONDITION: observation = bool(SwooleG.user_exit_condition); break;
        case SWR_EVENT_INIT_HAS_CONDITION:
            observation = sw_reactor()->isset_exit_condition(Reactor::EXIT_CONDITION_USER_AFTER_DEFAULT); break;
        case SWR_EVENT_INIT_SET_CONDITION:
            sw_reactor()->set_exit_condition(Reactor::EXIT_CONDITION_USER_AFTER_DEFAULT, SwooleG.user_exit_condition); break;
        case SWR_EVENT_INIT_WARN_CLI:
            php_swoole_fatal_error(E_ERROR, "async-io must be used in PHP CLI mode"); break;
        case SWR_EVENT_INIT_WARN_TASK:
            php_swoole_fatal_error(E_ERROR, "Unable to use async-io in task processes, please set `task_enable_coroutine` to true"); break;
        case SWR_EVENT_INIT_WARN_MANAGER:
            php_swoole_fatal_error(E_ERROR, "Unable to use async-io in manager process"); break;
        case SWR_EVENT_INIT_WARN_CREATE:
            php_swoole_fatal_error(E_ERROR, "Unable to create event-loop reactor"); break;
        default: return SW_ERR;
        }
    }''')
replace_body('static void event_check_reactor() {',r'''    uint32_t phase = 0;
    uint8_t observation = 0;
    for (;;) {
        switch (swr_v1_phpevents_handlers(&phase, observation)) {
        case SWR_EVENT_HANDLERS_CHECK_REACTOR: php_swoole_check_reactor(); break;
        case SWR_EVENT_HANDLERS_OBSERVE_READ:
            observation = swoole_event_isset_handler(SW_FD_USER, SW_EVENT_READ); break;
        case SWR_EVENT_HANDLERS_READ:
            swoole_event_set_handler(SW_FD_USER, SW_EVENT_READ, event_readable_callback); break;
        case SWR_EVENT_HANDLERS_WRITE:
            swoole_event_set_handler(SW_FD_USER, SW_EVENT_WRITE, event_writable_callback); break;
        case SWR_EVENT_HANDLERS_ERROR:
            swoole_event_set_handler(SW_FD_USER, SW_EVENT_ERROR, event_error_callback); break;
        default: return;
        }
    }''')
replace_body('void php_swoole_event_wait() {',r'''    uint32_t phase = 0;
    int64_t observation = 0;
    for (;;) {
        switch (swr_v1_phpevents_loop(&phase, SWR_EVENT_LOOP_WAIT, observation)) {
        case SWR_EVENT_LOOP_FATAL: observation = php_swoole_is_fatal_error(); break;
        case SWR_EVENT_LOOP_REACTOR: observation = sw_reactor() != nullptr; break;
        case SWR_EVENT_LOOP_IN_COROUTINE: observation = swoole_coroutine_is_in(); break;
        case SWR_EVENT_LOOP_IF_EXIT: observation = sw_reactor()->if_exit(); break;
        case SWR_EVENT_LOOP_BAILOUT: observation = sw_reactor()->bailout; break;
        case SWR_EVENT_LOOP_PREPARE_FLAGS:
#if defined(EG_FLAGS_IN_SHUTDOWN) && !defined(EG_FLAGS_OBJECT_STORE_NO_REUSE)
            observation = (EG(flags) & EG_FLAGS_IN_SHUTDOWN) != 0;
            EG(flags) &= ~EG_FLAGS_IN_SHUTDOWN;
#else
            observation = 0;
#endif
            break;
        case SWR_EVENT_LOOP_WAIT_NATIVE: observation = sw_reactor()->wait(); break;
        case SWR_EVENT_LOOP_WARN_WAIT: php_swoole_sys_error(E_ERROR, "reactor wait failed"); break;
        case SWR_EVENT_LOOP_RESTORE_FLAGS:
#if defined(EG_FLAGS_IN_SHUTDOWN) && !defined(EG_FLAGS_OBJECT_STORE_NO_REUSE)
            EG(flags) |= EG_FLAGS_IN_SHUTDOWN;
#endif
            break;
        case SWR_EVENT_LOOP_FREE: swoole_event_free(); break;
        case SWR_EVENT_LOOP_WARN_COROUTINE:
            php_swoole_fatal_error(E_ERROR, "Unable to call Event::wait() in coroutine"); break;
        default: return;
        }
    }''')
replace_body('void php_swoole_event_exit() {',r'''    uint32_t phase = 0;
    int64_t observation = 0;
    for (;;) {
        switch (swr_v1_phpevents_loop(&phase, SWR_EVENT_LOOP_EXIT, observation)) {
        case SWR_EVENT_LOOP_REACTOR: observation = sw_reactor() != nullptr; break;
        case SWR_EVENT_LOOP_CLEAR_TIMERS: php_swoole_timer_clear_all(); break;
        case SWR_EVENT_LOOP_STOP: sw_reactor()->running = false; break;
        default: return;
        }
    }''')
replace_body('static PHP_FUNCTION(swoole_event_dispatch) {',r'''    uint32_t phase = 0;
    int64_t observation = 0;
    for (;;) {
        switch (swr_v1_phpevents_loop(&phase, SWR_EVENT_LOOP_DISPATCH, observation)) {
        case SWR_EVENT_LOOP_FALSE: RETURN_FALSE;
        case SWR_EVENT_LOOP_TRUE: RETURN_TRUE;
        case SWR_EVENT_LOOP_REACTOR: observation = sw_reactor() != nullptr; break;
        case SWR_EVENT_LOOP_ONCE_ON: sw_reactor()->once = true; break;
        case SWR_EVENT_LOOP_ONCE_OFF: sw_reactor()->once = false; break;
        case SWR_EVENT_LOOP_WAIT_NATIVE: observation = sw_reactor()->wait(); break;
        case SWR_EVENT_LOOP_WARN_WAIT: php_swoole_sys_error(E_ERROR, "reactor wait failed"); break;
        default: RETURN_FALSE;
        }
    }''')
replace_body('static PHP_FUNCTION(swoole_event_rshutdown) {',r'''    /* Native bailout boundary: Rust returns before every Zend/effect call. */
    zend_try {
        uint32_t phase = 0;
        int64_t observation = 0;
        for (;;) {
            const auto action = swr_v1_phpevents_loop(&phase, SWR_EVENT_LOOP_RSHUTDOWN, observation);
            if (action == SWR_EVENT_LOOP_DONE) { break; }
            switch (action) {
            case SWR_EVENT_LOOP_FATAL: observation = php_swoole_is_fatal_error(); break;
            case SWR_EVENT_LOOP_REACTOR: observation = sw_reactor() != nullptr; break;
            case SWR_EVENT_LOOP_BAILOUT: observation = sw_reactor()->bailout; break;
            case SWR_EVENT_LOOP_DEPRECATED:
                php_swoole_fatal_error(E_DEPRECATED, "Event::wait() in shutdown function is deprecated"); break;
            case SWR_EVENT_LOOP_CORE_WAIT: php_swoole_event_wait(); break;
            }
        }
    }
    zend_end_try();''')
# Stable Zend arrays are a mandatory ABI projection, never a second catalogue.
start = selected.index('static const zend_function_entry swoole_event_methods[]')
end = selected.index('// clang-format on', start)
original_table = selected[start:end]
bindings = []
import re
for name, handler, info in re.findall(r'ZEND_FENTRY\(\s*(\w+),\s*(ZEND_FN\(\w+\)),\s*(\w+),', original_table):
    bindings.append('    {' + handler + ', ' + info + ', static_cast<uint32_t>(sizeof(' + info + ') / sizeof(zend_internal_arg_info) - 1)},')
assert len(bindings) == 11
selected = selected[:start] + r'''#ifdef SWOOLE_RS_PHPEVENTS
struct PhpEventMethodBinding {
    zif_handler handler;
    const zend_internal_arg_info *arginfo;
    uint32_t arguments;
};
static constexpr PhpEventMethodBinding phpevents_bindings[] = {
''' + '\n'.join(bindings) + r'''
};
static zend_function_entry swoole_event_methods[12]{};
#else
''' + original_table + '#endif\n' + selected[end:]
replace_body('void php_swoole_event_minit(int module_number) {',r'''    SwrPhpEventMethod method;
    size_t index = 0;
    for (; swr_v1_phpevents_catalogue(index, 0, ZEND_ACC_PUBLIC, ZEND_ACC_STATIC, &method); ++index) {
        const auto &binding = phpevents_bindings[method.handler];
        auto &entry = swoole_event_methods[index];
        entry.fname = method.alias.method;
        entry.handler = binding.handler;
        entry.arg_info = binding.arginfo;
        entry.num_args = binding.arguments;
        entry.flags = method.flags;
    }
    swoole_event_methods[index] = {};
    SW_INIT_CLASS_ENTRY(swoole_event, "Swoole\\Event", nullptr, swoole_event_methods);
    SW_SET_CLASS_CREATE(swoole_event, sw_zend_create_object_deny);
    for (index = 0; swr_v1_phpevents_catalogue(index, 1, ZEND_ACC_PUBLIC, ZEND_ACC_STATIC, &method); ++index) {
        sw_zend_register_function_alias(&swoole_event_ce->function_table,
                                        method.alias.method, method.alias.method_length,
                                        CG(function_table), method.alias.function, method.alias.function_length,
                                        phpevents_bindings[method.handler].arginfo);
    }''')
replace_body('int php_swoole_convert_to_fd(zval *zsocket) {',r'''    int fd = -1;
    php_stream *stream = nullptr;
    zval *property = nullptr;
#ifdef SWOOLE_SOCKETS_SUPPORT
    const uint8_t sockets = 1;
    php_socket *socket_value = nullptr;
#else
    const uint8_t sockets = 0;
#endif
    const auto kind = phpevents_fd_kind(zsocket);
    uint32_t phase = 0;
    int64_t observation = 0;
    for (;;) {
        switch (swr_v1_phpevents_fd(&phase, kind, sockets, observation)) {
        case SWR_EVENT_FD_RETURN: return fd;
        case SWR_EVENT_FD_STREAM:
            observation = (php_stream_from_zval_no_verify(stream, zsocket)) != nullptr;
            break;
        case SWR_EVENT_FD_CAST_STREAM:
            observation = php_stream_cast(stream, PHP_STREAM_AS_FD_FOR_SELECT | PHP_STREAM_CAST_INTERNAL,
                                          (void **) &fd, 1);
            break;
        case SWR_EVENT_FD_READ_FD: observation = fd; break;
        case SWR_EVENT_FD_READ_LONG: fd = Z_LVAL_P(zsocket); observation = fd; break;
        case SWR_EVENT_FD_CHECK_CO_SOCKET: observation = sw_zval_is_co_socket(zsocket); break;
        case SWR_EVENT_FD_CO_SOCKET_PROPERTY:
            property = sw_zend_read_property_ex(Z_OBJCE_P(zsocket), zsocket, SW_ZSTR_KNOWN(SW_ZEND_STR_FD), 0);
            break;
        case SWR_EVENT_FD_CHECK_CLIENT: observation = sw_zval_is_client(zsocket); break;
        case SWR_EVENT_FD_CLIENT_PROPERTY:
            property = sw_zend_read_property_ex(Z_OBJCE_P(zsocket), zsocket, SW_ZSTR_KNOWN(SW_ZEND_STR_SOCK), 0);
            break;
        case SWR_EVENT_FD_CHECK_PROCESS: observation = sw_zval_is_process(zsocket); break;
        case SWR_EVENT_FD_PROCESS_PROPERTY:
            property = sw_zend_read_property_ex(Z_OBJCE_P(zsocket), zsocket, SW_ZSTR_KNOWN(SW_ZEND_STR_PIPE), 0);
            break;
#ifdef SWOOLE_SOCKETS_SUPPORT
        case SWR_EVENT_FD_CHECK_PHP_SOCKET: observation = sw_zval_is_php_socket(zsocket); break;
        case SWR_EVENT_FD_READ_SOCKET: socket_value = SW_Z_SOCKET_P(zsocket); break;
        case SWR_EVENT_FD_CHECK_SOCKET_CLOSED: observation = IS_INVALID_SOCKET(socket_value); break;
        case SWR_EVENT_FD_SOCKET_FD: fd = socket_value->bsd_socket; break;
#endif
        case SWR_EVENT_FD_CHECK_PROPERTY_PRESENT: observation = property != nullptr; break;
        case SWR_EVENT_FD_CHECK_PROPERTY_LONG: observation = Z_TYPE_P(property) == IS_LONG; break;
        case SWR_EVENT_FD_PROPERTY_FD: fd = Z_LVAL_P(property); break;
        case SWR_EVENT_FD_WARN_RESOURCE:
            php_swoole_fatal_error(E_WARNING, "fd argument must be either valid PHP stream or valid PHP socket resource");
            break;
        case SWR_EVENT_FD_WARN_NEGATIVE:
            php_swoole_fatal_error(E_WARNING, "invalid file descriptor#%d passed", fd);
            break;
        case SWR_EVENT_FD_WARN_CLOSED:
            php_swoole_fatal_error(E_WARNING, "contains a closed socket");
            break;
        case SWR_EVENT_FD_WARN_UNKNOWN:
            php_swoole_fatal_error(E_WARNING, "invalid file descriptor passed");
            break;
        default: return SW_ERR;
        }
    }''')
replace_body('static PHP_FUNCTION(swoole_event_add) {',r'''    zval *zfd;
    zend_long events = SW_EVENT_READ;
    zval *zreadable_callback = nullptr;
    zval *zwritable_callback = nullptr;
    ZEND_PARSE_PARAMETERS_START(1, 4)
    Z_PARAM_ZVAL(zfd)
    Z_PARAM_OPTIONAL
    Z_PARAM_ZVAL(zreadable_callback)
    Z_PARAM_ZVAL(zwritable_callback)
    Z_PARAM_LONG(events)
    ZEND_PARSE_PARAMETERS_END_EX(RETURN_FALSE);

    event_check_reactor();
    const int socket_fd = php_swoole_convert_to_fd(zfd);
    zend::Callable *readable_callback = nullptr, *writable_callback = nullptr;
    EventObject *peo = nullptr;
    Socket *socket = nullptr;
    uint32_t phase = 0;
    int64_t observation = 0;
    for (;;) {
        switch (swr_v1_phpevents_add(&phase, socket_fd, events, observation)) {
        case SWR_EVENT_ADD_RETURN_FD: RETURN_LONG(socket_fd);
        case SWR_EVENT_ADD_CHECK_DUPLICATE:
            observation = event_socket_map.contains(socket_fd);
            break;
        case SWR_EVENT_ADD_CREATE_READ:
            readable_callback = sw_callable_create_ex(zreadable_callback, "readable_callback", true);
            observation = readable_callback != nullptr;
            break;
        case SWR_EVENT_ADD_CREATE_WRITE:
            writable_callback = sw_callable_create_ex(zwritable_callback, "writable_callback", true);
            observation = writable_callback != nullptr;
            break;
        case SWR_EVENT_ADD_ALLOCATE: {
            peo = static_cast<EventObject *>(ecalloc(1, sizeof(EventObject)));
            Z_TRY_ADDREF_P(zfd);
            peo->zsocket = *zfd;
            uint32_t callbacks_phase = 0;
            uintptr_t identity = 0;
            swr_v1_phpevents_callbacks(&callbacks_phase, SWR_EVENT_CALLBACK_SEED,
                &peo->readable_callback, &peo->writable_callback,
                reinterpret_cast<uintptr_t>(readable_callback),
                reinterpret_cast<uintptr_t>(writable_callback), &identity);
            socket = make_socket(socket_fd, SW_FD_USER);
            socket->set_nonblock();
            socket->object = peo;
            break;
        }
        case SWR_EVENT_ADD_BACKEND_ADD: observation = swoole_event_add(socket, events); break;
        case SWR_EVENT_ADD_PUBLISH: event_socket_map.insert(socket_fd, socket); break;
        case SWR_EVENT_ADD_DELETE_READ: delete readable_callback; break;
        case SWR_EVENT_ADD_FREE_SOCKET: socket->free(); break;
        case SWR_EVENT_ADD_FREE_OBJECT: event_object_free(peo); break;
        case SWR_EVENT_ADD_WARN_UNKNOWN:
            php_swoole_fatal_error(E_WARNING, "unknown fd type"); break;
        case SWR_EVENT_ADD_WARN_FD:
            php_swoole_fatal_error(E_WARNING, "invalid socket fd [%d]", socket_fd); break;
        case SWR_EVENT_ADD_WARN_DUPLICATE:
            php_swoole_fatal_error(E_WARNING, "already exist"); break;
        case SWR_EVENT_ADD_WARN_EVENTS:
            php_swoole_fatal_error(E_WARNING, "invalid events"); break;
        case SWR_EVENT_ADD_WARN_READ:
            php_swoole_fatal_error(E_WARNING, "%s: unable to find readable callback of fd [%d]",
                                   ZSTR_VAL(swoole_event_ce->name), socket_fd); break;
        case SWR_EVENT_ADD_WARN_WRITE:
            php_swoole_fatal_error(E_WARNING, "%s: unable to find writable callback of fd [%d]",
                                   ZSTR_VAL(swoole_event_ce->name), socket_fd); break;
        case SWR_EVENT_ADD_WARN_ADD:
            php_swoole_fatal_error(E_WARNING, "swoole_event_add failed"); break;
        default: RETURN_FALSE;
        }
    }''')
replace_body('int php_swoole_convert_to_fd_ex(zval *zsocket, int *async) {',r'''    *async = 0;
    const uint8_t resource = Z_TYPE_P(zsocket) == IS_RESOURCE;
    int fd = -1;
    php_stream *stream = nullptr;
#ifdef SWOOLE_SOCKETS_SUPPORT
    const uint8_t sockets = 1;
    php_socket *php_sock = nullptr;
#else
    const uint8_t sockets = 0;
#endif
    uint32_t phase = 0;
    int64_t observation = 0;
    for (;;) {
        switch (swr_v1_phpevents_stream(&phase, resource, sockets, observation)) {
        case SWR_EVENT_STREAM_RETURN: return fd;
        case SWR_EVENT_STREAM_READ_STREAM:
            observation = (php_stream_from_zval_no_verify(stream, zsocket)) != nullptr;
            break;
        case SWR_EVENT_STREAM_CAST:
            observation = php_stream_cast(stream, PHP_STREAM_AS_FD_FOR_SELECT | PHP_STREAM_CAST_INTERNAL,
                                          (void **) &fd, 1);
            break;
        case SWR_EVENT_STREAM_READ_FD: observation = fd; break;
        case SWR_EVENT_STREAM_READ_ASYNC:
            *async = (stream->wrapper && (stream->wrapper->wops == php_plain_files_wrapper.wops)) ? 0 : 1;
            break;
#ifdef SWOOLE_SOCKETS_SUPPORT
        case SWR_EVENT_STREAM_READ_SOCKET:
            observation = (php_sock = SW_Z_SOCKET_P(zsocket)) != nullptr;
            break;
        case SWR_EVENT_STREAM_SOCKET_FD: fd = php_sock->bsd_socket; break;
#endif
        case SWR_EVENT_STREAM_SET_ASYNC: *async = 1; break;
        case SWR_EVENT_STREAM_WARN_RESOURCE:
            php_swoole_fatal_error(E_WARNING, "fd argument must be either valid PHP stream or valid PHP socket resource");
            break;
        default: return SW_ERR;
        }
    }''')
replace_body('static Socket *event_get_socket(int socket_fd) {',r'''    return event_socket_map.get(socket_fd);''')
signature = 'static PHP_FUNCTION(swoole_event_set) {'
start = original.index(signature) + len(signature)
end = original.index('    auto *peo = static_cast<EventObject *>(socket->object);', start)
prefix = original[start:end]
replace_body(signature,prefix + r'''    auto *peo = static_cast<EventObject *>(socket->object);
    zend::Callable *readable_callback = nullptr, *writable_callback = nullptr;
    uint32_t phase = 0;
    int64_t observation = 0;
    for (;;) {
        uintptr_t identity = 0;
        switch (swr_v1_phpevents_update_owned(&phase, events, observation,
                    &peo->readable_callback, &peo->writable_callback,
                    reinterpret_cast<uintptr_t>(readable_callback),
                    reinterpret_cast<uintptr_t>(writable_callback), &identity)) {
        case SWR_EVENT_UPDATE_TRUE: RETURN_TRUE;
        case SWR_EVENT_UPDATE_CREATE_READ:
            readable_callback = sw_callable_create_ex(zreadable_callback, "readable_callback"); break;
        case SWR_EVENT_UPDATE_CREATE_WRITE:
            writable_callback = sw_callable_create_ex(zwritable_callback, "writable_callback"); break;
        case SWR_EVENT_UPDATE_DEFER_READ: swoole_event_defer(sw_callable_free, reinterpret_cast<void *>(identity)); break;
        case SWR_EVENT_UPDATE_DEFER_WRITE: swoole_event_defer(sw_callable_free, reinterpret_cast<void *>(identity)); break;
        case SWR_EVENT_UPDATE_BACKEND: observation = swoole_event_set(socket, events); break;
        case SWR_EVENT_UPDATE_WARN_READ:
            php_swoole_fatal_error(E_WARNING, "%s: unable to find readable callback of fd [%d]",
                                   ZSTR_VAL(swoole_event_ce->name), socket_fd); break;
        case SWR_EVENT_UPDATE_WARN_WRITE:
            php_swoole_fatal_error(E_WARNING, "%s: unable to find writable callback of fd [%d]",
                                   ZSTR_VAL(swoole_event_ce->name), socket_fd); break;
        case SWR_EVENT_UPDATE_WARN_SET:
            php_swoole_fatal_error(E_WARNING, "%s::set failed", ZSTR_VAL(swoole_event_ce->name)); break;
        default: RETURN_FALSE;
        }
    }''')
replace_body('static PHP_FUNCTION(swoole_event_isset) {',r'''    zval *zfd = nullptr;
    zend_long events = SW_EVENT_READ | SW_EVENT_WRITE;
    int socket_fd = -1;
    Socket *socket = nullptr;
    uint32_t phase = 0;
    int64_t observation = 0;
    for (;;) {
        switch (swr_v1_phpevents_query(&phase, events, observation)) {
        case SWR_EVENT_QUERY_TRUE: RETURN_TRUE;
        case SWR_EVENT_QUERY_REACTOR: observation = sw_reactor() != nullptr; break;
        case SWR_EVENT_QUERY_PARSE:
            if (zend_parse_parameters(ZEND_NUM_ARGS(), "z|l", &zfd, &events) == FAILURE) {
                RETURN_FALSE;
            }
            break;
        case SWR_EVENT_QUERY_DESCRIPTOR:
            socket_fd = php_swoole_convert_to_fd(zfd); observation = socket_fd; break;
        case SWR_EVENT_QUERY_LOOKUP:
            socket = event_get_socket(socket_fd); observation = socket != nullptr; break;
        case SWR_EVENT_QUERY_REMOVED: observation = socket->removed; break;
        case SWR_EVENT_QUERY_EVENTS: observation = socket->events; break;
        case SWR_EVENT_QUERY_WARN_UNKNOWN:
            php_swoole_fatal_error(E_WARNING, "unknown type"); break;
        default: RETURN_FALSE;
        }
    }''')
signature = 'static PHP_FUNCTION(swoole_event_write) {'
start = original.index(signature) + len(signature)
end = original.index('    if (len == 0)', start)
replace_body(signature,original[start:end] + r'''    int socket_fd = -1;
    Socket *socket = nullptr;
    uint32_t phase = 0;
    int64_t observation = 0;
    for (;;) {
        switch (swr_v1_phpevents_write(&phase, len, observation)) {
        case SWR_EVENT_WRITE_TRUE: RETURN_TRUE;
        case SWR_EVENT_WRITE_DESCRIPTOR:
            socket_fd = php_swoole_convert_to_fd(zfd); observation = socket_fd; break;
        case SWR_EVENT_WRITE_LOOKUP:
            socket = event_get_socket(socket_fd); observation = socket != nullptr; break;
        case SWR_EVENT_WRITE_REACTOR: event_check_reactor(); break;
        case SWR_EVENT_WRITE_BACKEND: observation = swoole_event_write(socket, data, len); break;
        case SWR_EVENT_WRITE_WARN_EMPTY: php_swoole_fatal_error(E_WARNING, "data empty"); break;
        case SWR_EVENT_WRITE_WARN_UNKNOWN: php_swoole_fatal_error(E_WARNING, "unknown type"); break;
        case SWR_EVENT_WRITE_WARN_MISSING:
            php_swoole_fatal_error(E_WARNING, "socket[%d] is not found in the reactor", socket_fd); break;
        default: RETURN_FALSE;
        }
    }''')
replace_body('static PHP_FUNCTION(swoole_event_del) {',r'''    zval *zfd = nullptr;
    int socket_fd = -1;
    Socket *socket = nullptr;
    uint32_t phase = 0;
    int64_t observation = 0;
    for (;;) {
        switch (swr_v1_phpevents_delete(&phase, observation)) {
        case SWR_EVENT_DELETE_TRUE: RETURN_TRUE;
        case SWR_EVENT_DELETE_REACTOR: observation = sw_reactor() != nullptr; break;
        case SWR_EVENT_DELETE_PARSE: {
            ZEND_PARSE_PARAMETERS_START(1, 1)
            Z_PARAM_ZVAL(zfd)
            ZEND_PARSE_PARAMETERS_END_EX(RETURN_FALSE);
            break;
        }
        case SWR_EVENT_DELETE_DESCRIPTOR:
            socket_fd = php_swoole_convert_to_fd(zfd); observation = socket_fd; break;
        case SWR_EVENT_DELETE_LOOKUP:
            socket = event_get_socket(socket_fd); observation = socket != nullptr; break;
        case SWR_EVENT_DELETE_DEFER: swoole_event_defer(event_object_free, socket->object); break;
        case SWR_EVENT_DELETE_BACKEND: observation = swoole_event_del(socket); break;
        case SWR_EVENT_DELETE_ERASE: event_socket_map.erase(socket_fd); break;
        case SWR_EVENT_DELETE_INVALIDATE: socket->fd = -1; break;
        case SWR_EVENT_DELETE_FREE: socket->free(); break;
        case SWR_EVENT_DELETE_WARN_READY:
            php_swoole_fatal_error(E_WARNING, "reactor is not ready, cannot call swoole_event_del"); break;
        case SWR_EVENT_DELETE_WARN_UNKNOWN: php_swoole_fatal_error(E_WARNING, "unknown type"); break;
        default: RETURN_FALSE;
        }
    }''')
signature = 'static PHP_FUNCTION(swoole_event_cycle) {'
start = original.index(signature) + len(signature)
end = original.index('    auto defer_task = before ?', start)
replace_body(signature,original[start:end] + r'''    decltype(&reactor->future_task) defer_task = nullptr;
    zend::Callable *callback = nullptr;
    uint32_t phase = 0;
    uint8_t observation = 0;
    for (;;) {
        switch (swr_v1_phpevents_cycle(&phase, before, observation)) {
        case SWR_EVENT_CYCLE_TRUE: RETURN_TRUE;
        case SWR_EVENT_CYCLE_FUTURE: defer_task = &reactor->future_task; break;
        case SWR_EVENT_CYCLE_IDLE: defer_task = &reactor->idle_task; break;
        case SWR_EVENT_CYCLE_IS_NULL: observation = ZVAL_IS_NULL(zcallback); break;
        case SWR_EVENT_CYCLE_HAS_CALLBACK: observation = defer_task->callback != nullptr; break;
        case SWR_EVENT_CYCLE_HAS_DATA: observation = defer_task->data != nullptr; break;
        case SWR_EVENT_CYCLE_DEFER: swoole_event_defer(sw_callable_free, defer_task->data); break;
        case SWR_EVENT_CYCLE_CLEAR: defer_task->callback = nullptr; defer_task->data = nullptr; break;
        case SWR_EVENT_CYCLE_CREATE: callback = sw_callable_create(zcallback); break;
        case SWR_EVENT_CYCLE_ASSIGN:
            defer_task->callback = event_cycle_callback; defer_task->data = callback; break;
        default: RETURN_FALSE;
        }
    }''')
for category, mode in [('readable', 'READ'), ('writable', 'WRITE')]:
    signature = 'static int event_' + category + '_callback(Reactor *reactor, Event *event) {'
    start = original.index(signature) + len(signature)
    end = original.index('    if (UNEXPECTED(!zend::function::call(', start)
    prefix = original[start:end]
    prefix = prefix.replace('    auto fcc = peo->' + category + '_callback->ptr();',
        '    uint32_t callbacks_phase = 0;\n    uintptr_t identity = 0;\n'
        '    swr_v1_phpevents_callbacks(&callbacks_phase, SWR_EVENT_CALLBACK_' + mode + ',\n'
        '        &peo->readable_callback, &peo->writable_callback, 0, 0, &identity);\n'
        '    auto fcc = reinterpret_cast<zend::Callable *>(identity)->ptr();')
    replacement = prefix + r'''    const bool success = zend::function::call(fcc, 1, argv, nullptr, php_swoole_is_enable_coroutine());
    uint32_t phase = 0;
    for (;;) {
        switch (swr_v1_phpevents_dispatch(&phase, SWR_EVENT_DISPATCH_MODE, success)) {
        case SWR_EVENT_DISPATCH_OK: return SW_OK;
        case SWR_EVENT_DISPATCH_ERROR: return SW_ERR;
        case SWR_EVENT_DISPATCH_WARN:
            php_swoole_fatal_error(E_WARNING, "%s: CATEGORY callback handler error, fd [%d] will be removed from reactor",
                                   ZSTR_VAL(swoole_event_ce->name), php_swoole_convert_to_fd(&peo->zsocket));
            break;
        case SWR_EVENT_DISPATCH_CLEAR_OBJECT: event->socket->object = nullptr; break;
        case SWR_EVENT_DISPATCH_DEFER_OBJECT: swoole_event_defer(event_object_free, peo); break;
        case SWR_EVENT_DISPATCH_DELETE_EVENT: swoole_event_del(event->socket); break;
        default: return SW_ERR;
        }
    }'''
    replace_body(signature,replacement.replace('DISPATCH_MODE', 'DISPATCH_' + mode).replace('CATEGORY', category))
for category,mode,diagnostic in [('defer','DEFER','defer'),('cycle','CYCLE','end')]:
    signature = 'static void event_' + category + '_callback(void *data) {'
    start = original.index(signature) + len(signature)
    end = original.index('    if (UNEXPECTED(!zend::function::call(', start)
    replacement = original[start:end] + r'''    const bool success = zend::function::call(cb, 0, nullptr, nullptr, php_swoole_is_enable_coroutine());
    uint32_t phase = 0;
    for (;;) {
        switch (swr_v1_phpevents_dispatch(&phase, SWR_EVENT_DISPATCH_MODE, success)) {
        case SWR_EVENT_DISPATCH_WARN:
            php_swoole_error(E_WARNING, "%s::DIAGNOSTIC callback handler error", ZSTR_VAL(swoole_event_ce->name));
            break;
DELETE_CASE
        default: return;
        }
    }'''
    replacement=replacement.replace('DISPATCH_MODE','DISPATCH_' + mode).replace('DIAGNOSTIC',diagnostic)
    replacement=replacement.replace('DELETE_CASE', '        case SWR_EVENT_DISPATCH_DELETE_CALLABLE: delete cb; break;' if category=='defer' else '')
    replace_body(signature,replacement)
content='diff --git a/'+destination+' b/'+destination+'\n'+''.join(difflib.unified_diff(original.splitlines(True),selected.splitlines(True),fromfile='a/'+destination,tofile='b/'+destination))
# Git accepts an empty line as blank context; avoid trailing-space-only lines
# in this tracked patch artifact while retaining all source and hunk context.
content=''.join('\n' if line == ' \n' else line for line in content.splitlines(True))
folder=ROOT/'migration/patches/phpevents';patch=folder/'0001-php-event-frontend.patch';patch.write_text(content)
(folder/'manifest.json').write_text(json.dumps({'upstream_commit':PIN,'patches':[{'path':patch.name,'sha256':hashlib.sha256(patch.read_bytes()).hexdigest(),'upstream_paths':[destination]}]},indent=2)+'\n')
