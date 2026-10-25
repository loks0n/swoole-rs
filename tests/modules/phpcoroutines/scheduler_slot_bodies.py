"""Whole Scheduler list cell/repetition custody, frozen APIs/layouts unchanged."""
import re
ADD = 'static void scheduler_add_task(SchedulerObject *s, SchedulerTask *task, zend_long count) {'
FREE = 'static void scheduler_free_object(zend_object *object) {'
START = 'static PHP_METHOD(swoole_coroutine_scheduler, start) {'


def replace_scheduler_slots(source, result, body):
    native_add = 'static void scheduler_add_task(SchedulerObject *s, SchedulerTask *task) {'
    original_add = body(source, native_add)
    new = '''
    if (!swr_v1_phpcoroutines_scheduler_prepare_slot(&s->list)) { throw std::bad_alloc(); }
    sw_zend_fci_cache_persist(&task->fci_cache);
    sw_zend_fci_params_persist(&task->fci);
    if (!swr_v1_phpcoroutines_scheduler_try_push_slot(&s->list, reinterpret_cast<uintptr_t>(task), count)) {
        throw std::bad_alloc();
    }
'''
    result = result.replace(native_add + original_add + '}', '#ifdef SWOOLE_RS_PHPCOROUTINES\n' + ADD + new + '}\n#else\n' + native_add + original_add + '}\n#endif')
    original = body(source, FREE)
    selected = '''
    SchedulerObject *s = scheduler_get_object(object);
    swr_phpcoroutines_scheduler_task next{};
    while (swr_v1_phpcoroutines_scheduler_next_slot(&s->list, &next) == SWR_CORO_SCHED_SLOT_TASK) {
        auto *task = reinterpret_cast<SchedulerTask *>(next.token);
        sw_zend_fci_cache_discard(&task->fci_cache);
        sw_zend_fci_params_discard(&task->fci);
        efree(task);
    }
    swr_v1_phpcoroutines_scheduler_drop_slot(&s->list);
    zend_object_std_dtor(&s->std);
'''
    result = result.replace(FREE + body(result,FREE) + '}', FREE + '\n#ifdef SWOOLE_RS_PHPCOROUTINES\n' + selected + '#else\n' + original + '#endif\n}')
    original = body(source, START)
    current = body(result, START)
    prefix, fallback = current.split('#else\n',1)
    old = '''    if (!s->list) {
        php_swoole_fatal_error(E_WARNING, "no coroutine task");
        RETURN_FALSE;
    }

    swr_phpcoroutines_scheduler_task next;
    while (swr_v1_phpcoroutines_scheduler_pop(s->list, &next)) {'''
    new = '''    swr_phpcoroutines_scheduler_task next{};
    uint32_t next_kind = swr_v1_phpcoroutines_scheduler_next_slot(&s->list, &next);
    if (next_kind == SWR_CORO_SCHED_SLOT_ABSENT) {
        php_swoole_fatal_error(E_WARNING, "no coroutine task");
        RETURN_FALSE;
    }

    while (next_kind == SWR_CORO_SCHED_SLOT_TASK) {'''
    if prefix.count(old)!=1: raise ValueError('Selected start absent/empty ordering changed')
    prefix = prefix.replace(old,new).replace('        for (uint64_t i = 0; i < next.repetitions; i++) {', '''        swr_phpcoroutines_repeat_state repeat{static_cast<int64_t>(next.repetitions), 0, 0};
        while (swr_v1_phpcoroutines_repeat(&repeat)) {''')
    prefix = prefix.replace('        efree(task);\n    }', '        efree(task);\n        next_kind = swr_v1_phpcoroutines_scheduler_next_slot(&s->list, &next);\n    }')
    prefix = prefix.replace('    swr_v1_phpcoroutines_scheduler_drop(s->list);\n    s->list = nullptr;', '    swr_v1_phpcoroutines_scheduler_drop_slot(&s->list);')
    if re.search(r'(?<!&)\bs->list\b', prefix): raise ValueError('Native list cell read/publication remains')
    result = result.replace(START + current + '}', START + prefix + '#else\n' + fallback + '}')
    return result
