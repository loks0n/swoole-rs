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


