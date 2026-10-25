// Ordinary whole activation policy with inert effects; no PHP, hooks, threads or callbacks execute.
#include <cassert>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>
#include "swoole_rs_phpcoroutines.h"
std::vector<std::string> trace;
#define sw_unlikely(value) (value)
#define ZEND_STRL(value) value, sizeof(value)-1
struct zval { bool value; } library;
unsigned library_mode;
zval *zend_get_constant_str(const char *name, size_t length) {
    assert(std::string(name, length) == "SWOOLE_LIBRARY"); trace.push_back("library");
    return library_mode == 0 ? nullptr : &library;
}
bool zval_is_true(zval *value) { assert(value); trace.push_back("truth"); return value->value; }
void php_swoole_load_library() { trace.push_back("load-stub"); }
void php_swoole_check_reactor() { trace.push_back("init-stub"); }
void original_interrupt() { assert(false); }
void coro_interrupt_function() { assert(false); }
using Interrupt = void (*)();
Interrupt zend_interrupt_function, orig_interrupt_function;
bool global_preemption, main_thread;
bool read_global() { trace.push_back("global-preemption"); return global_preemption; }
#define SWOOLE_G(name) read_global()
bool sw_is_main_thread() { trace.push_back("main-thread"); return main_thread; }
struct BoolFact {
    bool value;
    operator bool() const { trace.push_back("local-preemption"); return value; }
};
struct FlagFact {
    uint32_t value;
    operator uint32_t() const { trace.push_back("hook-flags"); return value; }
};
#ifdef SWOOLE_RS_PHPCOROUTINES
uint64_t observed_config(swr_phpcoroutines_config_state *state, uint32_t operation, uint64_t value) {
    if (operation == SWR_CORO_CONFIG_GET_PREEMPTIVE) trace.push_back("local-preemption");
    if (operation == SWR_CORO_CONFIG_GET_HOOKS) trace.push_back("hook-flags");
    return swr_v1_phpcoroutines_config(state, operation, value);
}
#define swr_v1_phpcoroutines_config observed_config
#endif
namespace PHPCoroutine {
#ifdef SWOOLE_RS_PHPCOROUTINES
swr_phpcoroutines_activation_state activated{0};
bool is_activated() { return swr_v1_phpcoroutines_scheduler_phase(&activated, SWR_CORO_SCHED_PHASE_READ); }
swr_phpcoroutines_config_state config{10, 0, 0, 0};
uint32_t get_hook_flags() { return static_cast<uint32_t>(swr_v1_phpcoroutines_config(&config, SWR_CORO_CONFIG_GET_HOOKS, 0)); }
#else
bool activated;
bool is_activated() { return activated; }
struct { BoolFact enable_preemptive_scheduler; FlagFact hook_flags; } config;
uint32_t get_hook_flags() { return config.hook_flags; }
#endif
void activate();
void deactivate(void *) { assert(false); }
void on_yield(void *) { assert(false); }
void on_resume(void *) { assert(false); }
void on_close(void *) { assert(false); }
void interrupt_thread_start() {
    assert(orig_interrupt_function == original_interrupt && zend_interrupt_function == coro_interrupt_function);
    trace.push_back("interrupt-stub");
}
void enable_hook(uint32_t value) { trace.push_back("hook-stub:" + std::to_string(value)); }
void disable_unsafe_function() { trace.push_back("unsafe-binding-stub"); }
}
struct Reactor {
    void add_destroy_callback(void (*callback)(void *), void *data) {
        assert(callback == PHPCoroutine::deactivate && data == nullptr);
        trace.push_back("register-only-stub");
    }
} reactor;
Reactor *sw_reactor() { trace.push_back("reactor"); return &reactor; }
namespace Coroutine {
void activate() { trace.push_back("core-activate-stub"); }
void set_on_yield(void (*callback)(void *)) { assert(callback == PHPCoroutine::on_yield); trace.push_back("on-yield-stub"); }
void set_on_resume(void (*callback)(void *)) { assert(callback == PHPCoroutine::on_resume); trace.push_back("on-resume-stub"); }
void set_on_close(void (*callback)(void *)) { assert(callback == PHPCoroutine::on_close); trace.push_back("on-close-stub"); }
}
// ACTUAL_BODY
int main() {
    for (unsigned mode = 0; mode < 3; ++mode) {
        for (unsigned bits = 0; bits < 32; ++bits) {
            library_mode = mode; library.value = mode == 2;
            global_preemption = bits & 1;
#ifdef SWOOLE_RS_PHPCOROUTINES
            swr_v1_phpcoroutines_config(&PHPCoroutine::config, SWR_CORO_CONFIG_SET_PREEMPTIVE, bits & 2);
#else
            PHPCoroutine::config.enable_preemptive_scheduler.value = bits & 2;
#endif
            main_thread = bits & 4;
#ifdef SWOOLE_RS_PHPCOROUTINES
            swr_v1_phpcoroutines_config(&PHPCoroutine::config, SWR_CORO_CONFIG_SET_HOOKS, bits & 8 ? 0x80000001u : 0);
#else
            PHPCoroutine::config.hook_flags.value = bits & 8 ? 0x80000001u : 0;
#endif
#ifdef SWOOLE_RS_PHPCOROUTINES
            swr_v1_phpcoroutines_scheduler_phase(&PHPCoroutine::activated, bits & 16 ? SWR_CORO_SCHED_PHASE_START : SWR_CORO_SCHED_PHASE_STOP);
#else
            PHPCoroutine::activated = bits & 16;
#endif
            zend_interrupt_function = original_interrupt;
            orig_interrupt_function = nullptr;
            trace.clear();
            PHPCoroutine::activate();
            assert(PHPCoroutine::is_activated());
            if (bits & 16) { assert(trace.empty()); assert(orig_interrupt_function == nullptr); }
            std::cout << mode << ':' << bits << '\n';
            for (const auto &entry : trace) std::cout << entry << '\n';
        }
    }
}
