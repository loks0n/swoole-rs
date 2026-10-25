// Exact production projector over inert Native handler/arginfo identity tokens.
// Never invokes a handler, Zend, alias, class registration or lifecycle operation.
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include "swoole_rs_phpcoroutines.h"
using zif_handler = void (*)();
struct zend_internal_arg_info { uint32_t token; };
struct zend_function_entry {
    const char *fname;
    zif_handler handler;
    const zend_internal_arg_info *arg_info;
    uint32_t num_args, flags;
};
#define ZEND_ACC_PUBLIC 0x400
#define ZEND_ACC_STATIC 0x80
#define ZEND_MN(name) zim_##name
#define ZEND_FN(name) zif_##name
#define ZEND_FENTRY(name, handler, info, flags) {#name, handler, info, static_cast<uint32_t>(sizeof(info) / sizeof(zend_internal_arg_info) - 1), flags},
#define PHP_ME(cls, name, info, flags) ZEND_FENTRY(name, ZEND_MN(cls##_##name), info, flags)
#define PHP_MALIAS(cls, name, alias, info, flags) ZEND_FENTRY(name, ZEND_MN(cls##_##alias), info, flags)
#define PHP_FE_END {nullptr, nullptr, nullptr, 0, 0}
// EXACT_TABLES_AND_PROJECTOR
int main() {
    zend_function_entry *actual[] = {swoole_coroutine_methods, swoole_exit_exception_methods,
        swoole_coroutine_scheduler_methods, swoole_coroutine_system_methods};
    const zend_function_entry *expected[] = {expected_swoole_coroutine_methods, expected_swoole_exit_exception_methods,
        expected_swoole_coroutine_scheduler_methods, expected_swoole_coroutine_system_methods};
    const PHPCoroutineMethodBinding *bindings[] = {swoole_coroutine_methods_bindings, swoole_exit_exception_methods_bindings,
        swoole_coroutine_scheduler_methods_bindings, swoole_coroutine_system_methods_bindings};
    unsigned rows = 0;
    for (uint32_t kind = 0; kind < 4; ++kind) {
        php_coroutine_project_methods(kind, bindings[kind], actual[kind]);
        auto *projection = actual[kind];
        const auto *reference = expected[kind];
        for (size_t i = 0;; ++i) {
            assert(projection[i].handler == reference[i].handler);
            assert(projection[i].arg_info == reference[i].arg_info);
            assert(projection[i].num_args == reference[i].num_args);
            assert(projection[i].flags == reference[i].flags);
            if (!reference[i].fname) { assert(!projection[i].fname); break; }
            assert(projection[i].fname && std::strcmp(projection[i].fname, reference[i].fname) == 0);
            ++rows;
        }
    }
#ifdef SW_CORO_TIME
    assert(rows == 57);
#else
    assert(rows == 56);
#endif
    assert(model_handler_observation == 0); // All addresses remain inert; no callback was invoked.
    std::printf("{\"rows\":%u,\"tables\":4,\"matched\":true}\n", rows);
}
