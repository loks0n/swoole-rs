// SPDX-License-Identifier: Apache-2.0
// Linux executable symbol interposition: bounded syscall failures, never host
// resource exhaustion. Every intercepted call and errno observation is asserted.
#include "swoole.h"
#include "swoole_api.h"
#include <cerrno>
#include <cstdio>
#include <stdexcept>
#include <unistd.h>

static int fork_calls, sleep_calls;
static bool exec_mode;
static void require(bool good) {
    if (!good) throw std::runtime_error("injected fork failure witness failed");
}
extern "C" pid_t fork(void) noexcept {
    ++fork_calls;
    if (exec_mode || fork_calls == 1) { errno = EAGAIN; return -1; }
    if (fork_calls == 2) { errno = EINTR; return -1; }
    return 12345; // simulated parent; no child/reset branch is executed
}
extern "C" unsigned int sleep(unsigned int seconds) {
    require(!exec_mode && seconds == 1 && fork_calls == sleep_calls + 1);
    require(swoole_get_last_error() == (fork_calls == 1 ? EAGAIN : EINTR));
    ++sleep_calls;
    errno = EBUSY; // next failing fork must replace this before warning
    return 0;
}
int main() {
    swoole_init();
    swoole_set_log_level(SW_LOG_NONE); // warning still publishes last_error
    auto *pool = SwooleG.memory_pool;
    require(swoole_fork(0) == 12345 && fork_calls == 3 && sleep_calls == 2);
    require(SwooleG.memory_pool == pool && swoole_get_last_error() == EINTR);
    std::puts("fork-fail:two-errors,two-warn-last-errors,two-sleep1,then-parent-no-reset");
    fork_calls = sleep_calls = 0;
    exec_mode = true;
    swoole_set_last_error(4242);
    bool callback = false;
    require(swoole_fork_exec([&] { callback = true; }) == 0);
    require(fork_calls == 1 && sleep_calls == 0 && !callback && errno == EAGAIN);
    require(swoole_get_last_error() == 4242 && SwooleG.memory_pool == pool);
    std::puts("fork-exec-fail:pid0,no-warning,no-retry,no-callback,no-reset");
    swoole_clean();
    return 0;
}
