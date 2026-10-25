// Supplemental Linux/PHP8.2 observation: stop only this diagnostic after 8 rounds.
extern "C" {
#include "php.h"
}
#include "swoole_reactor.h"
#include "swoole_timer.h"
#include <cstdio>

#if PHP_VERSION_ID < 80200 || PHP_VERSION_ID >= 80300 || !defined(ZEND_HAS_OOM)
#error "Diagnostic requires the actual PHP8.2 delayed-OOM headers"
#endif

extern "C" int swr_timer_oom_arm(long id, unsigned int budget) {
    if (!SwooleTG.reactor || !SwooleTG.timer || budget != 8 || id <= 0) return -1;
    SwooleTG.reactor->set_end_callback(swoole::Reactor::PRIORITY_WORKER_CALLBACK,
        [id, budget, step = 0U](swoole::Reactor *reactor) mutable {
            ++step;
            auto *timer = SwooleTG.timer;
            auto *node = timer ? timer->get(id) : nullptr;
            std::fprintf(stderr,
                "NATIVE {\"step\":%u,\"timer_count\":%zu,\"timer_round\":%llu,"
                "\"exec_count\":%llu,\"removed\":%d,\"executor_active\":%d,"
                "\"exception\":%d,\"delayed_oom\":%d,\"last_error_type\":%d,"
                "\"exit_status\":%d,\"running_before_budget\":%d}\n",
                step, timer ? timer->count() : 0,
                static_cast<unsigned long long>(timer ? timer->get_round() : 0),
                static_cast<unsigned long long>(node ? node->exec_count : 0),
                node ? node->removed : -1, EG(active), EG(exception) != nullptr,
                static_cast<int>(EG(delayed_oom).state), PG(last_error_type),
                EG(exit_status), reactor->running);
            std::fflush(stderr);
            if (step == budget) reactor->running = false;
        });
    return 0;
}
