// SPDX-License-Identifier: Apache-2.0
// Test-only scheduling barriers expose a legal last-reactor/idle-retirement interleaving.
#include "swoole_socket.h"
#include "swoole_async.h"
#include <atomic>
#include <cassert>
#include <cstdio>
#include <unistd.h>
static std::atomic<bool> first_started{false},retirement_ready{false},shutdown_started{false};
static std::atomic<int> handled{0},retirement_sent{0},retirement_callbacks{0};
static int callbacks=0;
extern "C" void swr_test_retirement_wait() {
    retirement_ready=true;
    while(!shutdown_started.load())usleep(1000);
}
extern "C" void swr_test_shutdown_begin() { shutdown_started=true; }
extern "C" long swr_test_observe_send(long result,bool retirement) {
    if(retirement && result>0)++retirement_sent;
    return result;
}
extern "C" void swr_test_retirement_callback() { ++retirement_callbacks; }
static void callback(swoole::AsyncEvent *) { ++callbacks; }
int main() {
    swoole_init();
    SwooleG.aio_core_worker_num=1;
    SwooleG.aio_worker_num=2;
    SwooleG.aio_max_wait_time=0.0001;
    SwooleG.aio_max_idle_time=0.5; // Preserve original cast to zero microseconds.
    swoole_event_init(SW_EVENTLOOP_WAIT_EXIT);
    swoole::AsyncEvent first{};
    first.callback=callback;
    first.handler=[](swoole::AsyncEvent *){
        first_started=true;
        while(!retirement_ready.load())usleep(1000);
        ++handled;
    };
    assert(swoole::async::dispatch(&first));
    while(!first_started.load())usleep(1000);
    swoole::AsyncEvent other{};
    other.callback=callback;
    other.handler=[](swoole::AsyncEvent *){++handled;};
    assert(swoole::async::dispatch(&other));
    usleep(100000); // Old queued task must age beyond original expansion threshold.
    assert(swoole::async::dispatch(&other));
    swoole_event_wait();
    assert(handled==3 && callbacks==3 && retirement_sent==1);
    assert(SwooleTG.async_threads==nullptr);
    swoole_clean();
    std::printf("ordinary_handlers=%d callbacks=%d retirement_sent=%d retirement_callbacks=%d\n",handled.load(),callbacks,retirement_sent.load(),retirement_callbacks.load());
    std::fflush(stdout);
    if(retirement_callbacks!=retirement_sent) {
        std::fputs("FAILED: idle-retirement notification sent after reactor teardown began, never consumed\n",stderr);
        return 3;
    }
}
