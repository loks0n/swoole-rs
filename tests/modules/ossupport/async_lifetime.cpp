// SPDX-License-Identifier: Apache-2.0
// Actual native worker queue consumers; no private layout mirror or event ownership in Rust.
#include "swoole_socket.h"
#include "swoole_async.h"
#include <atomic>
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <unistd.h>
using namespace swoole;
struct State {
    std::atomic<int> handled{0};
    int callbacks=0;
    int bad=0;
};
static void handler(AsyncEvent *event) {
    usleep(1000);
    ++static_cast<State *>(event->object)->handled;
}
static void callback(AsyncEvent *event) {
    assert(event->error==0);
    ++static_cast<State *>(event->object)->callbacks;
}
static void reenter(AsyncEvent *event) {
    callback(event);
    AsyncEvent nested{};
    nested.object=event->object;
    nested.handler=handler;
    nested.callback=callback;
    assert(async::dispatch(&nested));
}
int main(int argc,char **argv) {
    assert(argc==1 || (argc==2 && (std::strtod(argv[1],nullptr)==0.0 || std::strtod(argv[1],nullptr)==0.5)));
    swoole_init();
    SwooleG.aio_core_worker_num=2;
    SwooleG.aio_worker_num=8;
    SwooleG.aio_max_wait_time=0.0001;
    SwooleG.aio_max_idle_time=argc==2?std::strtod(argv[1],nullptr):0.5;
    for(int round=0;round<8;++round) {
        State state;
        swoole_event_init(SW_EVENTLOOP_WAIT_EXIT);
        for(int n=0;n<64;++n) {
            AsyncEvent event{};
            event.object=&state;
            event.handler=handler;
            event.callback=(n%8==0)?reenter:callback;
            assert(async::dispatch(&event));
        }
        AsyncEvent canceled{};
        canceled.object=&state;
        canceled.handler=handler;
        canceled.callback=[](AsyncEvent *){assert(false && "canceled completion callback must be suppressed");};
        canceled.canceled=1; // Copied before publication, no racing cancellation mutation.
        assert(async::dispatch(&canceled));
        AsyncEvent bad{};
        bad.object=&state;
        bad.callback=[](AsyncEvent *event){assert(event->retval==-1 && event->error==SW_ERROR_AIO_BAD_REQUEST);++static_cast<State *>(event->object)->bad;};
        assert(async::dispatch(&bad));
        bad.canceled=1;
        bad.callback=[](AsyncEvent *){assert(false && "canceled invalid request callback must be suppressed");};
        assert(async::dispatch(&bad));
        swoole_event_wait();
        assert(state.handled==72 && state.callbacks==72 && state.bad==1);
        assert(SwooleTG.async_threads==nullptr);
    }
    swoole_clean();
    puts("8 native pool teardown/reinit rounds:576 handler/callback pairs,8 reentrant batches,24 canceled/invalid events passed");
}
