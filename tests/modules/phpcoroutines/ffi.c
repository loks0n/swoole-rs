#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif
#include <assert.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/file.h>
#include "swoole_rs.h"
#include "swoole_rs_phpcoroutines.h"
int main(void) {
    assert(swr_v1_abi_version() == 1);
    swr_phpcoroutines_scheduler_callback_owner callback_owner = {73};
    swr_phpcoroutines_callback_control_state callback_state = {0, 0};
    const swr_phpcoroutines_scheduler_constants callback_constants = {0, 7, 9};
    swr_phpcoroutines_callback_control_plan callback_plan = swr_v1_phpcoroutines_callback_control(
        &callback_state, &callback_owner, SWR_CORO_SCHED_CONTROL_CALLBACK, 0, &callback_constants);
    assert(callback_plan.action == SWR_CORO_CALLBACK_ASSERT && callback_plan.identity == 73);
    callback_plan = swr_v1_phpcoroutines_callback_control(
        &callback_state, &callback_owner, SWR_CORO_SCHED_CONTROL_CALLBACK, 0, &callback_constants);
    assert(callback_plan.action == SWR_CORO_SCHED_CONTROL_CALL && callback_plan.identity == 73);
    swr_phpcoroutines_callback_control_state callback_shutdown = {0, 0};
    callback_plan = swr_v1_phpcoroutines_callback_control(
        &callback_shutdown, &callback_owner, SWR_CORO_SCHED_CONTROL_SHUTDOWN, 0, NULL);
    assert(callback_plan.action == SWR_CORO_SCHED_CONTROL_RESOLVERS);
    callback_plan = swr_v1_phpcoroutines_callback_control(
        &callback_shutdown, &callback_owner, SWR_CORO_SCHED_CONTROL_SHUTDOWN, 0, NULL);
    assert(callback_plan.action == SWR_CORO_SCHED_CONTROL_CACHE_FREE && callback_plan.identity == 73);
    assert(callback_owner.identity == 73);
    callback_plan = swr_v1_phpcoroutines_callback_control(
        &callback_shutdown, &callback_owner, SWR_CORO_SCHED_CONTROL_SHUTDOWN, 0, NULL);
    assert(callback_plan.action == SWR_CORO_SCHED_CONTROL_DONE && callback_owner.identity == 0);
    swr_phpcoroutines_exit_state exit_state = {0, 0};
    const swr_phpcoroutines_exit_config exit_config = {0x40, 0x100, 7, 12};
    assert(swr_v1_phpcoroutines_exit(&exit_state, &exit_config, 0, 0).action == SWR_CORO_EXIT_CURRENT);
    assert(swr_v1_phpcoroutines_exit(&exit_state, &exit_config, 0, 1).action == SWR_CORO_EXIT_SERVER);
    swr_phpcoroutines_exit_plan exit_flags = swr_v1_phpcoroutines_exit(&exit_state, &exit_config, 0, 0);
    assert(exit_flags.action == SWR_CORO_EXIT_LEGACY_BEGIN && exit_flags.flags == 0x40);
    assert(swr_v1_phpcoroutines_exit(&exit_state, &exit_config, 0, 0).action == SWR_CORO_EXIT_OPERAND);
    assert(swr_v1_phpcoroutines_exit(&exit_state, &exit_config, 0, 7).action == SWR_CORO_EXIT_NULL);
    assert(swr_v1_phpcoroutines_exit(&exit_state, &exit_config, 0, 0).action == SWR_CORO_EXIT_THROW_LEGACY);
    swr_phpcoroutines_join_owner *join_owner = swr_v1_phpcoroutines_join_try_new();
    assert(join_owner != NULL);
    assert(swr_v1_phpcoroutines_join_clone(join_owner));
    assert(swr_v1_phpcoroutines_join_empty(join_owner));
    assert(swr_v1_phpcoroutines_join_try_insert(join_owner, 19));
    assert(swr_v1_phpcoroutines_join_try_insert(join_owner, 7));
    size_t join_cursor = 0; uintptr_t join_token = 0;
    assert(swr_v1_phpcoroutines_join_next(join_owner, &join_cursor, &join_token) && join_token == 7);
    assert(!swr_v1_phpcoroutines_join_erase_empty(join_owner, 7));
    assert(swr_v1_phpcoroutines_join_erase_empty(join_owner, 19));
    assert(swr_v1_phpcoroutines_join_can_resume(join_owner));
    swr_v1_phpcoroutines_join_release_membership(join_owner);
    assert(swr_v1_phpcoroutines_join_empty(join_owner));
    swr_v1_phpcoroutines_join_cancel(join_owner);
    assert(!swr_v1_phpcoroutines_join_can_resume(join_owner));
    swr_v1_phpcoroutines_join_drop(join_owner);
    swr_v1_phpcoroutines_join_drop(join_owner);
    for (uint8_t caps = 0; caps < 2; ++caps) {
        const uint32_t expected_counts[] = {(uint32_t)(37 + caps), 2, 5, 12};
        for (uint32_t kind = 0; kind < 4; ++kind) {
            swr_phpcoroutines_method_cursor cursor = {0, 0};
            uint32_t count = 0;
            for (;;) {
                swr_phpcoroutines_method_plan method = swr_v1_phpcoroutines_method(&cursor, kind, caps, 0x400, 0x80);
                assert(method.slot == count);
                if (method.done) { assert(method.name == NULL); break; }
                assert(method.name != NULL && method.name[0] != '\0');
                assert(method.flags == ((kind == 0 || kind == 3) ? 0x480u : 0x400u));
                if (kind == 0 && caps == 0) assert(method.handler != 25);
                ++count;
            }
            assert(count == expected_counts[kind]);
        }
    }
    swr_phpcoroutines_scheduler_queue *slot = NULL;
    swr_phpcoroutines_scheduler_task slot_task = {99, 7};
    assert(swr_v1_phpcoroutines_scheduler_next_slot(&slot, &slot_task) == SWR_CORO_SCHED_SLOT_ABSENT);
    assert(slot_task.token == 99 && slot_task.repetitions == 7);
    swr_v1_phpcoroutines_scheduler_drop_slot(&slot);
    assert(swr_v1_phpcoroutines_scheduler_prepare_slot(&slot));
    swr_phpcoroutines_scheduler_queue *same_slot = slot;
    assert(swr_v1_phpcoroutines_scheduler_prepare_slot(&slot) && slot == same_slot);
    assert(swr_v1_phpcoroutines_scheduler_next_slot(&slot, &slot_task) == SWR_CORO_SCHED_SLOT_EMPTY);
    assert(slot_task.token == 99 && slot_task.repetitions == 7);
    const int64_t slot_counts[] = {-2, 0, 3};
    const uintptr_t slot_tokens[] = {41, 0, UINTPTR_MAX};
    for (size_t i = 0; i < 3; ++i)
        assert(swr_v1_phpcoroutines_scheduler_try_push_slot(&slot, slot_tokens[i], slot_counts[i]));
    for (size_t i = 0; i < 3; ++i) {
        assert(swr_v1_phpcoroutines_scheduler_next_slot(&slot, &slot_task) == SWR_CORO_SCHED_SLOT_TASK);
        assert(slot_task.token == slot_tokens[i]);
        assert(slot_task.repetitions == (slot_counts[i] > 0 ? (uint64_t) slot_counts[i] : 0));
    }
    assert(swr_v1_phpcoroutines_scheduler_next_slot(&slot, &slot_task) == SWR_CORO_SCHED_SLOT_EMPTY);
    swr_v1_phpcoroutines_scheduler_drop_slot(&slot);
    assert(slot == NULL);
    assert(swr_v1_phpcoroutines_scheduler_next_slot(&slot, &slot_task) == SWR_CORO_SCHED_SLOT_ABSENT);
    const swr_phpcoroutines_scheduler_constants scheduler_constants = {-3, 19, 71};
    uint32_t scheduler_control_stage = 0;
    assert(swr_v1_phpcoroutines_scheduler_control(&scheduler_control_stage, SWR_CORO_SCHED_CONTROL_CALLBACK, 0, &scheduler_constants) == SWR_CORO_SCHED_CONTROL_CALL);
    assert(swr_v1_phpcoroutines_scheduler_control(&scheduler_control_stage, SWR_CORO_SCHED_CONTROL_CALLBACK, -3, &scheduler_constants) == SWR_CORO_SCHED_CONTROL_EXCEPTION_PRESENCE);
    assert(swr_v1_phpcoroutines_scheduler_control(&scheduler_control_stage, SWR_CORO_SCHED_CONTROL_CALLBACK, 0, &scheduler_constants) == SWR_CORO_SCHED_CONTROL_RESULT);
    assert(swr_v1_phpcoroutines_scheduler_control(&scheduler_control_stage, SWR_CORO_SCHED_CONTROL_CALLBACK, 19, &scheduler_constants) == SWR_CORO_SCHED_CONTROL_FALSE);
    uint32_t control_stage = 0;
    assert(swr_v1_phpcoroutines_control(&control_stage, SWR_CORO_CONTROL_TIME_LIMIT, 1, 0.5).action == SWR_CORO_CONTROL_CID);
    swr_phpcoroutines_control_plan interval = swr_v1_phpcoroutines_control(&control_stage, SWR_CORO_CONTROL_TIME_LIMIT, 0, 0.5);
    assert(interval.action == SWR_CORO_CONTROL_TIMER);
    const double timeouts[] = {0.5, -0.5, 1.9, -1.9, 120.0, -120.0, 100000.0, 0.0, -0.0};
    for (size_t i = 0; i < sizeof(timeouts) / sizeof(timeouts[0]); ++i) {
        control_stage = 0;
        const int positive = timeouts[i] > 0;
        assert(swr_v1_phpcoroutines_control(&control_stage, SWR_CORO_CONTROL_TIME_LIMIT, 1, timeouts[i]).action ==
               (positive ? SWR_CORO_CONTROL_CID : SWR_CORO_CONTROL_FALSE));
        if (!positive) continue;
        assert(swr_v1_phpcoroutines_control(&control_stage, SWR_CORO_CONTROL_TIME_LIMIT, 0, timeouts[i]).action == SWR_CORO_CONTROL_TIMER);
    }
    swr_phpcoroutines_parent_cell parent_cell;
    swr_phpcoroutines_context_cells cells = {NULL, NULL, NULL, NULL, NULL, NULL, NULL};
    uint32_t metadata_stage = 0;
    cells.parent = &parent_cell;
    swr_v1_phpcoroutines_metadata(&metadata_stage, SWR_CORO_METADATA_SET_PARENT, &cells, -9, 0);
    metadata_stage = 0;
    assert(swr_v1_phpcoroutines_metadata(&metadata_stage, SWR_CORO_METADATA_PARENT, &cells, 0, 0).value == -9);
    swr_phpcoroutines_scheduler_phase scheduler_phase = {0};
    assert(swr_v1_phpcoroutines_scheduler_phase(&scheduler_phase, SWR_CORO_SCHED_PHASE_READ) == 0);
    assert(swr_v1_phpcoroutines_scheduler_phase(&scheduler_phase, SWR_CORO_SCHED_PHASE_START) == 1);
    assert(swr_v1_phpcoroutines_scheduler_phase(&scheduler_phase, SWR_CORO_SCHED_PHASE_READ) == 1);
    assert(swr_v1_phpcoroutines_scheduler_phase(&scheduler_phase, SWR_CORO_SCHED_PHASE_STOP) == 0);
    swr_phpcoroutines_fiber_states fiber_states = {11, -3, 24, 99};
    const char *creation_names[] = {"__destruct", "__destructor", "__destruc\0", "x_destruct"};
    for (size_t i = 0; i < sizeof(creation_names) / sizeof(creation_names[0]); ++i) {
        assert(swr_v1_phpcoroutines_create_destructor((const uint8_t *) creation_names[i]) ==
               (memcmp(creation_names[i], "__destruct", 10) == 0));
    }
    const uint8_t interrupt_maxima[] = {0, 1, 2, 9, 10, 255};
    for (size_t maximum_index = 0; maximum_index < sizeof(interrupt_maxima); ++maximum_index) {
        const uint8_t maximum = interrupt_maxima[maximum_index];
    swr_phpcoroutines_interrupt_state interrupt_state = {0};
    uint32_t interrupt_start = 0, interrupt_child = 0, interrupt_stop = 0, interrupt_record = 0;
    assert(sizeof(interrupt_state) == 1);
    assert(swr_v1_phpcoroutines_interrupt(&interrupt_state, &interrupt_start, SWR_CORO_INTERRUPT_START, maximum).action == SWR_CORO_INTERRUPT_VM_CAPTURE);
    assert(swr_v1_phpcoroutines_interrupt(&interrupt_state, &interrupt_record, SWR_CORO_INTERRUPT_RECORD, maximum).action == SWR_CORO_INTERRUPT_DONE);
    assert(swr_v1_phpcoroutines_interrupt(&interrupt_state, &interrupt_start, SWR_CORO_INTERRUPT_START, maximum).action == SWR_CORO_INTERRUPT_THREAD_START);
    assert(swr_v1_phpcoroutines_interrupt(&interrupt_state, &interrupt_child, SWR_CORO_INTERRUPT_CHILD, maximum).action == SWR_CORO_INTERRUPT_VM_STORE);
    swr_phpcoroutines_interrupt_plan interrupt_sleep = swr_v1_phpcoroutines_interrupt(&interrupt_state, &interrupt_child, SWR_CORO_INTERRUPT_CHILD, maximum);
    assert(interrupt_sleep.action == SWR_CORO_INTERRUPT_SLEEP && interrupt_sleep.value == (maximum / 2));
    assert(swr_v1_phpcoroutines_interrupt(&interrupt_state, &interrupt_stop, SWR_CORO_INTERRUPT_STOP, maximum).action == SWR_CORO_INTERRUPT_THREAD_JOIN);
    assert(swr_v1_phpcoroutines_interrupt(&interrupt_state, &interrupt_child, SWR_CORO_INTERRUPT_CHILD, maximum).action == SWR_CORO_INTERRUPT_DONE);
    }
    const int64_t repeat_counts[] = {-2, 0, 1, 5, 1024};
    for (size_t count_index = 0; count_index < sizeof(repeat_counts) / sizeof(repeat_counts[0]); ++count_index) {
        const int64_t count = repeat_counts[count_index];
        int64_t native_count = 0, selected_count = 0;
        for (int64_t i = 0; i < count; ++i) { ++native_count; }
        swr_phpcoroutines_repeat_state repeat = {count, 0, 0};
        while (swr_v1_phpcoroutines_repeat(&repeat)) { ++selected_count; }
        assert(selected_count == native_count);
    }
    uint32_t create_stage = 0;
    assert(swr_v1_phpcoroutines_control(&create_stage, SWR_CORO_CONTROL_CREATE_FRONTEND, 0, 0).action == SWR_CORO_CONTROL_REQUEST_SHUTDOWN);
    assert(swr_v1_phpcoroutines_control(&create_stage, SWR_CORO_CONTROL_CREATE_FRONTEND, 0, 0).action == SWR_CORO_CONTROL_CREATE_EFFECT);
    assert(swr_v1_phpcoroutines_control(&create_stage, SWR_CORO_CONTROL_CREATE_FRONTEND, 7, 0).action == SWR_CORO_CONTROL_CREATE_LONG);
    uint32_t terminal_stage = 0;
    assert(swr_v1_phpcoroutines_control(&terminal_stage, SWR_CORO_CONTROL_CLOSE, 0, 0).action == SWR_CORO_CONTROL_CLOSE_PRESENCE);
    assert(swr_v1_phpcoroutines_control(&terminal_stage, SWR_CORO_CONTROL_CLOSE, 1, 0).action == SWR_CORO_CONTROL_CLOSE_CALLBACK);
    assert(swr_v1_phpcoroutines_control(&terminal_stage, SWR_CORO_CONTROL_CLOSE, 0, 0).action == SWR_CORO_CONTROL_CLOSE_FREE);
    assert(swr_v1_phpcoroutines_control(&terminal_stage, SWR_CORO_CONTROL_CLOSE, 0, 0).action == SWR_CORO_CONTROL_DONE);
    uint32_t destroy_stage = 0;
    const uint32_t destroy_actions[] = {SWR_CORO_FIBER_DESTROY_PRESENT, SWR_CORO_FIBER_PUBLISH_DEAD,
        SWR_CORO_FIBER_DESTROY_SWITCH, SWR_CORO_FIBER_DESTROY_NOTIFY,
        SWR_CORO_FIBER_REFRESH_PRESENT, SWR_CORO_FIBER_FREE, SWR_CORO_FIBER_DONE};
    for (size_t i = 0; i < sizeof(destroy_actions) / sizeof(destroy_actions[0]); ++i) {
        assert(swr_v1_phpcoroutines_fiber(&destroy_stage, SWR_CORO_FIBER_DESTROY, 1, NULL) == destroy_actions[i]);
    }
    uint32_t fiber_stage = 0;
    assert(swr_v1_phpcoroutines_fiber(&fiber_stage, SWR_CORO_FIBER_STATUS, 0, &fiber_states) == SWR_CORO_FIBER_MAIN);
    assert(swr_v1_phpcoroutines_fiber(&fiber_stage, SWR_CORO_FIBER_STATUS, 0, &fiber_states) == SWR_CORO_FIBER_STATE);
    assert(swr_v1_phpcoroutines_fiber(&fiber_stage, SWR_CORO_FIBER_STATUS, -3, &fiber_states) == SWR_CORO_FIBER_SUSPENDED);
    swr_phpcoroutines_bootstrap_state bootstrap = {0, 0, 0};
    swr_phpcoroutines_bootstrap_plan bootstrap_first = swr_v1_phpcoroutines_bootstrap(&bootstrap, 0, 0, 1);
    assert(bootstrap_first.action == SWR_CORO_BOOT_CLASS && bootstrap_first.id == 0);
    assert(!strcmp(bootstrap_first.name, "Swoole\\Coroutine") && bootstrap_first.length == strlen(bootstrap_first.name));
    swr_phpcoroutines_config_state config_state = {7, 0, 0, 0};
    assert(swr_v1_phpcoroutines_config(&config_state, SWR_CORO_CONFIG_GET_MAX, 0) == 7);
    assert(swr_v1_phpcoroutines_config(&config_state, SWR_CORO_CONFIG_GET_DEADLOCK, 0) == 1);
    assert(swr_v1_phpcoroutines_config(&config_state, SWR_CORO_CONFIG_GET_PREEMPTIVE, 0) == 0);
    swr_v1_phpcoroutines_config(&config_state, SWR_CORO_CONFIG_SET_MAX, UINT64_MAX);
    assert(swr_v1_phpcoroutines_config(&config_state, SWR_CORO_CONFIG_GET_MAX, 0) == UINT64_MAX);
    swr_v1_phpcoroutines_config(&config_state, SWR_CORO_CONFIG_SET_HOOKS, UINT32_MAX);
    assert(swr_v1_phpcoroutines_config(&config_state, SWR_CORO_CONFIG_GET_HOOKS, 0) == UINT32_MAX);
    swr_v1_phpcoroutines_config(&config_state, SWR_CORO_CONFIG_SET_PREEMPTIVE, 1);
    swr_v1_phpcoroutines_config(&config_state, SWR_CORO_CONFIG_SET_DEADLOCK, 0);
    assert(swr_v1_phpcoroutines_config(&config_state, SWR_CORO_CONFIG_GET_PREEMPTIVE, 0) == 1);
    assert(swr_v1_phpcoroutines_config(&config_state, SWR_CORO_CONFIG_GET_DEADLOCK, 0) == 0);
    uint32_t trace_stage = 0;
    swr_phpcoroutines_trace_plan self_trace = swr_v1_phpcoroutines_trace(&trace_stage, 0, 0, 1);
    assert(self_trace.action == SWR_CORO_TRACE_SELF && self_trace.skip_last == 1);
    assert(swr_v1_phpcoroutines_context_query(SWR_CORO_QUERY_PARENT, NULL, 0, 9) == SWR_CORO_QUERY_LONG);
    uint32_t query_stage = 0;
    assert(swr_v1_phpcoroutines_context_query(SWR_CORO_QUERY_CONTEXT, &query_stage, 0, 0) == SWR_CORO_QUERY_CURRENT);
    assert(swr_v1_phpcoroutines_system_address(5, 2, 2, 10) == SWR_CORO_ADDRESS_READY);
    swr_phpcoroutines_result_state result_state = {0, 0};
    assert(swr_v1_phpcoroutines_system_complete(SWR_CORO_RESULT_STATVFS, &result_state, 0, 0).action == SWR_CORO_RESULT_ARRAY);
    swr_phpcoroutines_result_plan first_stat = swr_v1_phpcoroutines_system_complete(SWR_CORO_RESULT_STATVFS, &result_state, 0, 0);
    assert(first_stat.action == SWR_CORO_RESULT_FIELD && first_stat.index == 0 && !strcmp(first_stat.key, "bsize"));
    swr_phpcoroutines_result_state wait_state = {0, 0};
    assert(swr_v1_phpcoroutines_system_complete(SWR_CORO_RESULT_WAIT, &wait_state, -1, 0).action == SWR_CORO_RESULT_WAIT_ANY);
    assert(swr_v1_phpcoroutines_system_complete(SWR_CORO_RESULT_WAIT, &wait_state, 42, 0).action == SWR_CORO_RESULT_ARRAY);
    swr_phpcoroutines_result_plan wait_pid = swr_v1_phpcoroutines_system_complete(SWR_CORO_RESULT_WAIT, &wait_state, 42, 0);
    assert(wait_pid.action == SWR_CORO_RESULT_FIELD && wait_pid.index == 0 && !strcmp(wait_pid.key, "pid"));
    swr_phpcoroutines_result_state signal_state = {0, 0};
    assert(swr_v1_phpcoroutines_system_complete(SWR_CORO_RESULT_SIGNAL, &signal_state, -1, 0).action == SWR_CORO_RESULT_BUSY);
    assert(swr_v1_phpcoroutines_system_complete(SWR_CORO_RESULT_SIGNAL, &signal_state, 0, 0).action == SWR_CORO_RESULT_INVALID);
    assert(swr_v1_phpcoroutines_system_complete(SWR_CORO_RESULT_SIGNAL, &signal_state, 1, 0).action == SWR_CORO_RESULT_WARN_INVALID);
    assert(swr_v1_phpcoroutines_system_complete(SWR_CORO_RESULT_SIGNAL, &signal_state, 0, 0).action == SWR_CORO_RESULT_ERRNO);
    assert(swr_v1_phpcoroutines_system_complete(SWR_CORO_RESULT_SIGNAL, &signal_state, 0, 0).action == SWR_CORO_RESULT_FALSE);
    assert(swr_v1_phpcoroutines_context_route(SWR_CORO_CONTEXT_BY_ID, -1, 0) == SWR_CORO_CONTEXT_MAIN);
    assert(swr_v1_phpcoroutines_scheduler_policy(SWR_CORO_SCHED_ELAPSED, 1, 1, 100, 89, 10));
    swr_phpcoroutines_stack_state stack_state = {0, 0, 0, 0};
    assert(swr_v1_phpcoroutines_stack_step(&stack_state, 0, 0) == SWR_CORO_STACK_CID);
    assert(swr_v1_phpcoroutines_stack_step(&stack_state, 7, 0) == SWR_CORO_STACK_CONTEXT && stack_state.cid == 7);
#ifdef SWR_M29_SUPPLIED_ARCHIVE
    assert((swr_v1_feature_bits() & UINT64_C(134217728)) != 0);
#else
    assert(swr_v1_feature_bits() == UINT64_C(134217728));
#endif
    swr_phpcoroutines_scheduler_queue *queue = swr_v1_phpcoroutines_scheduler_new();
    swr_v1_phpcoroutines_scheduler_push(queue, 17, 2);
    swr_phpcoroutines_scheduler_task task;
    assert(swr_v1_phpcoroutines_scheduler_pop(queue, &task) && task.token == 17 && task.repetitions == 2);
    assert(!swr_v1_phpcoroutines_scheduler_pop(queue, &task));
    swr_v1_phpcoroutines_scheduler_drop(queue);
    swr_v1_phpcoroutines_yield_put(-5, 21);
    uintptr_t token = 0;
    assert(swr_v1_phpcoroutines_yield_take(-5, &token) && token == 21);
    swr_v1_phpcoroutines_yield_erase(-5);
    swr_phpcoroutines_yield_registry *registry = NULL;
    assert(!swr_v1_phpcoroutines_yield_registry_take(registry, -6, &token));
    swr_v1_phpcoroutines_yield_registry_put(&registry, -6, 22);
    assert(swr_v1_phpcoroutines_yield_registry_take(registry, -6, &token) && token == 22);
    swr_v1_phpcoroutines_yield_registry_erase(registry, -6);
    swr_v1_phpcoroutines_yield_registry_drop(registry);
    swr_phpcoroutines_file_config config = {LOCK_EX, 8, O_CREAT | O_WRONLY | O_NOFOLLOW, O_APPEND, O_TRUNC};
    swr_phpcoroutines_file_plan file = swr_v1_phpcoroutines_system_file(1, 8 | LOCK_EX, &config);
    assert(file.accepted && file.lock == LOCK_EX && file.open == (config.base_open | O_APPEND));
    assert(swr_v1_phpcoroutines_system_sleep(0.125, 0.001));
    swr_phpcoroutines_option_state state = {0, 0};
    swr_phpcoroutines_option_plan option = swr_v1_phpcoroutines_options(&state, 0, 100000);
    assert(option.action == SWR_CORO_OPTION_LOOKUP && !strcmp(option.key, "max_coro_num"));
    assert(option.key_length == strlen(option.key));
    option = swr_v1_phpcoroutines_options(&state, 1, 100000);
    assert(option.action == SWR_CORO_OPTION_GET_MAX);
    option = swr_v1_phpcoroutines_options(&state, -1, 100000);
    assert(option.action == SWR_CORO_OPTION_SET_MAX && option.value == 100000);
    option = swr_v1_phpcoroutines_options(&state, 0, 100000);
    assert(option.action == SWR_CORO_OPTION_LOOKUP && !strcmp(option.key, "enable_deadlock_check"));
    for (unsigned i = 0; option.action != SWR_CORO_OPTION_DONE; ++i) {
        assert(i < 32);
        option = swr_v1_phpcoroutines_options(&state, 0, 100000);
    }
    swr_phpcoroutines_autoload_queue *autoload = swr_v1_phpcoroutines_autoload_new();
    swr_v1_phpcoroutines_autoload_push(autoload, 23);
    assert(swr_v1_phpcoroutines_autoload_pop(autoload, &token) && token == 23);
    swr_v1_phpcoroutines_autoload_drop(autoload);
    uint32_t creation = 0;
    assert(swr_v1_phpcoroutines_create(&creation, 2, 10, 2, 1) == SWR_CORO_CREATE_HANDLER);
    assert(swr_v1_phpcoroutines_create(&creation, 1, 10, 2, 1) == SWR_CORO_CREATE_TYPE);
    assert(swr_v1_phpcoroutines_create(&creation, 2, 10, 2, 1) == SWR_CORO_CREATE_ACTIVE);
    assert(swr_v1_phpcoroutines_create(&creation, 1, 10, 2, 1) == SWR_CORO_CREATE_READY);
    swr_phpcoroutines_stats_state statistics = {0, 0};
    swr_phpcoroutines_stats_plan field = swr_v1_phpcoroutines_stats(&statistics, 0, 0);
    assert(field.action == SWR_CORO_STATS_EVENT && !strcmp(field.key, "event_num"));
    assert(field.key_length == strlen(field.key));
    for (unsigned i = 0; field.action != SWR_CORO_STATS_DONE; ++i) {
        assert(i < 20);
        field = swr_v1_phpcoroutines_stats(&statistics, 0, 0);
    }
    swr_phpcoroutines_defer_queue *deferred = swr_v1_phpcoroutines_defer_new();
    assert(deferred && swr_v1_phpcoroutines_defer_push(deferred, 48));
    assert(swr_v1_phpcoroutines_defer_pop(deferred, &token) && token == 48);
    swr_v1_phpcoroutines_defer_drop(deferred);
    swr_phpcoroutines_configure_state configuration = {0, 0};
    swr_phpcoroutines_configure_plan action = swr_v1_phpcoroutines_configure(&configuration, 0);
    assert(action.action == SWR_CORO_CONFIG_GLOBAL);
    for (unsigned i = 0; action.action != SWR_CORO_CONFIG_DONE; ++i) {
        assert(i < 32);
        action = swr_v1_phpcoroutines_configure(&configuration, 0);
    }
    uint32_t activation = 0;
    assert(swr_v1_phpcoroutines_activation(&activation, 0) == SWR_CORO_ACTIVATE_ACTIVE);
    assert(swr_v1_phpcoroutines_activation(&activation, 1) == SWR_CORO_ACTIVATE_DONE);
    uint32_t autoload_policy = 0;
    assert(swr_v1_phpcoroutines_autoload_policy(&autoload_policy, 0) == SWR_CORO_AUTOLOAD_CURRENT);
    assert(swr_v1_phpcoroutines_autoload_policy(&autoload_policy, 0) == SWR_CORO_AUTOLOAD_DIRECT);
    swr_phpcoroutines_scheduler_queue *fallible_scheduler = swr_v1_phpcoroutines_scheduler_try_new();
    assert(fallible_scheduler && swr_v1_phpcoroutines_scheduler_try_push(fallible_scheduler, 8, 1));
    for (unsigned i = 0; i < 4096; ++i) {
        assert(swr_v1_phpcoroutines_scheduler_try_push(fallible_scheduler, i + 100, (int64_t)(i % 5) - 2));
    }
    assert(swr_v1_phpcoroutines_scheduler_pop(fallible_scheduler, &task) && task.token == 8);
    for (unsigned i = 0; i < 4096; ++i) {
        const int64_t count = (int64_t)(i % 5) - 2;
        assert(swr_v1_phpcoroutines_scheduler_pop(fallible_scheduler, &task));
        assert(task.token == i + 100 && task.repetitions == (uint64_t)(count > 0 ? count : 0));
    }
    assert(!swr_v1_phpcoroutines_scheduler_pop(fallible_scheduler, &task));
    swr_v1_phpcoroutines_scheduler_drop(fallible_scheduler);
    swr_phpcoroutines_autoload_queue *owned_autoload = swr_v1_phpcoroutines_autoload_owner_try_new(73);
    assert(owned_autoload && swr_v1_phpcoroutines_autoload_is_owner(owned_autoload, 73));
    assert(!swr_v1_phpcoroutines_autoload_is_owner(owned_autoload, 74));
    assert(swr_v1_phpcoroutines_autoload_try_push(owned_autoload, 0));
    assert(swr_v1_phpcoroutines_autoload_pop(owned_autoload, &token) && token == 0);
    swr_v1_phpcoroutines_autoload_drop(owned_autoload);
    swr_phpcoroutines_autoload_queue *fallible_autoload = swr_v1_phpcoroutines_autoload_try_new();
    assert(fallible_autoload && swr_v1_phpcoroutines_autoload_try_push(fallible_autoload, 9));
    for (unsigned i = 0; i < 4096; ++i) assert(swr_v1_phpcoroutines_autoload_try_push(fallible_autoload, i + 100));
    assert(swr_v1_phpcoroutines_autoload_pop(fallible_autoload, &token) && token == 9);
    for (unsigned i = 0; i < 4096; ++i) {
        assert(swr_v1_phpcoroutines_autoload_pop(fallible_autoload, &token) && token == i + 100);
    }
    assert(!swr_v1_phpcoroutines_autoload_pop(fallible_autoload, &token));
    swr_v1_phpcoroutines_autoload_drop(fallible_autoload);
    swr_phpcoroutines_yield_registry *fallible_registry = NULL;
    assert(swr_v1_phpcoroutines_yield_registry_try_put(&fallible_registry, 10, 11));
    assert(swr_v1_phpcoroutines_yield_registry_try_put(&fallible_registry, 10, 12));
    assert(swr_v1_phpcoroutines_yield_registry_take(fallible_registry, 10, &token) && token == 12);
    swr_v1_phpcoroutines_yield_registry_drop(fallible_registry);
#ifdef SWR_M29_SUPPLIED_ARCHIVE
    printf("{\"abi\":%u,\"bits\":%llu,\"passed\":true}\n", swr_v1_abi_version(),
           (unsigned long long) swr_v1_feature_bits());
#else
    puts("M29_ONLY_FFI_OK");
#endif
    return 0;
}
