#include <cassert>
#include <cstdint>
#include <iostream>
#include <limits>
#include <queue>
#include <string>
#include <vector>
#include "swoole_rs_phpcoroutines.h"
using zend_long = int64_t;
struct zend_fcall_info { int id; unsigned param_count; void *params; int function_name; };
struct zend_fcall_info_cache { int id; };
struct zend_object { int unused; };
std::vector<std::string> trace;
void sw_zend_fci_cache_persist(zend_fcall_info_cache *f) { trace.push_back("persist-cache:" + std::to_string(f->id)); }
void sw_zend_fci_params_persist(zend_fcall_info *f) { trace.push_back("persist-args:" + std::to_string(f->id)); }
void sw_zend_fci_cache_discard(zend_fcall_info_cache *f) { trace.push_back("discard-cache:" + std::to_string(f->id)); }
void sw_zend_fci_params_discard(zend_fcall_info *f) { trace.push_back("discard-args:" + std::to_string(f->id)); }
namespace PHPCoroutine {
void create(zend_fcall_info_cache *f, unsigned, void *, int *) { trace.push_back("create-stub:" + std::to_string(f->id)); }
}
int php_swoole_reactor_init() { trace.push_back("reactor-init-stub"); return 0; }
void php_swoole_event_wait() { trace.push_back("event-wait-stub"); }
#define PHP_METHOD(class_name, method) void method()
#define ZEND_THIS nullptr
#define Z_OBJ_P(object) nullptr
#define SW_Z_OBJCE_NAME_VAL_P(object) "model"
#define E_WARNING 1
void php_swoole_fatal_error(int, const char *, ...) { assert(false); }
#define RETURN_FALSE return
#define RETURN_TRUE return
// ACTUAL_TYPES
SchedulerObject current{};
SchedulerObject *scheduler_get_object(zend_object *) { return &current; }
void efree(SchedulerTask *task) { trace.push_back("free:" + std::to_string(task->fci.id)); delete task; }
// ACTUAL_ADD
// ACTUAL_START
int main() {
    const std::vector<zend_long> counts{1, 3, 0, -1, 2, std::numeric_limits<zend_long>::min()};
    for (size_t i = 0; i < counts.size(); ++i) {
        auto *task = new SchedulerTask{};
        task->fci.id = task->fci_cache.id = int(i + 1);
#ifdef SWOOLE_RS_PHPCOROUTINES
        scheduler_add_task(&current, task, counts[i]);
#else
        task->count = counts[i];
        scheduler_add_task(&current, task);
#endif
    }
#ifdef SWOOLE_RS_PHPCOROUTINES
    assert(!swr_v1_phpcoroutines_scheduler_phase(&current.started, SWR_CORO_SCHED_PHASE_READ) && current.list);
#else
    assert(!current.started && current.list);
#endif
    start();
#ifdef SWOOLE_RS_PHPCOROUTINES
    assert(!swr_v1_phpcoroutines_scheduler_phase(&current.started, SWR_CORO_SCHED_PHASE_READ) && !current.list);
#else
    assert(!current.started && !current.list);
#endif
    for (const auto &event : trace) std::cout << event << '\n';
#ifdef SWOOLE_RS_PHPCOROUTINES
    auto *queue = swr_v1_phpcoroutines_scheduler_new();
    for (uintptr_t i = 1; i <= 4096; ++i) swr_v1_phpcoroutines_scheduler_push(queue, i, int64_t(i));
    swr_phpcoroutines_scheduler_task next{};
    for (uintptr_t i = 1; i <= 4096; ++i) {
        assert(swr_v1_phpcoroutines_scheduler_pop(queue, &next));
        assert(next.token == i && next.repetitions == i);
    }
    assert(!swr_v1_phpcoroutines_scheduler_pop(queue, &next));
    swr_v1_phpcoroutines_scheduler_push(queue, 0, std::numeric_limits<int64_t>::max());
    assert(swr_v1_phpcoroutines_scheduler_pop(queue, &next));
    assert(next.token == 0 && next.repetitions == uint64_t(std::numeric_limits<int64_t>::max()));
    swr_v1_phpcoroutines_scheduler_drop(queue);
    auto *autoload = swr_v1_phpcoroutines_autoload_new();
    std::queue<uintptr_t> reference;
    for (uintptr_t i = 0; i < 4096; ++i) {
        reference.push(i);
        swr_v1_phpcoroutines_autoload_push(autoload, i);
    }
    uintptr_t token = 99999;
    while (!reference.empty()) {
        assert(swr_v1_phpcoroutines_autoload_pop(autoload, &token) && token == reference.front());
        reference.pop();
    }
    assert(!swr_v1_phpcoroutines_autoload_pop(autoload, &token) && token == 4095);
    swr_v1_phpcoroutines_autoload_drop(autoload);
#endif
}
