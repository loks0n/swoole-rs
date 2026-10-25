// SPDX-License-Identifier: Apache-2.0
// Linux executable C++new interposition: selected constructor failures, not
// system-wide OOM or malloc/sanitizer proof. No event services or fixed files.
#include "swoole.h"
#include "swoole_api.h"
#include <cstdio>
#include <cstdlib>
#include <new>
#include <stdexcept>

static long fail_at = -1;
static unsigned calls;
void *operator new(size_t size) {
    if (fail_at >= 0 && calls++ == static_cast<unsigned long>(fail_at)) throw std::bad_alloc();
    if (void *p = std::malloc(size ? size : 1)) return p;
    throw std::bad_alloc();
}
void *operator new[](size_t size) { return ::operator new(size); }
void operator delete(void *p) noexcept { std::free(p); }
void operator delete[](void *p) noexcept { std::free(p); }
void operator delete(void *p, size_t) noexcept { std::free(p); }
void operator delete[](void *p, size_t) noexcept { std::free(p); }
static void require(bool value) {
    if (!value) throw std::runtime_error("init lifetime witness failed");
}

int main() {
    for (long index = 0; index < 24; ++index) {
        calls = 0; fail_at = index;
        bool threw = false;
        try { swoole_init(); } catch (const std::bad_alloc &) { threw = true; }
        fail_at = -1;
        // Guard publication precedes every C++ allocation in this clean process.
        require(SwooleG.init && SwooleG.running && SwooleG.enable_coroutine);
        const unsigned observed_calls = calls;
        require(threw ? observed_calls == static_cast<unsigned>(index + 1)
                      : observed_calls <= static_cast<unsigned>(index));
        auto *logger = SwooleG.logger;
        auto *buffer = SwooleTG.buffer_stack;
        auto *pool = SwooleG.memory_pool;
        const auto sockets = SwooleG.max_sockets;
        const auto task = SwooleG.task_tmpfile;
        const auto bug = SwooleG.bug_report_message;
        // Repeated init after a partial constructor failure must not restart,
        // roll back, allocate, or replace any of the published native state.
        calls = 0; fail_at = 0;
        swoole_init();
        fail_at = -1;
        require(calls == 0 && SwooleG.logger == logger && SwooleTG.buffer_stack == buffer
                && SwooleG.memory_pool == pool && SwooleG.max_sockets == sockets
                && SwooleG.task_tmpfile == task && SwooleG.bug_report_message == bug);
        std::printf("case%ld:threw%d,calls%u,guard1,logger%d,buffer%d,pool%d,sockets%u,task%zu,bug%zu\n",
                    index, threw, observed_calls, logger != nullptr, buffer != nullptr, pool != nullptr,
                    static_cast<unsigned>(sockets), task.size(), bug.size());
        swoole_clean();
        require(!SwooleG.init && !SwooleG.logger && !SwooleG.memory_pool && !SwooleTG.buffer_stack);
    }
    return 0;
}
