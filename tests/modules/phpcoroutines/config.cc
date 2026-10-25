// Exact five public helper bodies/config seed over primitive state. No Zend/runtime effects.
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <limits>
#include <thread>
#include "swoole_rs_phpcoroutines.h"
#if CONFIG_THREAD_LOCAL
#define SW_THREAD_LOCAL thread_local
#else
#define SW_THREAD_LOCAL
#endif
#define SW_DEFAULT_MAX_CORO_NUM 77
class PHPCoroutine {
  public:
// ACTUAL_PUBLIC_CONFIG
// ACTUAL_CONFIG_DECL
// ACTUAL_CONFIG_HEADER_BODIES
    static void hooks(uint32_t flags) {
#ifdef SWOOLE_RS_PHPCOROUTINES
        swr_v1_phpcoroutines_config(&config, SWR_CORO_CONFIG_SET_HOOKS, flags);
#else
        config.hook_flags = flags;
#endif
    }
    static bool preemptive() {
#ifdef SWOOLE_RS_PHPCOROUTINES
        return swr_v1_phpcoroutines_config(&config, SWR_CORO_CONFIG_GET_PREEMPTIVE, 0);
#else
        return config.enable_preemptive_scheduler;
#endif
    }
    static bool deadlock() {
#ifdef SWOOLE_RS_PHPCOROUTINES
        return swr_v1_phpcoroutines_config(&config, SWR_CORO_CONFIG_GET_DEADLOCK, 0);
#else
        return config.enable_deadlock_check;
#endif
    }
};
// ACTUAL_CONFIG_SEED
constexpr swr_phpcoroutines_config_state seed{SW_DEFAULT_MAX_CORO_NUM, 0, 0, 0};
static_assert(seed.max_num == SW_DEFAULT_MAX_CORO_NUM && seed.hook_flags == 0 &&
              seed.preemptive == 0 && seed.disable_deadlock == 0, "constant native seed");
static_assert(sizeof(PHPCoroutine::Config) == sizeof(swr_phpcoroutines_config_state), "Config POD size");
static_assert(alignof(PHPCoroutine::Config) == alignof(swr_phpcoroutines_config_state), "Config POD alignment");
static_assert(offsetof(PHPCoroutine::Config, max_num) == offsetof(swr_phpcoroutines_config_state, max_num), "maximum slot");
static_assert(offsetof(PHPCoroutine::Config, hook_flags) == offsetof(swr_phpcoroutines_config_state, hook_flags), "hook slot");
void defaults() {
    assert(PHPCoroutine::get_max_num() == 77 && PHPCoroutine::get_hook_flags() == 0);
    assert(!PHPCoroutine::preemptive() && PHPCoroutine::deadlock());
}
int main() {
    defaults();
    for (uint64_t value : {uint64_t(0), uint64_t(1), std::numeric_limits<uint64_t>::max()}) {
        PHPCoroutine::set_max_num(value);
        assert(PHPCoroutine::get_max_num() == value);
        std::cout << "max:" << value << '\n';
    }
    for (uint32_t flags : {uint32_t(0), uint32_t(0x80000001u), std::numeric_limits<uint32_t>::max()}) {
        PHPCoroutine::hooks(flags);
        assert(PHPCoroutine::get_hook_flags() == flags);
        std::cout << "hooks:" << flags << '\n';
    }
    for (bool preemptive : {false, true}) for (bool deadlock : {false, true}) {
        PHPCoroutine::enable_preemptive_scheduler(preemptive);
        PHPCoroutine::set_deadlock_check(deadlock);
        assert(PHPCoroutine::preemptive() == preemptive && PHPCoroutine::deadlock() == deadlock);
        std::cout << "flags:" << preemptive << deadlock << '\n';
    }
    PHPCoroutine::set_deadlock_check();
    assert(PHPCoroutine::deadlock());
    PHPCoroutine::set_max_num(9); PHPCoroutine::hooks(11);
    PHPCoroutine::enable_preemptive_scheduler(true); PHPCoroutine::set_deadlock_check(false);
    std::thread worker([] {
#if CONFIG_THREAD_LOCAL
        defaults();
#else
        assert(PHPCoroutine::get_max_num() == 9 && PHPCoroutine::get_hook_flags() == 11);
        assert(PHPCoroutine::preemptive() && !PHPCoroutine::deadlock());
#endif
        PHPCoroutine::set_max_num(21); PHPCoroutine::hooks(31);
        PHPCoroutine::enable_preemptive_scheduler(false); PHPCoroutine::set_deadlock_check(true);
    });
    worker.join();
#if CONFIG_THREAD_LOCAL
    assert(PHPCoroutine::get_max_num() == 9 && PHPCoroutine::get_hook_flags() == 11);
    assert(PHPCoroutine::preemptive() && !PHPCoroutine::deadlock());
#else
    assert(PHPCoroutine::get_max_num() == 21 && PHPCoroutine::get_hook_flags() == 31);
    assert(!PHPCoroutine::preemptive() && PHPCoroutine::deadlock());
#endif
    // Distinct original field locations remain distinct; no packed-byte RMW or
    // whole-state mutable borrow/read is introduced for these serialized owners.
    std::thread max_writer([] { for (uint64_t value = 1; value <= 1000; ++value) {
        PHPCoroutine::set_max_num(value); assert(PHPCoroutine::get_max_num() == value);
    }});
    std::thread hook_writer([] { for (uint32_t value = 1; value <= 1000; ++value) {
        PHPCoroutine::hooks(value); assert(PHPCoroutine::get_hook_flags() == value);
    }});
    max_writer.join(); hook_writer.join();
#if !CONFIG_THREAD_LOCAL
    assert(PHPCoroutine::get_max_num() == 1000 && PHPCoroutine::get_hook_flags() == 1000);
#endif
    std::cout << "scope:" << CONFIG_THREAD_LOCAL << "\n";
}
