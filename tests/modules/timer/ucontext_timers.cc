// Timer-owned lifetime witness; native scheduler/context bodies remain unchanged.
#include "swoole_coroutine.h"
#include "swoole_coroutine_context.h"
#include "swoole_timer.h"
#include <cstdlib>
#include <iostream>
#include <thread>

#if !defined(USE_UCONTEXT) || defined(SW_USE_THREAD_CONTEXT) || defined(USE_ASM_CONTEXT)
#error This witness requires the actual native ucontext configuration.
#endif

static void require(bool value) { if (!value) std::abort(); }

int main() {
    swoole_init();
    const auto owner = std::this_thread::get_id();
    int expired = 0, canceled = 0, ticks = 0, resumed = 0;
    require(swoole::coroutine::run([&](void *) {
        auto *co = swoole::Coroutine::get_current();
        require(co != nullptr && std::this_thread::get_id() == owner);
        // The native timeout callback resumes this stack while its timer is active.
        require(!co->yield_ex(0.002));
        require(co->is_timedout() && swoole_get_last_error() == SW_ERROR_CO_TIMEDOUT);
        ++expired;
        require(std::this_thread::get_id() == owner);

        require(swoole_timer_after(2, [&](swoole::Timer *, swoole::TimerNode *) {
            require(std::this_thread::get_id() == owner);
            require(co->cancel()); // No co access after this synchronous resumption.
        }) > 0);
        require(!co->yield_ex(0.1));
        require(co->is_canceled() && swoole_get_last_error() == SW_ERROR_CO_CANCELED);
        ++canceled;

        require(swoole_timer_tick(2, [&](swoole::Timer *, swoole::TimerNode *node) {
            require(std::this_thread::get_id() == owner);
            ++ticks;
            if (ticks == 3) {
                require(swoole_timer_del(node)); // Active removal before resume.
                co->resume(); // Resumed stack may finish; no later co/node access.
            }
        }) > 0);
        co->yield();
        require(ticks == 3 && std::this_thread::get_id() == owner);

        require(swoole_timer_after(2, [&](swoole::Timer *, swoole::TimerNode *) {
            co->resume(); // Final resumption synchronously destroys the coroutine.
        }) > 0);
        co->yield();
        ++resumed;
        require(std::this_thread::get_id() == owner);
    }));
    require(swoole::Coroutine::count() == 0);
    require(!swoole_timer_is_available() || sw_timer()->count() == 0);
    require(expired == 1 && canceled == 1 && ticks == 3 && resumed == 1);
    swoole_clean();
    std::cout << "{\"context\":\"ucontext\",\"expired\":1,\"canceled\":1,\"ticks\":3,\"resumed\":1,\"coroutines\":0,\"timers\":0,\"owner_thread\":true}\n";
}
