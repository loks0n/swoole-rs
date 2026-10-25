// Entire Scheduler::set body, inert argument/value/cache/reactor effects only.
#include <cassert>
#include <cstdint>
#include <ctime>
#include <iostream>
#include <map>
#include <string>
#include <vector>
#include "swoole_rs_phpcoroutines.h"
using zend_long = int64_t;
struct zval;
using HashTable = std::map<std::string, zval>;
struct zval { int64_t value; bool null; HashTable *items; };
struct Reactor;
using ExitCondition = bool (*)(Reactor *, size_t &);
struct { ExitCondition user_exit_condition; } SwooleG;
std::vector<std::string> trace;
bool php_swoole_coroutine_reactor_can_exit(Reactor *, size_t &) { assert(false); return false; }
bool old_exit(Reactor *, size_t &) { assert(false); return false; }
namespace zend { struct Callable {}; }
zend::Callable previous, created;
#ifdef SWOOLE_RS_PHPCOROUTINES
swr_phpcoroutines_scheduler_callback_owner exit_condition_fci_cache{0};
#else
zend::Callable *exit_condition_fci_cache;
#endif
void sw_callable_free(zend::Callable *callable) { assert(callable == &previous); trace.push_back("free-stub"); }
zend::Callable *sw_callable_create(zval *value) { assert(value && !value->null); trace.push_back("create-stub"); return &created; }
struct Reactor {
    enum { EXIT_CONDITION_USER_AFTER_DEFAULT = 9 };
    void set_exit_condition(int code, ExitCondition fn) { assert(code == 9 && fn == php_swoole_coroutine_reactor_can_exit); trace.push_back("install-stub"); }
    void remove_exit_condition(int) { assert(false); }
} reactor;
bool reactor_present;
Reactor *sw_reactor() {
    trace.push_back(std::string("reactor:") + (SwooleG.user_exit_condition == php_swoole_coroutine_reactor_can_exit ? "new" : "old"));
    return reactor_present ? &reactor : nullptr;
}
zval *zend_hash_str_find(HashTable *input, const char *key, size_t length) {
    std::string name(key, length); trace.push_back("lookup:" + name);
    auto found = input->find(name); return found == input->end() ? nullptr : &found->second;
}
#define php_swoole_array_get_value(input, key, value) ((value = zend_hash_str_find(input, key, sizeof(key)-1)) && !value->null)
#define ZVAL_IS_NULL(value) ((value)->null)
#define ZEND_STRL(s) s, sizeof(s)-1
#define Z_ARRVAL_P(value) ((value)->items)
#define PHP_METHOD(a, b) void configure(zval *input)
#define ZEND_PARSE_PARAMETERS_START(a, b)
#define Z_PARAM_ARRAY(value) value = input;
#define ZEND_PARSE_PARAMETERS_END_EX(...)
zend_long zval_get_long(zval *value) { trace.push_back("long:" + std::to_string(value->value)); return value->value; }
void php_swoole_set_global_option(HashTable *) { trace.push_back("global-stub"); }
void php_swoole_set_coroutine_option(HashTable *) { trace.push_back("coroutine-stub"); }
namespace System {
void set_dns_cache_expire(time_t value) { trace.push_back("expire:" + std::to_string(value)); }
void set_dns_cache_capacity(size_t value) { trace.push_back("capacity:" + std::to_string(value)); }
}
// ACTUAL_BODY
int main() {
    for (unsigned presence = 0; presence < 8; ++presence) {
        for (unsigned variant = 0; variant < 8; ++variant) {
            HashTable fields;
            if (presence & 1) fields.emplace("dns_cache_expire", zval{-3, bool(variant & 1), nullptr});
            if (presence & 2) fields.emplace("dns_cache_capacity", zval{-1, bool(variant & 1), nullptr});
            if (presence & 4) fields.emplace("exit_condition", zval{42, false, nullptr});
            zval input{0, false, &fields};
#ifdef SWOOLE_RS_PHPCOROUTINES
            exit_condition_fci_cache.identity = variant & 2 ? reinterpret_cast<uintptr_t>(&previous) : 0;
#else
            exit_condition_fci_cache = variant & 2 ? &previous : nullptr;
#endif
            reactor_present = variant & 4;
            SwooleG.user_exit_condition = old_exit;
            trace.clear();
            configure(&input);
            std::cout << presence << ':' << variant << '\n';
            for (const auto &entry : trace) std::cout << entry << '\n';
            std::cout << "published:" << (SwooleG.user_exit_condition == php_swoole_coroutine_reactor_can_exit) << '\n';
        }
    }
}
