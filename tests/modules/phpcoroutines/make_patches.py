#!/usr/bin/env python3
"""Produce the pinned Scheduler overlay; never modify the reference checkout."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
from bootstrap_bodies import replace_minit
from method_catalogue_bodies import replace_method_catalogue
from transfer_bodies import replace_transfers
from config_bodies import replace_config_cpp, replace_config_header
from fiber_bodies import replace_fibers
from system_control_bodies import replace_system_controls
from activated_bodies import replace_activated_cpp, replace_activated_header, ACTIVATED_SIGNATURE
from exit_bodies import replace_exits
from control_bodies import replace_controls
from join_bodies import replace_join
from terminal_bodies import replace_terminal
from lifecycle_bodies import replace_lifecycle
from interrupt_bodies import replace_interrupt_cpp, replace_interrupt_header
from ordinary_bodies import replace_ordinary
from context_lifecycle_bodies import replace_context_lifecycle
from scheduler_control_bodies import replace_scheduler_controls
from scheduler_slot_bodies import replace_scheduler_slots
from metadata_bodies import replace_metadata_cpp, replace_metadata_header

ROOT = Path(__file__).resolve().parents[3]
import sys
sys.path.insert(0, str(ROOT))
from tools.build_upstream import COMMIT as PIN
DEST = 'ext-src/swoole_coroutine_scheduler.cc'
SOURCE_SHA = '1138bb9799c96ac6ec75ad027eaa3fc5f40cce63f76939e71d9f753e1d80395c'


def body(source, signature):
    start = source.index(signature) + len(signature)
    depth = 1
    end = start
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end - 1]


def selected(source):
    if hashlib.sha256(source.encode()).hexdigest() != SOURCE_SHA:
        raise ValueError('Pinned Scheduler source changed')
    result = source.replace('#include <queue>', '''#ifdef SWOOLE_RS_PHPCOROUTINES
#include "swoole_rs_phpcoroutines.h"
#include <new>
#else
#include <queue>
#endif''')
    result = result.replace('    zend_long count;\n    zend_fcall_info fci;', '''#ifndef SWOOLE_RS_PHPCOROUTINES
    zend_long count;
#endif
    zend_fcall_info fci;''')
    result = result.replace('    std::queue<SchedulerTask *> *list;', '''#ifdef SWOOLE_RS_PHPCOROUTINES
    swr_phpcoroutines_scheduler_queue *list;
#else
    std::queue<SchedulerTask *> *list;
#endif''')
    result = result.replace('    bool started;', '''#ifdef SWOOLE_RS_PHPCOROUTINES
    swr_phpcoroutines_scheduler_phase started;
#else
    bool started;
#endif''')
    result = result.replace('static zend::Callable *exit_condition_fci_cache = nullptr;',
        '#ifdef SWOOLE_RS_PHPCOROUTINES\nstatic swr_phpcoroutines_scheduler_callback_owner exit_condition_fci_cache{0};\n#else\nstatic zend::Callable *exit_condition_fci_cache = nullptr;\n#endif')
    replacements = {}
    for name, expression in [('add', '1'), ('parallel', 'count')]:
        sig = f'static PHP_METHOD(swoole_coroutine_scheduler, {name}) {{'
        replacements[sig] = body(source, sig).replace(
            f'    task->count = {expression};\n    scheduler_add_task(s, task);',
            f'    scheduler_add_task(s, task, {expression});')
    sig = 'static PHP_METHOD(swoole_coroutine_scheduler, start) {'
    replacements[sig] = body(source, sig).replace('''    while (!s->list->empty()) {
        SchedulerTask *task = s->list->front();
        s->list->pop();
        for (zend_long i = 0; i < task->count; i++) {''', '''    swr_phpcoroutines_scheduler_task next;
    while (swr_v1_phpcoroutines_scheduler_pop(s->list, &next)) {
        auto *task = reinterpret_cast<SchedulerTask *>(next.token);
        for (uint64_t i = 0; i < next.repetitions; i++) {''').replace(
            '    delete s->list;', '    swr_v1_phpcoroutines_scheduler_drop(s->list);')
    replacements['void php_swoole_set_coroutine_option(zend_array *vht) {'] = r"""
    zval *ztmp = nullptr;
    swr_phpcoroutines_option_state state{};
    int64_t observation = 0;
    for (;;) {
        const auto plan = swr_v1_phpcoroutines_options(&state, observation, SW_DEFAULT_MAX_CORO_NUM);
        switch (plan.action) {
        case SWR_CORO_OPTION_DONE: return;
        case SWR_CORO_OPTION_LOOKUP:
            ztmp = zend_hash_str_find(vht, plan.key, plan.key_length);
            observation = ztmp && !ZVAL_IS_NULL(ztmp);
            break;
        case SWR_CORO_OPTION_GET_MAX: observation = zval_get_long(ztmp); break;
        case SWR_CORO_OPTION_SET_MAX: PHPCoroutine::set_max_num(plan.value); break;
        case SWR_CORO_OPTION_DEADLOCK: PHPCoroutine::set_deadlock_check(zval_is_true(ztmp)); break;
        case SWR_CORO_OPTION_HOOKS: PHPCoroutine::set_hook_flags(zval_get_long(ztmp)); break;
        case SWR_CORO_OPTION_PREEMPTIVE: PHPCoroutine::enable_preemptive_scheduler(zval_is_true(ztmp)); break;
        case SWR_CORO_OPTION_STACK: Coroutine::set_stack_size(php_swoole_parse_to_size(ztmp)); break;
        case SWR_CORO_OPTION_CHECK_RESOLVERS: observation = ZVAL_IS_ARRAY(ztmp); break;
        case SWR_CORO_OPTION_WARN_RESOLVERS:
            php_swoole_fatal_error(E_WARNING, "name_resolver must be an array");
            break;
        case SWR_CORO_OPTION_RESOLVERS:
            zend_hash_apply(Z_ARR_P(ztmp), [](zval *zresolver) -> int {
                php_swoole_name_resolver_add(zresolver);
                return ZEND_HASH_APPLY_KEEP;
            });
            break;
        case SWR_CORO_OPTION_HAS_OPTIONS: observation = PHPCoroutine::options != nullptr; break;
        case SWR_CORO_OPTION_MERGE: zend_hash_merge(PHPCoroutine::options, vht, zval_add_ref, true); break;
        case SWR_CORO_OPTION_DUP: PHPCoroutine::options = zend_array_dup(vht); break;
        }
    }
"""
    sig = 'PHP_METHOD(swoole_coroutine_scheduler, set) {'
    original = body(source, sig)
    prefix = original[:original.index('    php_swoole_set_global_option(vht);')].replace('zval *ztmp;', 'zval *ztmp = nullptr;')
    replacements[sig] = prefix + r"""
    swr_phpcoroutines_configure_state state{};
    uint8_t observation = 0;
    uintptr_t created = 0;
    for (;;) {
        const auto owned = swr_v1_phpcoroutines_configure_owned(&state, &exit_condition_fci_cache, observation, created);
        const auto &plan = owned.plan;
        switch (plan.action) {
        case SWR_CORO_CONFIG_DONE: return;
        case SWR_CORO_CONFIG_GLOBAL: php_swoole_set_global_option(vht); break;
        case SWR_CORO_CONFIG_COROUTINE: php_swoole_set_coroutine_option(vht); break;
        case SWR_CORO_CONFIG_LOOKUP_NONNULL:
            ztmp = zend_hash_str_find(vht, plan.key, plan.key_length);
            observation = ztmp && !ZVAL_IS_NULL(ztmp);
            break;
        case SWR_CORO_CONFIG_EXPIRE: System::set_dns_cache_expire((time_t) zval_get_long(ztmp)); break;
        case SWR_CORO_CONFIG_CAPACITY: System::set_dns_cache_capacity((size_t) zval_get_long(ztmp)); break;
        case SWR_CORO_CONFIG_LOOKUP_ANY:
            ztmp = zend_hash_str_find(vht, plan.key, plan.key_length);
            observation = ztmp != nullptr;
            break;
        case SWR_CORO_CONFIG_FREE: sw_callable_free(reinterpret_cast<zend::Callable *>(owned.identity)); break;
        case SWR_CORO_CONFIG_CREATE:
            created = reinterpret_cast<uintptr_t>(sw_callable_create(ztmp));
            break;
        case SWR_CORO_CONFIG_PUBLISH: SwooleG.user_exit_condition = php_swoole_coroutine_reactor_can_exit; break;
        case SWR_CORO_CONFIG_HAS_REACTOR: observation = sw_reactor() != nullptr; break;
        case SWR_CORO_CONFIG_INSTALL:
            sw_reactor()->set_exit_condition(Reactor::EXIT_CONDITION_USER_AFTER_DEFAULT, SwooleG.user_exit_condition);
            break;
        case SWR_CORO_CONFIG_REMOVE: sw_reactor()->remove_exit_condition(Reactor::EXIT_CONDITION_USER_AFTER_DEFAULT); break;
        case SWR_CORO_CONFIG_CLEAR: SwooleG.user_exit_condition = nullptr; break;
        }
    }
"""
    for sig, new_body in replacements.items():
        if sig in ['static PHP_METHOD(swoole_coroutine_scheduler, ' + name + ') {' for name in ('add', 'parallel', 'start')]:
            new_body = new_body.replace('if (s->started)', 'if (swr_v1_phpcoroutines_scheduler_phase(&s->started, SWR_CORO_SCHED_PHASE_READ))')
            new_body = new_body.replace('s->started = true;', 'swr_v1_phpcoroutines_scheduler_phase(&s->started, SWR_CORO_SCHED_PHASE_START);')
            new_body = new_body.replace('s->started = false;', 'swr_v1_phpcoroutines_scheduler_phase(&s->started, SWR_CORO_SCHED_PHASE_STOP);')
        original = body(source, sig)
        result = result.replace(sig + original + '}', sig + '\n#ifdef SWOOLE_RS_PHPCOROUTINES\n' +
                                new_body + '#else\n' + original + '#endif\n}')
    return replace_method_catalogue(source, replace_scheduler_slots(source, replace_scheduler_controls(source, replace_minit(source, result, 1, body), body), body), body)


def coroutine_selected(source):
    expected = 'dbad84a6cfdedff33a327d9d43a2c70777ea68efd9421db15cd8e9d46145a112'
    if hashlib.sha256(source.encode()).hexdigest() != expected:
        raise ValueError('Pinned Coroutine source changed')
    result = source.replace('#include <unordered_map>', '#ifdef SWOOLE_RS_PHPCOROUTINES\n#include "swoole_rs_phpcoroutines.h"\n#include <new>\n#else\n#include <unordered_map>\n#endif')
    result = result.replace('using std::unordered_map;', '#ifndef SWOOLE_RS_PHPCOROUTINES\nusing std::unordered_map;\n#endif')
    result = result.replace('static SW_THREAD_LOCAL unordered_map<long, Coroutine *> user_yield_coros;', r"""#ifdef SWOOLE_RS_PHPCOROUTINES
class UserYieldCoroutines {
    swr_phpcoroutines_yield_registry *registry = nullptr;
  public:
    UserYieldCoroutines() = default;
    ~UserYieldCoroutines() {
        if (registry) { swr_v1_phpcoroutines_yield_registry_drop(registry); }
    }
    UserYieldCoroutines(const UserYieldCoroutines &) = delete;
    UserYieldCoroutines &operator=(const UserYieldCoroutines &) = delete;
    void put(long cid, Coroutine *co) {
        if (!swr_v1_phpcoroutines_yield_registry_try_put(&registry, cid, reinterpret_cast<uintptr_t>(co))) {
            throw std::bad_alloc();
        }
    }
    bool take(long cid, Coroutine **co) {
        uintptr_t token;
        if (!swr_v1_phpcoroutines_yield_registry_take(registry, cid, &token)) { return false; }
        *co = reinterpret_cast<Coroutine *>(token);
        return true;
    }
    void erase(long cid) { swr_v1_phpcoroutines_yield_registry_erase(registry, cid); }
};
static SW_THREAD_LOCAL UserYieldCoroutines user_yield_coros;
#else
static SW_THREAD_LOCAL unordered_map<long, Coroutine *> user_yield_coros;
#endif""")
    signature = 'void PHPCoroutine::activate() {'
    original = body(source, signature)
    replacement = r"""
    uint32_t stage = 0;
    uint8_t observation = 0;
    zval *enable_library = nullptr;
    for (;;) {
        switch (swr_v1_phpcoroutines_activation(&stage, observation)) {
        case SWR_CORO_ACTIVATE_DONE: return;
        case SWR_CORO_ACTIVATE_ACTIVE: observation = activated; break;
        case SWR_CORO_ACTIVATE_LIBRARY:
            enable_library = zend_get_constant_str(ZEND_STRL("SWOOLE_LIBRARY"));
            observation = enable_library != nullptr;
            break;
        case SWR_CORO_ACTIVATE_LIBRARY_BOOL: observation = zval_is_true(enable_library); break;
        case SWR_CORO_ACTIVATE_LOAD: php_swoole_load_library(); break;
        case SWR_CORO_ACTIVATE_REACTOR:
            php_swoole_check_reactor();
            orig_interrupt_function = zend_interrupt_function;
            zend_interrupt_function = coro_interrupt_function;
            break;
        case SWR_CORO_ACTIVATE_GLOBAL_PREEMPT: observation = SWOOLE_G(enable_preemptive_scheduler); break;
        case SWR_CORO_ACTIVATE_LOCAL_PREEMPT: observation = swr_v1_phpcoroutines_config(&config, SWR_CORO_CONFIG_GET_PREEMPTIVE, 0); break;
        case SWR_CORO_ACTIVATE_INTERRUPT: interrupt_thread_start(); break;
        case SWR_CORO_ACTIVATE_MAIN: observation = sw_is_main_thread(); break;
        case SWR_CORO_ACTIVATE_HOOK_FLAGS: observation = get_hook_flags() != 0; break;
        case SWR_CORO_ACTIVATE_HOOKS: enable_hook(get_hook_flags()); break;
        case SWR_CORO_ACTIVATE_UNSAFE: disable_unsafe_function(); break;
        case SWR_CORO_ACTIVATE_PUBLISH:
            sw_reactor()->add_destroy_callback(deactivate, nullptr);
            Coroutine::activate();
            Coroutine::set_on_yield(on_yield);
            Coroutine::set_on_resume(on_resume);
            Coroutine::set_on_close(on_close);
            activated = true;
            break;
        }
    }
"""
    result = result.replace(signature + original + '}', signature + '\n#ifdef SWOOLE_RS_PHPCOROUTINES\n' + replacement + '#else\n' + original + '#endif\n}')
    definition = r"""
#ifdef SWOOLE_RS_PHPCOROUTINES
namespace swoole {
struct PHPCoroutineDeferredTasks {
    swr_phpcoroutines_defer_queue *queue;
    PHPCoroutineDeferredTasks() : queue(swr_v1_phpcoroutines_defer_new()) {
        if (!queue) { throw std::bad_alloc(); }
    }
    ~PHPCoroutineDeferredTasks() { swr_v1_phpcoroutines_defer_drop(queue); }
    PHPCoroutineDeferredTasks(const PHPCoroutineDeferredTasks &) = delete;
    PHPCoroutineDeferredTasks &operator=(const PHPCoroutineDeferredTasks &) = delete;
    void push(zend::Function *function) {
        if (!swr_v1_phpcoroutines_defer_push(queue, reinterpret_cast<uintptr_t>(function))) {
            throw std::bad_alloc();
        }
    }
    bool pop(zend::Function **function) {
        uintptr_t token;
        if (!swr_v1_phpcoroutines_defer_pop(queue, &token)) { return false; }
        *function = reinterpret_cast<zend::Function *>(token);
        return true;
    }
};
}
#endif
"""
    result = result.replace('enum sw_exit_flags', definition + '\nenum sw_exit_flags')
    sig = 'static PHP_METHOD(swoole_coroutine, stats) {'
    original = body(source, sig)
    replacement = r"""
    array_init(return_value);
    swr_phpcoroutines_stats_state state{};
    uint8_t observation = 0;
#ifdef SW_USE_IOURING
    decltype(SwooleTG.iouring) iouring = nullptr;
    constexpr uint8_t has_iouring = 1;
#else
    constexpr uint8_t has_iouring = 0;
#endif
    for (;;) {
        const auto plan = swr_v1_phpcoroutines_stats(&state, observation, has_iouring);
        if (plan.action == SWR_CORO_STATS_DONE) { return; }
        zend_long value = 0;
        if (!plan.zero) {
            switch (plan.action) {
            case SWR_CORO_STATS_EVENT: value = sw_reactor() ? sw_reactor()->get_event_num() : 0; break;
            case SWR_CORO_STATS_SIGNAL: value = swoole_signal_get_listener_num(); break;
            case SWR_CORO_STATS_ASYNC: observation = sw_async_threads() != nullptr; continue;
            case SWR_CORO_STATS_AIO_TASK: value = sw_async_threads()->get_task_num(); break;
            case SWR_CORO_STATS_AIO_WORKER: value = sw_async_threads()->get_worker_num(); break;
            case SWR_CORO_STATS_AIO_QUEUE: value = sw_async_threads()->get_queue_size(); break;
            case SWR_CORO_STATS_STACK: value = Coroutine::get_stack_size(); break;
            case SWR_CORO_STATS_COUNT: value = Coroutine::count(); break;
            case SWR_CORO_STATS_PEAK: value = Coroutine::get_peak_num(); break;
            case SWR_CORO_STATS_LAST: value = Coroutine::get_last_cid(); break;
#ifdef SW_USE_IOURING
            case SWR_CORO_STATS_IOURING: iouring = SwooleTG.iouring; observation = iouring != nullptr; continue;
            case SWR_CORO_STATS_IO_TASK: value = iouring->get_task_num(); break;
            case SWR_CORO_STATS_IO_SQ: value = iouring->get_sq_usage_percent(); break;
            case SWR_CORO_STATS_IO_WAITING: value = iouring->get_waiting_task_num(); break;
#endif
            }
        }
        add_assoc_long_ex(return_value, plan.key, plan.key_length, value);
    }
"""
    result = result.replace(sig + original + '}', sig + '\n#ifdef SWOOLE_RS_PHPCOROUTINES\n' + replacement + '#else\n' + original + '#endif\n}')
    sig = 'static PHP_METHOD(swoole_coroutine, resume) {'
    original = body(source, sig)
    replacement = original.replace(
        '    auto coroutine_iterator = user_yield_coros.find(cid);\n    if (coroutine_iterator == user_yield_coros.end()) {',
        '    Coroutine *co;\n    if (!user_yield_coros.take(cid, &co)) {').replace(
        '    Coroutine *co = coroutine_iterator->second;\n    user_yield_coros.erase(cid);',
        '')
    result = result.replace(sig + original + '}', sig + '\n#ifdef SWOOLE_RS_PHPCOROUTINES\n' + replacement + '#else\n' + original + '#endif\n}')
    sig = 'static PHP_METHOD(swoole_coroutine, yield) {'
    original = body(source, sig)
    replacement = original.replace('    user_yield_coros[co->get_cid()] = co;',
        '    user_yield_coros.put(co->get_cid(), co);')
    result = result.replace(sig + original + '}', sig + '\n#ifdef SWOOLE_RS_PHPCOROUTINES\n' + replacement + '#else\n' + original + '#endif\n}')
    result = result.replace('struct AutoloadQueue {\n    Coroutine *coroutine;\n    std::queue<AutoloadContext *> *queue;\n};', r"""#ifdef SWOOLE_RS_PHPCOROUTINES
class AutoloadContextQueue {
    swr_phpcoroutines_autoload_queue *queue;
  public:
    explicit AutoloadContextQueue(Coroutine *owner)
        : queue(swr_v1_phpcoroutines_autoload_owner_try_new(reinterpret_cast<uintptr_t>(owner))) {
        if (!queue) { throw std::bad_alloc(); }
    }
    ~AutoloadContextQueue() { swr_v1_phpcoroutines_autoload_drop(queue); }
    AutoloadContextQueue(const AutoloadContextQueue &) = delete;
    AutoloadContextQueue &operator=(const AutoloadContextQueue &) = delete;
    bool is_owner(Coroutine *owner) const {
        return swr_v1_phpcoroutines_autoload_is_owner(queue, reinterpret_cast<uintptr_t>(owner)) != 0;
    }
    void push(AutoloadContext *context) {
        if (!swr_v1_phpcoroutines_autoload_try_push(queue, reinterpret_cast<uintptr_t>(context))) {
            throw std::bad_alloc();
        }
    }
    bool pop(AutoloadContext **context) {
        uintptr_t token;
        if (!swr_v1_phpcoroutines_autoload_pop(queue, &token)) {
            return false;
        }
        *context = reinterpret_cast<AutoloadContext *>(token);
        return true;
    }
};
#else
struct AutoloadQueue {
    Coroutine *coroutine;
    std::queue<AutoloadContext *> *queue;
};
#endif
""")
    signature = 'static zend_class_entry *swoole_coroutine_autoload(zend_string *name, zend_string *lc_name) {'
    original = body(source, signature)
    replacement = original.replace('    AutoloadQueue queue;\n    queue.coroutine = current;\n    std::queue<AutoloadContext *> queue_object;\n    queue.queue = &queue_object;', '    AutoloadContextQueue queue_object(current);').replace('lc_name, &queue);', 'lc_name, &queue_object);').replace(
        '    while (!queue_object.empty()) {\n        pending_context = queue_object.front();\n        queue_object.pop();',
        '    while (queue_object.pop(&pending_context)) {')
    owner_body = replacement[replacement.index('    AutoloadContextQueue queue_object(current);'):]
    replacement = r"""
    uint32_t stage = 0;
    uint8_t observation = 0;
    Coroutine *current = nullptr;
    zval *z_queue = nullptr;
    AutoloadContextQueue *pending_queue = nullptr;
    for (;;) {
        switch (swr_v1_phpcoroutines_autoload_policy(&stage, observation)) {
        case SWR_CORO_AUTOLOAD_NULL: return nullptr;
        case SWR_CORO_AUTOLOAD_CURRENT:
            current = Coroutine::get_current();
            observation = current != nullptr;
            break;
        case SWR_CORO_AUTOLOAD_DIRECT: return original_zend_autoload(name, lc_name);
        case SWR_CORO_AUTOLOAD_DELETE:
            ZEND_ASSERT(EG(in_autoload) != nullptr);
            zend_hash_del(EG(in_autoload), lc_name);
            observation = SWOOLE_G(in_autoload) != nullptr;
            break;
        case SWR_CORO_AUTOLOAD_INIT:
            ALLOC_HASHTABLE(SWOOLE_G(in_autoload));
            zend_hash_init(SWOOLE_G(in_autoload), 8, nullptr, nullptr, 0);
            break;
        case SWR_CORO_AUTOLOAD_LOOKUP:
            z_queue = zend_hash_find(SWOOLE_G(in_autoload), lc_name);
            observation = z_queue != nullptr;
            break;
        case SWR_CORO_AUTOLOAD_RECURSION:
            pending_queue = (AutoloadContextQueue *) Z_PTR_P(z_queue);
            observation = pending_queue->is_owner(current);
            break;
        case SWR_CORO_AUTOLOAD_WAITER: {
            AutoloadContext context;
            context.coroutine = current;
            context.ce = nullptr;
            pending_queue->push(&context);
            current->yield();
            return context.ce;
        }
        case SWR_CORO_AUTOLOAD_OWNER: {
""" + owner_body + r"""
        }
        }
    }
"""
    result = result.replace(signature + original + '}', signature + '\n#ifdef SWOOLE_RS_PHPCOROUTINES\n' + replacement + '#else\n' + original + '#endif\n}')
    signature = 'long PHPCoroutine::create(zend_fcall_info_cache *fci_cache, uint32_t argc, zval *argv, zval *callable) {'
    original = body(source, signature)
    replacement = r"""
    uint32_t phase = 0;
    uint64_t observation = Coroutine::count();
    const uint64_t max_num = get_max_num();
    for (;;) {
        switch (swr_v1_phpcoroutines_create(&phase, observation, max_num, ZEND_USER_FUNCTION, ZEND_INTERNAL_FUNCTION)) {
        case SWR_CORO_CREATE_LIMIT:
            php_swoole_fatal_error(E_WARNING, "exceed max number of coroutine %zu", (uintmax_t) Coroutine::count());
            return Coroutine::ERR_LIMIT;
        case SWR_CORO_CREATE_HANDLER:
            observation = fci_cache && fci_cache->function_handler;
            break;
        case SWR_CORO_CREATE_INVALID_CACHE:
            php_swoole_fatal_error(E_ERROR, "invalid function call info cache");
            return Coroutine::ERR_INVALID;
        case SWR_CORO_CREATE_TYPE: observation = fci_cache->function_handler->type; break;
        case SWR_CORO_CREATE_INVALID_TYPE:
            php_swoole_fatal_error(E_ERROR, "invalid function type %u", fci_cache->function_handler->type);
            return Coroutine::ERR_INVALID;
        case SWR_CORO_CREATE_ACTIVE: observation = activated; break;
        case SWR_CORO_CREATE_ACTIVATE: activate(); break;
        case SWR_CORO_CREATE_READY:
            Args _args;
            _args.fci_cache = fci_cache;
            _args.argv = argv;
            _args.argc = argc;
            _args.callable = callable;
            save_context(get_context());
            return Coroutine::create(main_func, (void *) &_args);
        }
    }
"""
    result = result.replace(signature + original + '}', signature + '\n#ifdef SWOOLE_RS_PHPCOROUTINES\n' + replacement + '#else\n' + original + '#endif\n}')
    for method, value, kind in [('getPcid', 'ret', 'PARENT'), ('getStackUsage', 'usage', 'STACK')]:
        signature = ('static ' if method == 'getStackUsage' else '') + 'PHP_METHOD(swoole_coroutine, ' + method + ') {'
        original = body(source, signature)
        condition = 'ret == 0' if method == 'getPcid' else 'usage < 0'
        replacement = original.replace(condition,
            'swr_v1_phpcoroutines_context_query(SWR_CORO_QUERY_' + kind + ', nullptr, cid, ' + value + ') == SWR_CORO_QUERY_FALSE')
        result = result.replace(signature + original + '}', signature + '\n#ifdef SWOOLE_RS_PHPCOROUTINES\n' + replacement + '#else\n' + original + '#endif\n}')
    signature = 'static PHP_METHOD(swoole_coroutine, getContext) {'
    original = body(source, signature)
    replacement = original[:original.index('    auto *ctx = static_cast<PHPContext *>(')] + """
    uint32_t stage = 0;
    int64_t observation = 0;
    PHPContext *ctx = nullptr;
    for (;;) {
        switch (swr_v1_phpcoroutines_context_query(SWR_CORO_QUERY_CONTEXT, &stage, cid, observation)) {
        case SWR_CORO_QUERY_CURRENT:
            ctx = static_cast<PHPContext *>(Coroutine::get_current_task());
            observation = ctx != nullptr;
            break;
        case SWR_CORO_QUERY_BY_ID:
            ctx = static_cast<PHPContext *>(Coroutine::get_task_by_cid(cid));
            observation = ctx != nullptr;
            break;
        case SWR_CORO_QUERY_MISSING:
            swoole_set_last_error(SW_ERROR_CO_NOT_EXISTS);
            RETURN_NULL();
        case SWR_CORO_QUERY_CHECK_DESTROYED:
            observation = ctx->context == reinterpret_cast<zend_object *>(INVALID_PTR);
            break;
        case SWR_CORO_QUERY_DESTROYED:
            php_swoole_fatal_error(E_WARNING, "The context of coroutine has been destroyed");
            RETURN_NULL();
        case SWR_CORO_QUERY_HAS_OBJECT: observation = ctx->context != nullptr; break;
        case SWR_CORO_QUERY_INIT_OBJECT:
            object_init_ex(return_value, swoole_coroutine_context_ce);
            ctx->context = Z_OBJ_P(return_value);
            break;
        case SWR_CORO_QUERY_PUBLISH:
            GC_ADDREF(ctx->context);
            RETURN_OBJ(ctx->context);
        }
    }
"""
    result = result.replace(signature + original + '}', signature + '\n#ifdef SWOOLE_RS_PHPCOROUTINES\n' + replacement + '#else\n' + original + '#endif\n}')
    for printing, signature in [(False, 'static PHP_METHOD(swoole_coroutine, getBackTrace) {'),
                                 (True, 'void sw_php_print_backtrace(zend_long cid, zend_long options, zend_long limit, zval *return_value) {')]:
        original = body(source, signature)
        prefix = '' if printing else original[:original.index('    if (!cid || cid == PHPCoroutine::get_cid()) {')]
        invoke = ('sw_php_print_backtrace_impl(plan.skip_last, options, limit);' if printing else
                  'zend_fetch_debug_backtrace(return_value, plan.skip_last, options, limit);')
        clear = 'RETVAL_FALSE; break;' if printing else 'RETURN_FALSE;'
        replacement = prefix + """
    uint32_t stage = 0;
    int64_t observation = 0;
    PHPContext *task = nullptr;
    zend_execute_data *ex_backup = nullptr;
    for (;;) {
        const auto plan = swr_v1_phpcoroutines_trace(&stage, cid, observation, """ + str(int(printing)) + """);
        switch (plan.action) {
        case SWR_CORO_TRACE_CID: observation = PHPCoroutine::get_cid(); break;
        case SWR_CORO_TRACE_SELF:
            """ + invoke + """
            return;
        case SWR_CORO_TRACE_CONTEXT:
            task = PHPCoroutine::get_context_by_cid(cid);
            observation = task != nullptr;
            break;
        case SWR_CORO_TRACE_MISSING: swoole_set_last_error(SW_ERROR_CO_NOT_EXISTS); break;
        case SWR_CORO_TRACE_RETURN_PRESENCE: observation = """ + ('return_value != nullptr' if printing else '1') + """; break;
        case SWR_CORO_TRACE_FALSE: """ + clear + """
        case SWR_CORO_TRACE_SWITCH:
            ex_backup = EG(current_execute_data);
            EG(current_execute_data) = task->execute_data;
            break;
        case SWR_CORO_TRACE_TARGET:
            """ + invoke + """
            break;
        case SWR_CORO_TRACE_RESTORE: EG(current_execute_data) = ex_backup; break;
        case SWR_CORO_TRACE_DONE: return;
        }
    }
"""
        result = result.replace(signature + original + '}', signature + '\n#ifdef SWOOLE_RS_PHPCOROUTINES\n' + replacement + '#else\n' + original + '#endif\n}')
    result = replace_minit(source, result, 0, body)
    for transform in (replace_transfers, replace_config_cpp, replace_fibers,
                      replace_activated_cpp, replace_exits, replace_metadata_cpp, replace_controls, replace_join, replace_terminal, replace_lifecycle, replace_interrupt_cpp, replace_ordinary, replace_context_lifecycle, replace_method_catalogue):
        result = transform(source, result, body)
    return result


def system_selected(source):
    if hashlib.sha256(source.encode()).hexdigest() != '1b2a3d669d95bc7e524787c254ecb38467fa5e2050c1544b360f54e0cbc8c869':
        raise ValueError('Pinned System source changed')
    result = source.replace('#include <string>', '#include <string>\n#ifdef SWOOLE_RS_PHPCOROUTINES\n#include "swoole_rs_phpcoroutines.h"\n#endif')
    config = '    const swr_phpcoroutines_file_config config{SW_FILE_LOCK, SW_FILE_APPEND, O_CREAT | O_WRONLY | O_NOFOLLOW, O_APPEND, O_TRUNC};\n'
    for method, argument in [('readFile', 'filename'), ('writeFile', 'filename'), ('statvfs', 'path'), ('sleep', None)]:
        signature = 'PHP_METHOD(swoole_coroutine_system, ' + method + ') {'
        original = body(source, signature)
        replacement = original
        if method == 'sleep':
            replacement = replacement.replace('seconds < SW_TIMER_MIN_SEC', '!swr_v1_phpcoroutines_system_sleep(seconds, SW_TIMER_MIN_SEC)')
        else:
            guard = '    if (!' + argument + ' || !*' + argument + ') {'
            replacement = replacement.replace(guard, config + '    const auto plan = swr_v1_phpcoroutines_system_file(' + argument + ' && *' + argument + ', ' + ('0' if method == 'statvfs' else 'flags') + ', &config);\n    if (!plan.accepted) {')
            replacement = replacement.replace('flags & SW_FILE_LOCK', 'plan.lock')
            if method == 'writeFile':
                begin = replacement.index('    int _flags = O_CREAT | O_WRONLY | O_NOFOLLOW;')
                end = replacement.index('    ssize_t retval', begin)
                replacement = replacement[:begin] + replacement[end:]
                replacement = replacement.replace('plan.lock, _flags)', 'plan.lock, plan.open)')
        if method == 'sleep':
            replacement = replacement.replace('    RETURN_BOOL(System::sleep(seconds) == 0);',
                '    const int status = System::sleep(seconds);\n    RETURN_BOOL(swr_v1_phpcoroutines_system_complete(SWR_CORO_RESULT_SLEEP, nullptr, status, 0).value);')
        elif method == 'readFile':
            replacement = replacement.replace('    if (result == nullptr) {',
                '    if (swr_v1_phpcoroutines_system_complete(SWR_CORO_RESULT_READ, nullptr, result != nullptr, 0).action == SWR_CORO_RESULT_FALSE) {')
        elif method == 'writeFile':
            replacement = replacement.replace('    if (retval < 0) {',
                '    const auto completion = swr_v1_phpcoroutines_system_complete(SWR_CORO_RESULT_WRITE, nullptr, retval, 0);\n    if (completion.action == SWR_CORO_RESULT_FALSE) {').replace('RETURN_LONG(retval);', 'RETURN_LONG(completion.value);')
        elif method == 'statvfs':
            start = replacement.index('    array_init(return_value);')
            fields = 'bsize frsize blocks bfree bavail files ffree favail fsid flag namemax'.split()
            cases = '\n'.join(f'            case {i}: add_assoc_long(return_value, field.key, _stat.f_{key}); break;' for i, key in enumerate(fields))
            replacement = replacement[:start] + """
    swr_phpcoroutines_result_state state{};
    for (;;) {
        const auto field = swr_v1_phpcoroutines_system_complete(SWR_CORO_RESULT_STATVFS, &state, 0, 0);
        if (field.action == SWR_CORO_RESULT_DONE) { return; }
        if (field.action == SWR_CORO_RESULT_ARRAY) { array_init(return_value); continue; }
        switch (field.index) {
""" + cases + """
        }
    }
"""
        result = result.replace(signature + original + '}', signature + '\n#ifdef SWOOLE_RS_PHPCOROUTINES\n' + replacement + '#else\n' + original + '#endif\n}')
    for signature, length in [('PHP_FUNCTION(swoole_coroutine_gethostbyname) {', 'l_domain_name'),
                              ('PHP_METHOD(swoole_coroutine_system, getaddrinfo) {', 'l_hostname')]:
        original = body(source, signature)
        replacement = original.replace('    if (' + length + ' == 0) {',
            '    const auto admission = swr_v1_phpcoroutines_system_address(' + length + ', family, AF_INET, AF_INET6);\n    if (admission == SWR_CORO_ADDRESS_EMPTY) {').replace('    if (family != AF_INET && family != AF_INET6) {', '    if (admission == SWR_CORO_ADDRESS_FAMILY) {')
        if length == 'l_domain_name':
            replacement = replacement.replace('    if (address.empty()) {',
                '    if (swr_v1_phpcoroutines_system_complete(SWR_CORO_RESULT_HOST, nullptr, 0, address.length()).action == SWR_CORO_RESULT_FALSE) {')
        else:
            replacement = replacement[:replacement.index('    if (result.empty()) {')] + """
    swr_phpcoroutines_result_state state{};
    for (;;) {
        const auto plan = swr_v1_phpcoroutines_system_complete(SWR_CORO_RESULT_ADDRINFO, &state, 0, result.size());
        switch (plan.action) {
        case SWR_CORO_RESULT_FALSE: RETURN_FALSE;
        case SWR_CORO_RESULT_DONE: return;
        case SWR_CORO_RESULT_ARRAY: array_init(return_value); break;
        case SWR_CORO_RESULT_ITEM: {
            auto &i = result[plan.index];
            add_next_index_stringl(return_value, i.c_str(), i.length());
            break;
        }
        }
    }
"""
        result = result.replace(signature + original + '}', signature + '\n#ifdef SWOOLE_RS_PHPCOROUTINES\n' + replacement + '#else\n' + original + '#endif\n}')
    return replace_method_catalogue(source, replace_system_controls(source, replace_minit(source, result, 2, body), body), body)


HEADER_DEST = 'ext-src/php_swoole_coroutine.h'
HEADER_SHA = '4e6c50c8aae126a9522d1791a846ed424f36c6e4128eccec61b611be129ae22f'


HEADER_SIGNATURES = [
    'static inline long get_cid() {', 'static inline long get_pcid(long cid = 0) {',
    'static inline long get_elapsed(long cid = 0) {', 'static inline PHPContext *get_context() {',
    'static inline PHPContext *get_origin_context(PHPContext *ctx) {',
    'static inline PHPContext *get_context_by_cid(long cid) {',
    'static inline ssize_t get_stack_usage(long cid) {', 'static inline bool is_schedulable(PHPContext *ctx) {',
    'static inline bool enable_scheduler() {', 'static inline bool disable_scheduler() {',
    'static inline long get_execute_time(long cid = 0) {', 'static void record_last_msec(PHPContext *ctx) {',
    ACTIVATED_SIGNATURE,
]


def header_selected(source):
    if hashlib.sha256(source.encode()).hexdigest() != HEADER_SHA:
        raise ValueError('Pinned coroutine header changed')
    result = source.replace('struct PHPContext {', '#ifdef SWOOLE_RS_PHPCOROUTINES\nstruct PHPCoroutineDeferredTasks;\n#endif\n\nstruct PHPContext {')
    result = result.replace('    std::stack<zend::Function *> *defer_tasks;', '#ifdef SWOOLE_RS_PHPCOROUTINES\n    PHPCoroutineDeferredTasks *defer_tasks;\n#else\n    std::stack<zend::Function *> *defer_tasks;\n#endif')
    result = result.replace('#include "swoole_coroutine.h"', '#include "swoole_coroutine.h"\n#ifdef SWOOLE_RS_PHPCOROUTINES\n#include "swoole_rs_phpcoroutines.h"\n#endif')
    replacements = {
        HEADER_SIGNATURES[0]: """
        return swr_v1_phpcoroutines_context_route(SWR_CORO_CONTEXT_ACTIVE, 0, activated)
                   ? Coroutine::get_current_cid() : -1;
""",
        HEADER_SIGNATURES[2]: """
        return swr_v1_phpcoroutines_context_route(SWR_CORO_CONTEXT_ACTIVE, 0, activated)
                   ? Coroutine::get_elapsed(cid) : -1;
""",
        HEADER_SIGNATURES[3]: """
        PHPContext *ctx = (PHPContext *) Coroutine::get_current_task();
        return swr_v1_phpcoroutines_context_route(SWR_CORO_CONTEXT_FALLBACK, 0, ctx != nullptr) == SWR_CORO_CONTEXT_MAIN
                   ? &main_context : ctx;
""",
        HEADER_SIGNATURES[4]: """
        Coroutine *co = ctx->co->get_origin();
        return swr_v1_phpcoroutines_context_route(SWR_CORO_CONTEXT_FALLBACK, 0, co != nullptr) == SWR_CORO_CONTEXT_MAIN
                   ? &main_context : (PHPContext *) co->get_task();
""",
        HEADER_SIGNATURES[5]: """
        return swr_v1_phpcoroutines_context_route(SWR_CORO_CONTEXT_BY_ID, cid, 0) == SWR_CORO_CONTEXT_MAIN
                   ? &main_context : (PHPContext *) Coroutine::get_task_by_cid(cid);
""",
        HEADER_SIGNATURES[6]: """
        swr_phpcoroutines_stack_state state = {cid, 0, 0, 0};
        int64_t observation = 0;
        size_t bytes = 0;
        PHPContext *ctx = nullptr;
        zend_vm_stack stack = nullptr;
        for (;;) {
            switch (swr_v1_phpcoroutines_stack_step(&state, observation, bytes)) {
            case SWR_CORO_STACK_CID: observation = PHPCoroutine::get_cid(); break;
            case SWR_CORO_STACK_CONTEXT:
                ctx = (PHPContext *) PHPCoroutine::get_context_by_cid(state.cid);
                observation = ctx != nullptr;
                break;
            case SWR_CORO_STACK_MISSING:
                swoole_set_last_error(SW_ERROR_CO_NOT_EXISTS);
                return -1;
            case SWR_CORO_STACK_CURRENT: stack = EG(vm_stack); observation = stack != nullptr; break;
            case SWR_CORO_STACK_SAVED: stack = ctx->vm_stack; observation = stack != nullptr; break;
            case SWR_CORO_STACK_BYTES: bytes = (stack->end - stack->top) * sizeof(zval); break;
            case SWR_CORO_STACK_NEXT: stack = stack->prev; observation = stack != nullptr; break;
            case SWR_CORO_STACK_DONE: return state.usage;
            }
        }
""",
        HEADER_SIGNATURES[10]: """
        return swr_v1_phpcoroutines_context_route(SWR_CORO_CONTEXT_ACTIVE, 0, activated)
                   ? Coroutine::get_execute_time(cid) : -1;
""",
    }
    for signature, replacement in replacements.items():
        original = body(source, signature)
        result = result.replace(signature + original + '}', signature + '\n#ifdef SWOOLE_RS_PHPCOROUTINES' +
                                replacement + '#else' + original + '#endif\n    }')
    return replace_interrupt_header(source, replace_metadata_header(source, replace_activated_header(source, replace_config_header(source, result, body), body), body), body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    args = parser.parse_args()
    source = (args.source / DEST).read_text()
    overlay = selected(source)
    folder = ROOT / 'migration/patches/phpcoroutines'
    patch = folder / '0001-scheduler-queue.patch'
    text = 'diff --git a/' + DEST + ' b/' + DEST + '\n' + ''.join(difflib.unified_diff(
        source.splitlines(True), overlay.splitlines(True), fromfile='a/' + DEST, tofile='b/' + DEST))
    patch.write_text(text)
    coroutine_dest = 'ext-src/swoole_coroutine.cc'
    coroutine = (args.source / coroutine_dest).read_text()
    coroutine_patch = folder / '0002-user-yield-registry.patch'
    coroutine_patch.write_text('diff --git a/' + coroutine_dest + ' b/' + coroutine_dest + '\n' + ''.join(difflib.unified_diff(
        coroutine.splitlines(True), coroutine_selected(coroutine).splitlines(True),
        fromfile='a/' + coroutine_dest, tofile='b/' + coroutine_dest)))
    system_dest = 'ext-src/swoole_coroutine_system.cc'
    system_source = (args.source / system_dest).read_text()
    system_patch = folder / '0003-system-file-admission.patch'
    system_patch.write_text('diff --git a/' + system_dest + ' b/' + system_dest + '\n' + ''.join(difflib.unified_diff(
        system_source.splitlines(True), system_selected(system_source).splitlines(True),
        fromfile='a/' + system_dest, tofile='b/' + system_dest)))
    header = (args.source / HEADER_DEST).read_text()
    header_patch = folder / '0004-deferred-context-header.patch'
    header_patch.write_text('diff --git a/' + HEADER_DEST + ' b/' + HEADER_DEST + '\n' + ''.join(difflib.unified_diff(
        header.splitlines(True), header_selected(header).splitlines(True),
        fromfile='a/' + HEADER_DEST, tofile='b/' + HEADER_DEST)))
    (folder / 'manifest.json').write_text(json.dumps(dict(upstream_commit=PIN, patches=[dict(
        path=p.name, sha256=hashlib.sha256(p.read_bytes()).hexdigest(), upstream_paths=[dest])
        for p, dest in [(patch, DEST), (coroutine_patch, coroutine_dest), (system_patch, system_dest), (header_patch, HEADER_DEST)]]), indent=2) + '\n')


if __name__ == '__main__':
    main()
