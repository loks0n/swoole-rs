// Primitive metadata scope/constant seed only; no PHP, activation or callbacks.
#include <cassert>
#include <cstdint>
#include <iostream>
#include <thread>
#include "swoole_rs_phpcoroutines.h"
#if ACTIVATED_THREAD_LOCAL
#define SW_THREAD_LOCAL thread_local
#else
#define SW_THREAD_LOCAL
#endif
struct PHPCoroutine {
// ACTUAL_ACTIVATED_DECL
// ACTUAL_ACTIVATED_BODY
    static void publish(bool value) {
#ifdef SWOOLE_RS_PHPCOROUTINES
        swr_v1_phpcoroutines_scheduler_phase(&activated, value ? SWR_CORO_SCHED_PHASE_START : SWR_CORO_SCHED_PHASE_STOP);
#else
        activated = value;
#endif
    }
};
// ACTUAL_ACTIVATED_SEED
#ifdef SWOOLE_RS_PHPCOROUTINES
constexpr swr_phpcoroutines_activation_state seed{0};
static_assert(seed.started == 0, "constant false seed");
static_assert(sizeof(swr_phpcoroutines_activation_state) == sizeof(bool), "original bool size");
static_assert(alignof(swr_phpcoroutines_activation_state) == alignof(bool), "original bool alignment");
#endif
int main() {
    assert(!PHPCoroutine::is_activated());
    PHPCoroutine::publish(true);
    assert(PHPCoroutine::is_activated());
    std::thread worker([] {
        assert(PHPCoroutine::is_activated() == !bool(ACTIVATED_THREAD_LOCAL));
        PHPCoroutine::publish(true);
        assert(PHPCoroutine::is_activated());
        PHPCoroutine::publish(false);
        assert(!PHPCoroutine::is_activated());
    });
    worker.join();
    assert(PHPCoroutine::is_activated() == bool(ACTIVATED_THREAD_LOCAL));
    PHPCoroutine::publish(true);
    auto read_only = [] {
        for (unsigned i = 0; i < 256; ++i) {
            assert(PHPCoroutine::is_activated() == !bool(ACTIVATED_THREAD_LOCAL));
        }
    };
    std::thread reader_a(read_only), reader_b(read_only);
    reader_a.join();
    reader_b.join();
    assert(PHPCoroutine::is_activated());
    PHPCoroutine::publish(false);
    assert(!PHPCoroutine::is_activated());
    std::thread fresh([] { assert(!PHPCoroutine::is_activated()); });
    fresh.join();
    std::cout << "constant-seed/scope/publication:" << ACTIVATED_THREAD_LOCAL << '\n';
}
