"""Select complete context-transfer ordering without interpreting Zend memory."""
from metadata_bodies import silence

SIGNATURES = [f'{prefix}void PHPCoroutine::{name}(PHPContext *ctx) {{'
              for prefix, name in [('inline ', 'save_vm_stack'), ('inline ', 'restore_vm_stack'),
                                   ('inline ', 'save_og'), ('inline ', 'restore_og'),
                                   ('', 'save_bg'), ('', 'restore_bg'),
                                   ('', 'save_context'), ('', 'restore_context')]]
KINDS = ['SAVE_VM', 'RESTORE_VM', 'SAVE_OUTPUT', 'RESTORE_OUTPUT',
         'SAVE_BASIC', 'RESTORE_BASIC', 'SAVE_CONTEXT', 'RESTORE_CONTEXT']
NOTIFICATION_SIGNATURES = ['void PHPCoroutine::on_yield(void *arg) {',
                           'void PHPCoroutine::on_resume(void *arg) {']


def replace_transfers(source, result, body):
    for index, (signature, kind) in enumerate(zip(SIGNATURES, KINDS)):
        original = body(source, signature)
        cases = [('DONE', 'return;')]
        if index < 2:
            prefix = original[:original.index('    if (UNEXPECTED(ctx->in_silence)) {')]
            stack = original.split('#ifdef ZEND_CHECK_STACK_LIMIT\n', 1)[1].split('#endif', 1)[0]
            kind += '_METADATA'
            cases += [('VM', prefix), ('SILENCE', silence('SAVE' if index == 0 else 'RESTORE')),
                      ('STACK_LIMIT', '#ifdef ZEND_CHECK_STACK_LIMIT\n' + stack + '#endif\n')]
        elif index < 4:
            condition = 'OG(handlers).elements' if index == 2 else 'ctx->output_ptr'
            effect = body(original, f'if ({condition}) {{')
            cases += [('OUTPUT_PRESENCE', f'observation = {condition} != 0;'), ('OUTPUT', effect)]
            if index == 2:
                cases += [('CLEAR_OUTPUT', 'ctx->output_ptr = nullptr;')]
        elif index < 6:
            for field, action in [('serialize_lock', 'LOCK'), ('serialize.data', 'SERIALIZE'), ('unserialize.data', 'UNSERIALIZE')]:
                condition = 'BG(' + field.split('.')[0] + ')' + ('.data' if '.data' in field else '') if index == 4 else 'ctx->' + field
                effect = body(original, f'if ({condition}) {{')
                cases += [(action + '_PRESENCE', f'observation = {condition} != 0;'), (action, effect)]
        else:
            direction = 'save' if index == 6 else 'restore'
            cases += [('CALL_VM', f'{direction}_vm_stack(ctx);'),
                      ('CALL_OUTPUT', f'{direction}_og(ctx);'), ('CALL_BASIC', f'{direction}_bg(ctx);')]
        cap = '''    uint8_t stack_limit = 0;
#ifdef ZEND_CHECK_STACK_LIMIT
    stack_limit = 1;
#endif
''' if index < 2 else '    constexpr uint8_t stack_limit = 0;\n'
        replacement = '\n    uint32_t stage = 0;\n    uint8_t observation = 0;\n' + cap + '''    for (;;) {
        switch (swr_v1_phpcoroutines_transfer(&stage, SWR_CORO_TRANSFER_''' + kind + ''', observation, stack_limit)) {
'''
        for action, statements in cases:
            replacement += '        case SWR_CORO_TRANSFER_' + action + ': {\n' + statements.strip('\n') + '\n'
            if action != 'DONE':
                replacement += '            break;\n'
            replacement += '        }\n'
        replacement += '        }\n    }\n'
        result = result.replace(signature + original + '}', signature + '\n#ifdef SWOOLE_RS_PHPCOROUTINES\n' + replacement + '#else\n' + original + '#endif\n}')
    for index, signature in enumerate(NOTIFICATION_SIGNATURES):
        original = body(source, signature)
        prefix = original[:original.index('    fiber_context_switch_try_notify(')]
        kind, event = ('ON_YIELD', 'yield') if index == 0 else ('ON_RESUME', 'resume')
        from_ctx, to_ctx = ('ctx', 'origin_ctx') if index == 0 else ('current_ctx', 'ctx')
        fiber = f'fiber_context_switch_try_notify({from_ctx}, {to_ctx});'
        save, restore = f'save_context({from_ctx});', f'restore_context({to_ctx});'
        trace = next(line.strip() for line in original.splitlines() if 'swoole_trace_log(' in line)
        for statement in [fiber, save, restore, f'(*ctx->on_{event})(ctx);']:
            if statement not in original:
                raise ValueError('Pinned transfer notification effects changed')
        replacement = prefix + '''    uint32_t stage = 0;
    uint8_t observation = 0;
    for (;;) {
        switch (swr_v1_phpcoroutines_transfer(&stage, SWR_CORO_TRANSFER_''' + kind + ''', observation, 0)) {
        case SWR_CORO_TRANSFER_DONE: return;
        case SWR_CORO_TRANSFER_FIBER: ''' + fiber + ''' break;
        case SWR_CORO_TRANSFER_SAVE: ''' + save + ''' break;
        case SWR_CORO_TRANSFER_RESTORE: ''' + restore + ''' break;
'''
        if index == 1:
            replacement += '        case SWR_CORO_TRANSFER_RECORD: record_last_msec(ctx); break;\n'
        replacement += f'''        case SWR_CORO_TRANSFER_CALLBACK_PRESENCE: observation = ctx->on_{event} != nullptr; break;
        case SWR_CORO_TRANSFER_CALLBACK: (*ctx->on_{event})(ctx); break;
        case SWR_CORO_TRANSFER_TRACE: {trace} break;
        }}
    }}
'''
        result = result.replace(signature + original + '}', signature + '\n#ifdef SWOOLE_RS_PHPCOROUTINES\n' + replacement + '#else' + original + '#endif\n}')
    for signature, kind, prefix, cases in [
        ('static void coro_interrupt_resume(void *data) {', 'INTERRUPT_RESUME',
         '    auto *co = static_cast<Coroutine *>(data);\n', [
             ('CO_PRESENCE', 'observation = co != nullptr;'),
             ('CO_ENDED', 'observation = co->is_end();'),
             ('TRACE', 'swoole_trace_log(SW_TRACE_COROUTINE, "interrupt_callback cid=%ld ", co->get_cid());'),
             ('RESUME', 'co->resume();')]),
        ('static void coro_interrupt_function(zend_execute_data *execute_data) {', 'INTERRUPT_FUNCTION',
         '    PHPContext *task = PHPCoroutine::get_context();\n', [
             ('TASK_PRESENCE', 'observation = task != nullptr;'),
             ('TASK_CO_PRESENCE', 'observation = task->co != nullptr;'),
             ('SCHEDULABLE', 'observation = PHPCoroutine::is_schedulable(task);'),
             ('DEFER', 'swoole_event_defer(coro_interrupt_resume, (void *) task->co);'),
             ('YIELD', 'task->co->yield();'),
             ('CALLBACK_PRESENCE', 'observation = orig_interrupt_function != nullptr;'),
             ('CALLBACK', 'orig_interrupt_function(execute_data);')]),
    ]:
        original = body(source, signature)
        if not original.startswith('\n' + prefix):
            raise ValueError('Pinned interrupt Native prefix changed')
        replacement = '\n' + prefix + '''    uint32_t stage = 0;
    uint8_t observation = 0;
    for (;;) {
        switch (swr_v1_phpcoroutines_transfer(&stage, SWR_CORO_TRANSFER_''' + kind + ''', observation, 0)) {
        case SWR_CORO_TRANSFER_DONE: return;
'''
        for action, statement in cases:
            replacement += '        case SWR_CORO_TRANSFER_' + action + ': ' + statement + ' break;\n'
        replacement += '        }\n    }\n'
        result = result.replace(signature + original + '}', signature + '\n#ifdef SWOOLE_RS_PHPCOROUTINES\n' + replacement + '#else' + original + '#endif\n}')
    return result
