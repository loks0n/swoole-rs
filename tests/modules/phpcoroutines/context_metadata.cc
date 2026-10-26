#include "swoole_rs.h"
#include "swoole_rs_phpcoroutines.h"
#include <atomic>
#include <cassert>
#include <cstdio>
#include <initializer_list>
#define UNEXPECTED(value) (value)
#define EG(field) (error_mask)
#define ZEND_USER_OPCODE_DISPATCH 2
struct zend_execute_data {};

namespace native {
struct PHPContext { bool in_silence, enable_scheduler; int ori_error_reporting, tmp_error_reporting; bool fiber_init_notified; long pcid; int64_t last_msec; };
static PHPContext *current;
static int error_mask;
static int64_t now;
static unsigned clock_reads;
static std::atomic_bool interrupt_thread_running{false};
struct Timer { static int64_t get_absolute_msec() { ++clock_reads; return now; } };
struct Coroutine { static void *get_current_task() { return current; } };
struct PHPCoroutine {
    static const uint8_t MAX_EXEC_MSEC = 10;
    /* native_methods */
};
/* native_helpers */
}
namespace selected {
struct PHPContext { swr_phpcoroutines_scheduler_phase in_silence, enable_scheduler; swr_phpcoroutines_error_cell ori_error_reporting, tmp_error_reporting; swr_phpcoroutines_scheduler_phase fiber_init_notified; swr_phpcoroutines_parent_cell pcid; swr_phpcoroutines_clock_cell last_msec; };
static swr_phpcoroutines_context_cells php_coroutine_metadata_cells(PHPContext *);
static PHPContext *current;
static int error_mask;
static int64_t now;
static unsigned clock_reads;
static swr_phpcoroutines_interrupt_state interrupt_thread_running{};
struct Timer { static int64_t get_absolute_msec() { ++clock_reads; return now; } };
struct Coroutine { static void *get_current_task() { return current; } };
struct PHPCoroutine {
    static const uint8_t MAX_EXEC_MSEC = 10;
    /* selected_methods */
};
/* selected_helpers */
}
int main() {
    assert(swr_v1_abi_version() == 1);
    assert((swr_v1_feature_bits() & 134217728) != 0);
    native::PHPContext n{};
    selected::PHPContext s{};
    for (bool present : {false, true}) {
        native::current = present ? &n : nullptr;
        selected::current = present ? &s : nullptr;
        for (bool enabled : {false, true}) {
            n.enable_scheduler = enabled;
            s.enable_scheduler.started = enabled;
            assert(native::PHPCoroutine::enable_scheduler() == selected::PHPCoroutine::enable_scheduler());
            assert(n.enable_scheduler == bool(s.enable_scheduler.started));
            assert(native::PHPCoroutine::disable_scheduler() == selected::PHPCoroutine::disable_scheduler());
            assert(n.enable_scheduler == bool(s.enable_scheduler.started));
        }
    }
    for (bool running : {false, true}) {
        native::interrupt_thread_running = running; selected::interrupt_thread_running.running = running;
        for (bool enabled : {false, true}) {
            n.enable_scheduler = enabled; s.enable_scheduler.started = enabled;
            for (int64_t elapsed : {-1, 0, 10, 11, 100}) {
                n.last_msec = 37; s.last_msec.value = 37;
                native::now = selected::now = 37 + elapsed;
                native::clock_reads = selected::clock_reads = 0;
                assert(native::PHPCoroutine::is_schedulable(&n) == selected::PHPCoroutine::is_schedulable(&s));
                assert(native::clock_reads == selected::clock_reads);
                assert(native::clock_reads == unsigned(running && enabled));
            }
        }
    }
    native::current = &n; selected::current = &s;
    for (int mask : {-1, 0, 17, 32767}) {
        native::error_mask = selected::error_mask = mask;
        assert(native::coro_begin_silence_handler(nullptr) == selected::coro_begin_silence_handler(nullptr));
        assert(n.in_silence == bool(s.in_silence.started));
        assert(n.ori_error_reporting == s.ori_error_reporting.value);
        native::error_mask = selected::error_mask = mask ^ 3;
        native::save_mask(&n); selected::save_mask(&s);
        assert(n.tmp_error_reporting == s.tmp_error_reporting.value);
        assert(native::error_mask == selected::error_mask);
        native::restore_mask(&n); selected::restore_mask(&s);
        assert(native::error_mask == selected::error_mask);
        assert(native::coro_end_silence_handler(nullptr) == selected::coro_end_silence_handler(nullptr));
        assert(n.in_silence == bool(s.in_silence.started));
        native::error_mask = selected::error_mask = 123;
        native::save_mask(&n); selected::save_mask(&s);
        native::restore_mask(&n); selected::restore_mask(&s);
        assert(native::error_mask == selected::error_mask && native::error_mask == 123);
    }
    std::puts("CONTEXT_METADATA_MODELS_OK");
}
