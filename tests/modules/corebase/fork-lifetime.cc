// SPDX-License-Identifier: Apache-2.0
// Actual fork-mask, returning-handler and lifetime witnesses.
#include "swoole.h"
#include "swoole_api.h"
#include "swoole_async.h"
#include "swoole_coroutine.h"
#include <string>
#include <vector>
#include <cstdio>
#include <stdexcept>
#include <sys/wait.h>
#include <unistd.h>

static void require(bool good) {
    if (!good) throw std::runtime_error("fork lifetime witness failed");
}

struct Observation { int hooks; int pool_same; int cleaned; };
static std::vector<std::string> fatal_messages;
static swoole::AsyncThreads *published_pool;
static void returning_fatal(int code, const char *message, ...) {
    require(code == SW_ERROR_OPERATION_NOT_SUPPORT);
    fatal_messages.emplace_back(message);
    // First rejection publishes a real native pool; the next guard must see it.
    if (fatal_messages.back() == "must be forked outside the coroutine")
        SwooleTG.async_threads = published_pool;
}

int main() {
    swoole_init();
    int hooks = 0;
    swoole::hook_add(SwooleG.hooks, SW_GLOBAL_HOOK_AFTER_FORK, [&](void *) { ++hooks; }, 1);
    auto *pool = SwooleG.memory_pool;
    const pid_t parent = getpid();
    for (int mask = 0; mask < 8; ++mask) {
        const int flags = ((mask & 1) ? SW_FORK_EXEC : 0)
                        | ((mask & 2) ? SW_FORK_DAEMON : 0)
                        | ((mask & 4) ? SW_FORK_PRECHECK : 0);
        if (flags & SW_FORK_PRECHECK) {
            require(swoole_fork(flags) == 0 && getpid() == parent && hooks == 0 && SwooleG.memory_pool == pool);
            std::printf("mask%d:precheck,no-child,no-hook\n", mask); std::fflush(stdout);
            continue;
        }
        int fds[2]; require(pipe(fds) == 0);
        std::fflush(nullptr);
        pid_t child = swoole_fork(flags);
        if (child == 0) {
            close(fds[0]);
            Observation result{hooks, SwooleG.memory_pool == pool, 0};
            swoole_clean();
            result.cleaned = !SwooleG.init && !SwooleG.memory_pool && !SwooleTG.buffer_stack;
            const bool sent = write(fds[1], &result, sizeof(result)) == sizeof(result);
            close(fds[1]); _exit(sent ? 0 : 4);
        }
        require(child > 0); close(fds[1]);
        Observation result{};
        require(read(fds[0], &result, sizeof(result)) == sizeof(result)); close(fds[0]);
        int status; require(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0);
        const bool daemon = flags & SW_FORK_DAEMON;
        require(result.hooks == (daemon ? 0 : 1));
        require(result.pool_same == bool(flags & (SW_FORK_EXEC | SW_FORK_DAEMON)) && result.cleaned);
        require(hooks == 0 && SwooleG.memory_pool == pool && SwooleG.init);
        std::printf("mask%d:hook%d,pool-%s,child-clean,parent-intact\n", mask, result.hooks,
                    result.pool_same ? "same" : "new"); std::fflush(stdout);
    }
    int fds[2]; require(pipe(fds) == 0); std::fflush(nullptr);
    pid_t child = swoole_fork_exec([&] {
        close(fds[0]);
        const int unchanged = hooks == 0 && SwooleG.memory_pool == pool && SwooleG.init;
        if (write(fds[1], &unchanged, sizeof(unchanged)) != sizeof(unchanged)) _exit(5);
        close(fds[1]);
    });
    require(child > 0); close(fds[1]); int unchanged = 0;
    require(read(fds[0], &unchanged, sizeof(unchanged)) == sizeof(unchanged)); close(fds[0]);
    int status; require(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0 && unchanged);
    require(hooks == 0 && SwooleG.memory_pool == pool);
    // PRECHECK guarantees no OS fork while the real native async worker exists.
    SwooleG.aio_core_worker_num = 1;
    SwooleG.aio_worker_num = 1;
    require(swoole_event_init(SW_EVENTLOOP_WAIT_EXIT) == SW_OK);
    published_pool = new swoole::AsyncThreads();
    require(SwooleTG.async_threads == published_pool && published_pool->task_num == 0);
    auto old_fatal = SwooleG.fatal_error;
    SwooleG.fatal_error = returning_fatal;
    require(swoole_fork(SW_FORK_PRECHECK) == 0);
    require(fatal_messages == std::vector<std::string>{"can not fork after using async-threads"});
    fatal_messages.clear();
    // Keep the fully initialized pool alive, but publish it from the first fatal
    // handler. No event polling/callback runs while it is temporarily absent.
    SwooleTG.async_threads = nullptr;
    bool coroutine_ok = false;
    long cid = swoole::Coroutine::create([&](void *) {
        coroutine_ok = swoole_fork(SW_FORK_PRECHECK) == 0;
        coroutine_ok = coroutine_ok && fatal_messages == std::vector<std::string>{
            "must be forked outside the coroutine", "can not fork after using async-threads"};
        fatal_messages.clear();
        coroutine_ok = coroutine_ok && swoole_fork(SW_FORK_EXEC | SW_FORK_PRECHECK) == 0
                       && fatal_messages.empty();
    });
    require(cid > 0 && coroutine_ok && SwooleTG.async_threads == published_pool);
    SwooleG.fatal_error = old_fatal;
    swoole_event_free(); // native destroy callback deletes pool and joins workers
    require(!SwooleTG.async_threads && !SwooleTG.reactor);
    std::puts("guards:zero-task-pool,reject-after-returning-coroutine-handler,exec-bypass,precheck-no-fork");
    swoole_clean();
    require(!SwooleG.init && !SwooleG.memory_pool && !SwooleTG.buffer_stack);
    std::puts("fork-exec:callback,no-hook,pool-same,parent-clean");
    return 0;
}
