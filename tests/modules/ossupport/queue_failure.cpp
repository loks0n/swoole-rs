// SPDX-License-Identifier: Apache-2.0
// Include the exact selected native facade, not a handwritten class/layout mirror.
#ifndef SWRO_ASYNC_SOURCE
#error "exact patched async_thread.cc path required"
#endif
#include SWRO_ASYNC_SOURCE
#include <cassert>
#include <cstdio>
extern "C" void swr_test_os_queue_allocation_failure(bool);
int main() {
    using swoole::async::EventQueue;
    swr_test_os_queue_allocation_failure(true);
    bool failed=false;
    try { EventQueue queue; } catch(const std::bad_alloc &) { failed=true; }
    assert(failed);
    EventQueue queue;
    swr_test_os_queue_allocation_failure(true);
    failed=false;
    try { queue.push(reinterpret_cast<swoole::AsyncEvent *>(1)); } catch(const std::bad_alloc &) { failed=true; }
    assert(failed && queue.empty());
    queue.push(reinterpret_cast<swoole::AsyncEvent *>(1));
    size_t count=1;
    failed=false;
    for(;count<1024;++count) {
        swr_test_os_queue_allocation_failure(true);
        try { queue.push(reinterpret_cast<swoole::AsyncEvent *>(count+1)); }
        catch(const std::bad_alloc &) { failed=true;break; }
    }
    swr_test_os_queue_allocation_failure(false);
    assert(failed && queue.count()==count);
    for(size_t n=0;n<count;++n)assert(queue.pop()==reinterpret_cast<swoole::AsyncEvent *>(n+1));
    assert(queue.empty());
    puts("actual native EventQueue facade creation/first-push/growth OOM throws after Rust returns; FIFO unchanged");
}
