// SPDX-License-Identifier: Apache-2.0
// Real native lifecycle witnesses; these do not claim Rust hook conversion.
#include "swoole.h"
#include "swoole_string.h"
#include "swoole_timer.h"
#include "swoole_signal.h"
#include <iostream>
#include <list>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <pthread.h>
#include <signal.h>

static void require_at(bool good, const char *condition, int line) {
    if (!good) throw std::runtime_error(std::string("hook lifetime witness line ") + std::to_string(line) + ": " + condition);
}
#define require(value) require_at((value), #value, __LINE__)

struct CopyFailure {
    bool *fail;
    explicit CopyFailure(bool *flag) : fail(flag) {}
    CopyFailure(const CopyFailure &other) : fail(other.fail) {
        if (*fail) throw std::runtime_error("expected copy failure");
    }
    void operator()(void *) const {}
};

int main() {
    using Hooks = std::list<swoole::Callback>;
    void *hooks[1] = {nullptr};
    std::string trace;
    swoole::hook_call(hooks, 0, nullptr);
    require(!hooks[0]);
    bool expanded = false;
    swoole::hook_add(hooks, 0, [&](void *) {
        trace += 'A';
        if (!expanded) {
            expanded = true;
            swoole::hook_add(hooks, 0, [&](void *) { trace += 'C'; }, 1);
            swoole::hook_add(hooks, 0, [&](void *) { trace += 'D'; }, 0);
        }
    }, 1);
    swoole::hook_add(hooks, 0, [&](void *) { trace += 'B'; }, 1);
    swoole::hook_call(hooks, 0, nullptr);
    require(trace == "ABC");
    trace.clear();
    swoole::hook_call(hooks, 0, nullptr);
    require(trace == "DABC");
    delete static_cast<Hooks *>(hooks[0]); hooks[0] = nullptr;
    std::cout << "live-append/front:ABC,DABC\n";

    bool fail = false;
    swoole::Callback callback = CopyFailure(&fail);
    fail = true;
    bool caught = false;
    try { swoole::hook_add(hooks, 0, callback, 1); }
    catch (const std::runtime_error &) { caught = true; }
    require(caught && hooks[0] && static_cast<Hooks *>(hooks[0])->empty());
    swoole::hook_add(hooks, 0, [&](void *) { trace += 'R'; }, 1);
    trace.clear(); swoole::hook_call(hooks, 0, nullptr); require(trace == "R");
    delete static_cast<Hooks *>(hooks[0]); hooks[0] = nullptr;
    std::cout << "copy-failure:published-empty,recovered\n";

    bool throws = true;
    swoole::hook_add(hooks, 0, [&](void *) {
        trace += 'E'; if (throws) throw std::runtime_error("expected callback failure");
    }, 1);
    swoole::hook_add(hooks, 0, [&](void *) { trace += 'F'; }, 1);
    trace.clear(); caught = false;
    try { swoole::hook_call(hooks, 0, nullptr); }
    catch (const std::runtime_error &) { caught = true; }
    require(caught && trace == "E");
    throws = false; trace.clear(); swoole::hook_call(hooks, 0, nullptr); require(trace == "EF");
    delete static_cast<Hooks *>(hooks[0]);
    std::cout << "callback-exception:E,EF\n";

    swoole_init();
    bool destroyed = false, published = false, logger_alive = false, buffer_alive = false;
    {
        std::shared_ptr<int> token(new int(1), [&](int *value) {
            destroyed = true;
            // Observe publication only; never dereference the list being deleted.
            published = SwooleG.hooks[0] != nullptr;
            logger_alive = SwooleG.logger != nullptr;
            buffer_alive = SwooleTG.buffer_stack != nullptr;
            delete value;
        });
        swoole::hook_add(SwooleG.hooks, 0, [token](void *) {}, 1);
    }
    require(!destroyed);
    swoole_clean();
    require(destroyed && published && logger_alive && buffer_alive);
    require(!SwooleG.init && !SwooleG.hooks[0] && !SwooleG.logger && !SwooleTG.buffer_stack);
    std::cout << "clean-capture:hook-published,logger-alive,buffer-alive,then-zero\n";

    swoole_init();
    bool early = false, late = false, late_before_cleanup = false;
    {
        std::shared_ptr<int> token(new int(1), [&](int *value) {
            early = true;
            std::shared_ptr<int> later(new int(2), [&](int *last) {
                late = true;
                late_before_cleanup = SwooleG.logger && SwooleTG.buffer_stack;
                delete last;
            });
            const auto last_slot = sizeof(SwooleG.hooks) / sizeof(SwooleG.hooks[0]) - 1;
            require(SwooleG.hooks[last_slot] == nullptr);
            swoole::hook_add(SwooleG.hooks, last_slot, [later](void *) {}, 1);
            delete value;
        });
        swoole::hook_add(SwooleG.hooks, 0, [token](void *) {}, 1);
    }
    swoole_clean();
    require(early && late && late_before_cleanup && !SwooleG.init);
    std::cout << "clean-mutation:later-slot-observed-and-destroyed-before-thread\n";

    swoole_init();
    delete SwooleTG.buffer_stack;
    SwooleTG.buffer_stack = nullptr;
    auto *timer = new swoole::Timer(true);
    SwooleTG.timer = timer;
    bool timer_published = false;
    auto *node = timer->add(1000, false, nullptr, [](swoole::Timer *, swoole::TimerNode *) {});
    require(node != nullptr);
    node->destructor = [&](swoole::TimerNode *) {
        timer_published = SwooleTG.timer == timer;
        require(SwooleTG.buffer_stack == nullptr);
        SwooleTG.buffer_stack = new swoole::String(128);
    };
    swoole_thread_clean(true);
    require(timer_published && !SwooleTG.timer && !SwooleTG.buffer_stack);
    swoole_clean();
    std::cout << "thread-clean:fresh-buffer-after-timer,delete-before-null\n";

    swoole_init();
    sigset_t main_mask;
    require(pthread_sigmask(SIG_SETMASK, nullptr, &main_mask) == 0);
    std::thread worker([] {
        require(!SwooleTG.buffer_stack && !SwooleTG.timer && !SwooleTG.reactor);
        auto unblock = [] {
            sigset_t mask;
            require(sigemptyset(&mask) == 0 && sigaddset(&mask, SIGUSR1) == 0);
            require(pthread_sigmask(SIG_UNBLOCK, &mask, nullptr) == 0);
        };
        auto blocked = [] {
            sigset_t mask;
            require(pthread_sigmask(SIG_SETMASK, nullptr, &mask) == 0);
            return sigismember(&mask, SIGUSR1);
        };
        unblock(); swoole_thread_init(false);
        auto *buffer = SwooleTG.buffer_stack;
        require(buffer && !SwooleTG.main_thread && blocked() == 1);
        unblock(); swoole_thread_init(false);
        require(SwooleTG.buffer_stack == buffer && !SwooleTG.main_thread && blocked() == 0 && SwooleTG.signal_blocking_all);
        swoole_signal_unblock_all(); swoole_thread_init(false);
        require(SwooleTG.buffer_stack == buffer && blocked() == 1 && SwooleTG.signal_blocking_all);
        swoole_signal_unblock_all(); swoole_thread_init(true);
        require(SwooleTG.buffer_stack == buffer && SwooleTG.main_thread && blocked() == 0);
        swoole_thread_clean(false); swoole_thread_clean(true);
        require(!SwooleTG.buffer_stack && SwooleTG.main_thread);
    });
    worker.join();
    sigset_t after_mask;
    require(pthread_sigmask(SIG_SETMASK, nullptr, &after_mask) == 0);
    require(sigismember(&main_mask, SIGUSR1) == sigismember(&after_mask, SIGUSR1));
    swoole_clean();
    std::cout << "thread-init:allocate,reuse,native-mask-guard,nonmain-block,main-preserve,clean\n";
    return 0;
}
