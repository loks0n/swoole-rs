"""Whole primitive context custody; addresses/effects stay Native, no value mirror."""
FIELDS = {'in_silence': 'swr_phpcoroutines_scheduler_phase',
          'enable_scheduler': 'swr_phpcoroutines_scheduler_phase',
          'ori_error_reporting': 'swr_phpcoroutines_error_cell',
          'tmp_error_reporting': 'swr_phpcoroutines_error_cell',
          'fiber_init_notified': 'swr_phpcoroutines_scheduler_phase',
          'pcid': 'swr_phpcoroutines_parent_cell',
          'last_msec': 'swr_phpcoroutines_clock_cell'}


def call(kind, cells='cells', value='0'):
    return f'swr_v1_phpcoroutines_metadata(&stage, SWR_CORO_METADATA_{kind}, &{cells}, {value}, 0)'


def silence(kind, context='ctx'):
    return f'''const auto cells = php_coroutine_metadata_cells({context});
    uint32_t stage = 0;
    int64_t observation = 0;
    for (;;) {{
        const auto part = swr_v1_phpcoroutines_metadata(&stage, SWR_CORO_METADATA_{kind}, &cells, observation, 0);
        switch (part.action) {{
        case SWR_CORO_METADATA_DONE: goto silence_done;
        case SWR_CORO_METADATA_READ_ERROR: observation = EG(error_reporting); break;
        case SWR_CORO_METADATA_WRITE_ERROR: EG(error_reporting) = static_cast<int>(part.value); break;
        }}
    }}
    silence_done:;'''


def replace_active(source, result, signature, body, transform):
    original = body(source, signature)
    before = body(result, signature)
    marker = '#else' + original
    if marker in before:
        index = before.rindex(marker)
        after = transform(before[:index]) + before[index:]
    else:
        after = '\n#ifdef SWOOLE_RS_PHPCOROUTINES\n' + transform(original) + '#else' + original + '#endif\n'
    return result.replace(signature + before + '}', signature + after + '}')


def replace_metadata_header(source, result, body):
    for field, selected_type in FIELDS.items():
        native_type = {'ori_error_reporting': 'int', 'tmp_error_reporting': 'int', 'pcid': 'long', 'last_msec': 'int64_t'}.get(field, 'bool')
        declaration = f'    {native_type} {field};'
        if source.count(declaration) != 1:
            raise ValueError('Pinned primitive context declaration changed: ' + field)
        result = result.replace(declaration, '#ifdef SWOOLE_RS_PHPCOROUTINES\n    ' + selected_type + ' ' + field + ';\n#else\n' + declaration + '\n#endif')
    helper = '''
#ifdef SWOOLE_RS_PHPCOROUTINES
static inline swr_phpcoroutines_context_cells php_coroutine_metadata_cells(PHPContext *ctx) {
    if (!ctx) {
        return {};
    }
    return {&ctx->in_silence, &ctx->enable_scheduler, &ctx->ori_error_reporting,
            &ctx->tmp_error_reporting, &ctx->fiber_init_notified, &ctx->pcid, &ctx->last_msec};
}
'''
    for native_type, selected_type in [('bool', 'swr_phpcoroutines_scheduler_phase'), ('int', 'swr_phpcoroutines_error_cell'), ('long', 'swr_phpcoroutines_parent_cell'), ('int64_t', 'swr_phpcoroutines_clock_cell')]:
        helper += f'static_assert(sizeof({native_type}) == sizeof({selected_type}), "metadata width");\n'
        helper += f'static_assert(alignof({native_type}) == alignof({selected_type}), "metadata alignment");\n'
    result = result.replace('class PHPCoroutine {', helper + '#endif\n\nclass PHPCoroutine {')
    replacements = {
        'static inline long get_pcid(long cid = 0) {': '''
        const auto route = swr_v1_phpcoroutines_context_route(SWR_CORO_CONTEXT_PARENT, cid, 0);
        PHPContext *ctx = route == SWR_CORO_CONTEXT_CURRENT ? get_context() : get_context_by_cid(cid);
        const auto cells = php_coroutine_metadata_cells(ctx);
        uint32_t stage = 0;
        return static_cast<long>(''' + call('PARENT') + '''.value);
''',
        'static inline bool is_schedulable(PHPContext *ctx) {': '''
        const auto cells = php_coroutine_metadata_cells(ctx);
        uint32_t stage = 0;
        int64_t observation = 0;
        for (;;) {
            const auto part = swr_v1_phpcoroutines_metadata(&stage, SWR_CORO_METADATA_SCHEDULABLE,
                                                           &cells, observation, MAX_EXEC_MSEC);
            switch (part.action) {
            case SWR_CORO_METADATA_FALSE: return false;
            case SWR_CORO_METADATA_TRUE: return true;
            case SWR_CORO_METADATA_CLOCK: observation = Timer::get_absolute_msec(); break;
            }
        }
''',
    }
    for name, kind in [('enable', 'ENABLE'), ('disable', 'DISABLE')]:
        replacements[f'static inline bool {name}_scheduler() {{'] = '''
        PHPContext *ctx = (PHPContext *) Coroutine::get_current_task();
        const auto cells = php_coroutine_metadata_cells(ctx);
        uint32_t stage = 0;
        return ''' + call(kind) + '''.value != 0;
'''
    replacements['static void record_last_msec(PHPContext *ctx) {'] = '''
        uint32_t interrupt_stage = 0;
        if (swr_v1_phpcoroutines_interrupt(&interrupt_thread_running, &interrupt_stage, SWR_CORO_INTERRUPT_RECORD, MAX_EXEC_MSEC).action == SWR_CORO_INTERRUPT_CLOCK) {
            const auto cells = php_coroutine_metadata_cells(ctx);
            uint32_t stage = 0;
            const int64_t now = Timer::get_absolute_msec();
            ''' + call('RECORD', value='now') + ''';
        }
'''
    for signature, replacement in replacements.items():
        original = body(source, signature)
        if body(result, signature) != original:
            raise ValueError('Primitive header body already selected: ' + signature)
        result = result.replace(signature + original + '}', signature + '\n#ifdef SWOOLE_RS_PHPCOROUTINES' +
                                replacement + '#else' + original + '#endif\n    }')
    signature = 'static inline void init_main_context() {'
    original = body(source, signature)
    replacement = original.replace('main_context.fiber_init_notified = true;', '''{
            const auto cells = php_coroutine_metadata_cells(&main_context);
            uint32_t stage = 0;
            ''' + call('INIT_FIBER') + ''';
        }''')
    result = replace_active(source, result, signature, body, lambda _: replacement)
    return result


def replace_metadata_cpp(source, result, body):
    for signature, kind in [('static int coro_begin_silence_handler(zend_execute_data *execute_data) {', 'BEGIN'),
                             ('static int coro_end_silence_handler(zend_execute_data *execute_data) {', 'END')]:
        replacement = '\n    PHPContext *task = PHPCoroutine::get_context();\n    ' + silence(kind, 'task') + '\n    return ZEND_USER_OPCODE_DISPATCH;\n'
        result = replace_active(source, result, signature, body, lambda _: replacement)
    signature = 'PHPContext *PHPCoroutine::create_context(const Args *args) {'
    def initialize(original):
        result = original.replace('ctx->in_silence = false;', 'ctx->in_silence = {0};')
        result = result.replace('ctx->fiber_init_notified = false;', 'ctx->fiber_init_notified = {0};')
        result = result.replace('ctx->pcid = ctx->co->get_origin_cid();', '''{
        const auto cells = php_coroutine_metadata_cells(ctx);
        uint32_t stage = 0;
        const long parent = ctx->co->get_origin_cid();
        ''' + call('SET_PARENT', value='parent') + ''';
    }''')
        return result.replace('ctx->enable_scheduler = true;', '''{
        const auto cells = php_coroutine_metadata_cells(ctx);
        uint32_t stage = 0;
        ''' + call('INIT_SCHEDULER') + ''';
    }''')
    result = replace_active(source, result, signature, body, initialize)
    return result
