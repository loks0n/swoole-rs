// Whole statistics bodies with inert getter and Zend-publication trace recorders.
#include <cassert>
#include <cstdint>
#include <iostream>
#include <string>
#include <vector>
#include "swoole_rs_phpcoroutines.h"
using zend_long = int64_t;
#define PHP_METHOD(a, b) void statistics()
#define ZEND_STRL(s) s, sizeof(s) - 1
void *return_value = nullptr;
std::vector<std::string> trace;
void array_init(void *) { trace.push_back("array"); }
void add_assoc_long_ex(void *, const char *key, size_t length, zend_long value) {
    trace.push_back("field:" + std::string(key, length) + ':' + std::to_string(value));
}
struct Reactor {
    size_t get_event_num() { trace.push_back("event"); return 11; }
} reactor;
struct Async {
    size_t get_task_num() { trace.push_back("aio-task"); return 21; }
    size_t get_worker_num() { trace.push_back("aio-worker"); return 22; }
    size_t get_queue_size() { trace.push_back("aio-queue"); return 23; }
} async;
struct IOUring {
    size_t get_task_num() { trace.push_back("io-task"); return 31; }
    double get_sq_usage_percent() { trace.push_back("io-sq"); return 32.75; }
    size_t get_waiting_task_num() { trace.push_back("io-waiting"); return 33; }
} ring;
struct { IOUring *iouring = nullptr; } SwooleTG;
bool event_present, async_present;
Reactor *sw_reactor() { trace.push_back("reactor"); return event_present ? &reactor : nullptr; }
Async *sw_async_threads() { trace.push_back("async"); return async_present ? &async : nullptr; }
size_t swoole_signal_get_listener_num() { trace.push_back("signal"); return 12; }
namespace Coroutine {
size_t get_stack_size() { trace.push_back("stack"); return 41; }
size_t count() { trace.push_back("count"); return 42; }
size_t get_peak_num() { trace.push_back("peak"); return 43; }
long get_last_cid() { trace.push_back("last"); return 44; }
}
// ACTUAL_BODY
int main() {
    for (unsigned configuration = 0; configuration < 8; ++configuration) {
        event_present = configuration & 1;
        async_present = configuration & 2;
        SwooleTG.iouring = configuration & 4 ? &ring : nullptr;
        trace.clear();
        statistics();
        unsigned fields = 0;
        for (const auto &entry : trace) if (entry.find("field:") == 0) ++fields;
#ifdef SW_USE_IOURING
        assert(fields == (SwooleTG.iouring ? 12 : 9));
#else
        assert(fields == 9);
#endif
        std::cout << configuration << '\n';
        for (const auto &entry : trace) std::cout << entry << '\n';
    }
}
