// Exact pinned/selected header bodies over inert copied-fact controls, not Zend VM execution.
#include <cassert>
#include <cstdint>
#include <iostream>
#include <limits>
#include <string>
#include <vector>
#include "swoole_rs_phpcoroutines.h"
#define sw_likely(v) (v)
#define UNEXPECTED(v) (v)
#define EG(name) live_page
using zend_long = long;
struct zval { uintptr_t bytes[2]; };
struct Page { zval *end; zval *top; Page *prev; };
using zend_vm_stack = Page *;
zend_vm_stack live_page;
std::vector<std::string> trace;
struct PHPContext;
struct Coroutine {
    PHPContext *task;
    Coroutine *origin;
    static PHPContext *current, *by_id;
    static long get_current_cid() { trace.push_back("cid"); return 7; }
    static long get_elapsed(long cid) { trace.push_back("elapsed:" + std::to_string(cid)); return 81; }
    static long get_execute_time(long cid) { trace.push_back("execute:" + std::to_string(cid)); return 43; }
    static void *get_current_task() { trace.push_back("current"); return current; }
    static void *get_task_by_cid(long cid) { trace.push_back("by-id:" + std::to_string(cid)); return by_id; }
    Coroutine *get_origin() { trace.push_back("origin"); return origin; }
    void *get_task() { trace.push_back("origin-task"); return task; }
};
PHPContext *Coroutine::current, *Coroutine::by_id;
struct PHPContext {
    Coroutine *co; zend_vm_stack vm_stack;
#ifdef SWOOLE_RS_PHPCOROUTINES
    swr_phpcoroutines_parent_cell pcid;
    swr_phpcoroutines_scheduler_phase enable_scheduler;
    swr_phpcoroutines_clock_cell last_msec;
    swr_phpcoroutines_scheduler_phase in_silence, fiber_init_notified;
    swr_phpcoroutines_error_cell ori_error_reporting, tmp_error_reporting;
#else
    long pcid; bool enable_scheduler; int64_t last_msec;
#endif
};
// ACTUAL_METADATA_HELPER
#ifdef SWOOLE_RS_PHPCOROUTINES
#define PHASE(value) ((value).started)
#define SCALAR(item) ((item).value)
#define RUNNING(value) ((value).running)
#else
#define PHASE(value) (value)
#define SCALAR(value) (value)
#define RUNNING(value) (value)
#endif
struct Timer {
    static int64_t now;
    static int64_t get_absolute_msec() { trace.push_back("clock"); return now; }
};
int64_t Timer::now;
constexpr int SW_ERROR_CO_NOT_EXISTS = 1;
void swoole_set_last_error(int) { assert(false); } // Missing-context native error profile unexecuted.
struct PHPCoroutine {
#ifdef SWOOLE_RS_PHPCOROUTINES
    static swr_phpcoroutines_interrupt_state interrupt_thread_running;
#else
    static bool interrupt_thread_running;
#endif
#ifdef SWOOLE_RS_PHPCOROUTINES
    static swr_phpcoroutines_activation_state activated;
#else
    static bool activated;
#endif
    static PHPContext main_context;
    static constexpr uint8_t MAX_EXEC_MSEC = 10;
// ACTUAL_HEADER_BODIES
};
#ifdef SWOOLE_RS_PHPCOROUTINES
swr_phpcoroutines_interrupt_state PHPCoroutine::interrupt_thread_running{0};
#else
bool PHPCoroutine::interrupt_thread_running;
#endif
#ifdef SWOOLE_RS_PHPCOROUTINES
swr_phpcoroutines_activation_state PHPCoroutine::activated{0};
#else
bool PHPCoroutine::activated;
#endif
PHPContext PHPCoroutine::main_context;
int main() {
    static zval values[16] = {};
    static Page tail{values + 8, values + 1, nullptr}, live{values + 16, values + 3, &tail};
    static Page saved{values + 12, values + 2, nullptr};
    static Coroutine origin{}, coroutine{};
    static PHPContext ctx{}, ancestor{};
    ctx.co = &coroutine; ctx.vm_stack = &saved; SCALAR(ctx.pcid) = 9;
    ancestor.co = &origin; SCALAR(ancestor.pcid) = 13;
    coroutine.origin = &origin; origin.task = &ancestor;
    PHPCoroutine::main_context = {};
    PHPCoroutine::main_context.vm_stack = &tail;
    SCALAR(PHPCoroutine::main_context.pcid) = 19;
    Coroutine::by_id = &ctx;
    live_page = &live;
    for (unsigned bits = 0; bits < 8; ++bits) {
        trace.clear();
#ifdef SWOOLE_RS_PHPCOROUTINES
        swr_v1_phpcoroutines_scheduler_phase(&PHPCoroutine::activated, bits & 1 ? SWR_CORO_SCHED_PHASE_START : SWR_CORO_SCHED_PHASE_STOP);
#else
        PHPCoroutine::activated = bits & 1;
#endif
        Coroutine::current = bits & 2 ? &ctx : nullptr;
        coroutine.origin = bits & 4 ? &origin : nullptr;
        std::cout << bits << ':' << PHPCoroutine::get_cid() << ':' << PHPCoroutine::get_elapsed(8)
                  << ':' << PHPCoroutine::get_execute_time(8) << '\n';
        assert(PHPCoroutine::get_context() == (Coroutine::current ? &ctx : &PHPCoroutine::main_context));
        assert(PHPCoroutine::get_origin_context(&ctx) == (coroutine.origin ? &ancestor : &PHPCoroutine::main_context));
        assert(PHPCoroutine::get_context_by_cid(-1) == &PHPCoroutine::main_context);
        for (long cid : {-1, 0, 7, 8}) {
            std::cout << cid << ':' << PHPCoroutine::get_pcid(cid) << ':' << PHPCoroutine::get_stack_usage(cid) << '\n';
        }
        for (const auto &value : trace) std::cout << value << '\n';
    }
    for (bool present : {false, true}) for (bool enabled : {false, true}) {
        trace.clear(); Coroutine::current = present ? &ctx : nullptr;
        PHASE(ctx.enable_scheduler) = enabled;
        bool enable = PHPCoroutine::enable_scheduler();
        bool disable = PHPCoroutine::disable_scheduler();
        std::cout << "toggle:" << present << enabled << enable << disable << bool(PHASE(ctx.enable_scheduler)) << '\n';
        for (const auto &value : trace) std::cout << value << '\n';
    }
    for (bool enabled : {false, true}) for (int64_t now : {0, 10, 11, 100}) for (int64_t last : {0, 5, 100}) {
        trace.clear(); PHASE(ctx.enable_scheduler) = enabled; SCALAR(ctx.last_msec) = last; Timer::now = now;
        bool admitted = PHPCoroutine::is_schedulable(&ctx);
        std::cout << "schedule:" << enabled << ':' << now << ':' << last << ':' << admitted << ':' << trace.size() << '\n';
        assert(trace.size() == (enabled ? 1u : 0u));
    }
    for (bool running : {false, true}) {
        trace.clear(); RUNNING(PHPCoroutine::interrupt_thread_running) = running; SCALAR(ctx.last_msec) = -5; Timer::now = 123;
        PHPCoroutine::record_last_msec(&ctx);
        assert(SCALAR(ctx.last_msec) == (running ? 123 : -5)); assert(trace.size() == (running ? 1u : 0u));
        std::cout << "record:" << running << ':' << SCALAR(ctx.last_msec) << ':' << trace.size() << '\n';
    }
#ifdef SWOOLE_RS_PHPCOROUTINES
    // Copied counter facts only: no VM pages or errors are invoked for these arithmetic controls.
    swr_phpcoroutines_stack_state counter = {7, 7, std::numeric_limits<size_t>::max() - 2, 4};
    assert(swr_v1_phpcoroutines_stack_step(&counter, 0, 9) == SWR_CORO_STACK_NEXT && counter.usage == 6);
    counter.stage = 2;
    assert(swr_v1_phpcoroutines_stack_step(&counter, 0, 0) == SWR_CORO_STACK_MISSING);
#endif
}
