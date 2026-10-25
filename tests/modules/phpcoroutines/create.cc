// Ordinary create admission/body: no Coroutine, PHP, context switch or callback execution.
#include <cassert>
#include <cstdint>
#include <iostream>
#include <string>
#include <vector>
#include "swoole_rs_phpcoroutines.h"
using zend_uchar = uint8_t;
struct zend_function { zend_uchar type; };
struct zend_fcall_info_cache { zend_function *function_handler; };
struct zval { int value; };
#define ZEND_USER_FUNCTION 2
#define ZEND_INTERNAL_FUNCTION 1
#define E_WARNING 1
#define E_ERROR 2
#define sw_unlikely(value) (value)
std::vector<std::string> trace;
void php_swoole_fatal_error(int, const char *, ...) { assert(false); }
namespace Coroutine {
constexpr long ERR_LIMIT = -1, ERR_INVALID = -2;
size_t count() { trace.push_back("count-stub"); return 2; }
long create(void (*fn)(void *), void *args);
}
class PHPCoroutine {
  public:
#ifdef SWOOLE_RS_PHPCOROUTINES
    using Config = swr_phpcoroutines_config_state;
#else
    struct Config { uint64_t max_num; };
#endif
    struct Args { zend_fcall_info_cache *fci_cache; zval *argv; uint32_t argc; zval *callable; };
    static Config config;
    static uint64_t get_max_num() {
#ifdef SWOOLE_RS_PHPCOROUTINES
        return swr_v1_phpcoroutines_config(&config, SWR_CORO_CONFIG_GET_MAX, 0);
#else
        return config.max_num;
#endif
    }
#ifdef SWOOLE_RS_PHPCOROUTINES
    static swr_phpcoroutines_activation_state activated;
    static bool is_activated() { return swr_v1_phpcoroutines_scheduler_phase(&activated, SWR_CORO_SCHED_PHASE_READ); }
    static void activate() { trace.push_back("activate-stub"); swr_v1_phpcoroutines_scheduler_phase(&activated, SWR_CORO_SCHED_PHASE_START); }
#else
    static bool activated;
    static bool is_activated() { return activated; }
    static void activate() { trace.push_back("activate-stub"); activated = true; }
#endif
    static void *get_context() { trace.push_back("get-context-stub"); return nullptr; }
    static void save_context(void *) { trace.push_back("save-context-stub"); }
    static void main_func(void *) { assert(false); }
    static long create(zend_fcall_info_cache *, uint32_t, zval *, zval *);
};
#ifdef SWOOLE_RS_PHPCOROUTINES
PHPCoroutine::Config PHPCoroutine::config{10, 0, 0, 0};
#else
PHPCoroutine::Config PHPCoroutine::config{10};
#endif
#ifdef SWOOLE_RS_PHPCOROUTINES
swr_phpcoroutines_activation_state PHPCoroutine::activated{0};
#else
bool PHPCoroutine::activated = false;
#endif
long Coroutine::create(void (*fn)(void *), void *opaque) {
    assert(fn == PHPCoroutine::main_func);
    auto *args = static_cast<PHPCoroutine::Args *>(opaque);
    assert(args->argc == 1 && args->argv->value == 13 && args->callable->value == 14);
    trace.push_back("create-stub:" + std::to_string(args->fci_cache->function_handler->type));
    return 102;
}
// ACTUAL_BODY
int main() {
    for (zend_uchar kind : {zend_uchar(ZEND_USER_FUNCTION), zend_uchar(ZEND_INTERNAL_FUNCTION)}) {
#ifdef SWOOLE_RS_PHPCOROUTINES
        swr_v1_phpcoroutines_scheduler_phase(&PHPCoroutine::activated, SWR_CORO_SCHED_PHASE_STOP);
#else
        PHPCoroutine::activated = false;
#endif
        zend_function function{kind};
        zend_fcall_info_cache cache{&function};
        zval argument{13}, callable{14};
        for (unsigned i = 0; i < 2; ++i) assert(PHPCoroutine::create(&cache, 1, &argument, &callable) == 102);
    }
    for (const auto &event : trace) std::cout << event << '\n';
#ifdef SWOOLE_RS_PHPCOROUTINES
    uint32_t phase = 0;
    assert(swr_v1_phpcoroutines_create(&phase, 10, 10, ZEND_USER_FUNCTION, ZEND_INTERNAL_FUNCTION) == SWR_CORO_CREATE_LIMIT);
    phase = 0;
    assert(swr_v1_phpcoroutines_create(&phase, 2, 10, ZEND_USER_FUNCTION, ZEND_INTERNAL_FUNCTION) == SWR_CORO_CREATE_HANDLER);
    assert(swr_v1_phpcoroutines_create(&phase, 0, 10, ZEND_USER_FUNCTION, ZEND_INTERNAL_FUNCTION) == SWR_CORO_CREATE_INVALID_CACHE);
    phase = 2;
    assert(swr_v1_phpcoroutines_create(&phase, 99, 10, ZEND_USER_FUNCTION, ZEND_INTERNAL_FUNCTION) == SWR_CORO_CREATE_INVALID_TYPE);
#endif
}
