"""Selected whole MINIT bodies; typed Zend effects stay native after Rust plans."""

def selected_minit(kind):
    preamble = '''
    (void) module_number;
    swr_phpcoroutines_bootstrap_state state{};
    uint8_t observation = 0;
    zend_class_entry **slot = nullptr;
'''
    if kind == 0:
        preamble += '''#if PHP_VERSION_ID < 80400
    const uint8_t exit_opcode = 1;
#else
    const uint8_t exit_opcode = 0;
#endif
'''
    else:
        preamble += '    const uint8_t exit_opcode = 0;\n'
    common = '''
    for (;;) {
        const auto plan = swr_v1_phpcoroutines_bootstrap(&state, KIND, observation, exit_opcode);
        switch (plan.action) {
        case SWR_CORO_BOOT_DONE: return;
        case SWR_CORO_BOOT_SHORTNAME: observation = SWOOLE_G(use_shortname); break;
        case SWR_CORO_BOOT_ALIAS: sw_zend_register_class_alias(plan.name, plan.length, *slot); break;
'''.replace('KIND', str(kind))
    if kind == 0:
        effects = '''
        case SWR_CORO_BOOT_CLASS: {
            const zend_function_entry *methods = nullptr;
            zend_class_entry *const *parent_slot = nullptr;
            switch (plan.id) {
            case 0: slot = &swoole_coroutine_util_ce; methods = swoole_coroutine_methods; break;
            case 1: slot = &swoole_coroutine_iterator_ce; parent_slot = &spl_ce_ArrayIterator; break;
            case 2: slot = &swoole_coroutine_context_ce; parent_slot = &spl_ce_ArrayObject; break;
            case 3: slot = &swoole_exit_exception_ce; methods = swoole_exit_exception_methods; parent_slot = &swoole_exception_ce; break;
            case 4: slot = &swoole_coroutine_canceled_exception_ce; parent_slot = &zend_ce_exception; break;
            case 5: slot = &swoole_coroutine_timeout_exception_ce; parent_slot = &zend_ce_exception; break;
            default: assert(false); return;
            }
            swr_phpcoroutines_register_class(plan, slot, methods, parent_slot);
            break;
        }
        case SWR_CORO_BOOT_COPY:
            switch (plan.id) {
            case 3: memcpy(&swoole_exit_exception_handlers, &swoole_exception_handlers, sizeof(zend_object_handlers)); break;
            case 4: memcpy(&swoole_coroutine_canceled_exception_handlers, zend_get_std_object_handlers(), sizeof(zend_object_handlers)); break;
            case 5: memcpy(&swoole_coroutine_timeout_exception_handlers, zend_get_std_object_handlers(), sizeof(zend_object_handlers)); break;
            default: assert(false); return;
            }
            break;
        case SWR_CORO_BOOT_FIXUP:
            switch (plan.id) {
            case 0: SW_SET_CLASS_CREATE(swoole_coroutine_util, sw_zend_create_object_deny); break;
            case 4: swoole_coroutine_canceled_exception_ce->ce_flags |= ZEND_ACC_FINAL; break;
            case 5: swoole_coroutine_timeout_exception_ce->ce_flags |= ZEND_ACC_FINAL; break;
            default: assert(false); return;
            }
            break;
        case SWR_CORO_BOOT_CONSTANT: {
            zend_long value = 0;
            switch (plan.id) {
            case 0: value = SW_DEFAULT_MAX_CORO_NUM; break;
            case 1: value = Coroutine::MAX_NUM_LIMIT; break;
            case 2: value = Coroutine::STATE_INIT; break;
            case 3: value = Coroutine::STATE_WAITING; break;
            case 4: value = Coroutine::STATE_RUNNING; break;
            case 5: value = Coroutine::STATE_END; break;
            case 6: value = SW_EXIT_IN_COROUTINE; break;
            case 7: value = SW_EXIT_IN_SERVER; break;
            default: assert(false); return;
            }
            zend_register_long_constant(plan.name, plan.length, value, CONST_CS | CONST_PERSISTENT, module_number);
            break;
        }
        case SWR_CORO_BOOT_PROPERTY:
            zend_declare_property_long(swoole_exit_exception_ce, plan.name, plan.length, 0, ZEND_ACC_PRIVATE);
            break;
        case SWR_CORO_BOOT_CLI: observation = SWOOLE_G(cli); break;
        case SWR_CORO_BOOT_EFFECT:
            switch (plan.id) {
#if PHP_VERSION_ID < 80400
            case 0:
                ori_exit_handler = zend_get_user_opcode_handler(ZEND_EXIT);
                zend_set_user_opcode_handler(ZEND_EXIT, coro_exit_handler);
                break;
#endif
            case 1:
                ori_begin_silence_handler = zend_get_user_opcode_handler(ZEND_BEGIN_SILENCE);
                zend_set_user_opcode_handler(ZEND_BEGIN_SILENCE, coro_begin_silence_handler);
                break;
            case 2:
                ori_end_silence_handler = zend_get_user_opcode_handler(ZEND_END_SILENCE);
                zend_set_user_opcode_handler(ZEND_END_SILENCE, coro_end_silence_handler);
                break;
            case 3:
                original_zend_autoload = zend_autoload;
                zend_autoload = swoole_coroutine_autoload;
                SWOOLE_G(in_autoload) = nullptr;
                break;
            case 4:
                memset(&swoole_coroutine_internal_function, 0, sizeof(swoole_coroutine_internal_function));
                swoole_coroutine_internal_function.common.type = ZEND_INTERNAL_FUNCTION;
                break;
            default: assert(false); return;
            }
            break;
'''
    elif kind == 1:
        effects = '''
        case SWR_CORO_BOOT_CLASS:
            slot = &swoole_coroutine_scheduler_ce;
            swr_phpcoroutines_register_class(plan, slot, swoole_coroutine_scheduler_methods, nullptr);
            break;
        case SWR_CORO_BOOT_COPY:
            memcpy(&swoole_coroutine_scheduler_handlers, zend_get_std_object_handlers(), sizeof(zend_object_handlers));
            break;
        case SWR_CORO_BOOT_FIXUP:
            SW_SET_CLASS_NOT_SERIALIZABLE(swoole_coroutine_scheduler);
            SW_SET_CLASS_CLONEABLE(swoole_coroutine_scheduler, sw_zend_class_clone_deny);
            SW_SET_CLASS_UNSET_PROPERTY_HANDLER(swoole_coroutine_scheduler, sw_zend_class_unset_property_deny);
            SW_SET_CLASS_CREATE_WITH_ITS_OWN_HANDLERS(swoole_coroutine_scheduler);
            SW_SET_CLASS_CUSTOM_OBJECT(
                swoole_coroutine_scheduler, scheduler_create_object, scheduler_free_object, SchedulerObject, std);
            swoole_coroutine_scheduler_ce->ce_flags |= ZEND_ACC_FINAL;
            break;
'''
    else:
        effects = '''
        case SWR_CORO_BOOT_CLASS:
            slot = &swoole_coroutine_system_ce;
            swr_phpcoroutines_register_class(plan, slot, swoole_coroutine_system_methods, nullptr);
            break;
        case SWR_CORO_BOOT_FIXUP: SW_SET_CLASS_CREATE(swoole_coroutine_system, sw_zend_create_object_deny); break;
        case SWR_CORO_BOOT_CONSTANT: zend::add_constant(plan.name, SW_FILE_LOCK); break;
'''
    return preamble + common + effects + '''
        default: assert(false); return;
        }
    }
'''


def replace_minit(source, selected, kind, body):
    name = ['php_swoole_coroutine_minit', 'php_swoole_coroutine_scheduler_minit', 'php_swoole_coroutine_system_minit'][kind]
    signature = 'void ' + name + '(int module_number) {'
    original = body(source, signature)
    selected = selected.replace('#include "swoole_rs_phpcoroutines.h"', '#include "swoole_rs_phpcoroutines.h"\n#include "phpcoroutines_registration.h"')
    return selected.replace(signature + original + '}', signature + '\n#ifdef SWOOLE_RS_PHPCOROUTINES\n' + selected_minit(kind) + '#else\n' + original + '#endif\n}')
