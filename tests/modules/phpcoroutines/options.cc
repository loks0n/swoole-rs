// Option-policy bodies with inert Zend value/lookup/setter/resolver recorders.
#include <cassert>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <map>
#include <string>
#include <vector>
#include "swoole_rs_phpcoroutines.h"
using zend_long = int64_t;
struct zend_array;
struct zval { int64_t value; bool null; bool array; zend_array *items; };
struct zend_array { std::map<std::string, zval> values; };
std::vector<std::string> trace;
#define SW_DEFAULT_MAX_CORO_NUM 100000
#define ZVAL_IS_NULL(value) ((value)->null)
#define ZVAL_IS_ARRAY(value) ((value)->array)
#define Z_ARR_P(value) ((value)->items)
#define ZEND_HASH_APPLY_KEEP 0
#define E_WARNING 1
zval *zend_hash_str_find(zend_array *table, const char *key, size_t length) {
    std::string name(key, length);
    trace.push_back("lookup:" + name);
    auto it = table->values.find(name);
    return it == table->values.end() ? nullptr : &it->second;
}
#define php_swoole_array_get_value(ht, key, value) ((value = zend_hash_str_find(ht, key, sizeof(key) - 1)) && !ZVAL_IS_NULL(value))
zend_long zval_get_long(zval *value) { trace.push_back("long:" + std::to_string(value->value)); return value->value; }
bool zval_is_true(zval *value) { trace.push_back("bool:" + std::to_string(value->value)); return value->value != 0; }
size_t php_swoole_parse_to_size(zval *value) { trace.push_back("size:" + std::to_string(value->value)); return size_t(value->value); }
void php_swoole_fatal_error(int, const char *) { assert(false); }
namespace PHPCoroutine {
zend_array *options = nullptr;
void set_max_num(zend_long value) { trace.push_back("max:" + std::to_string(value)); }
void set_deadlock_check(bool value) { trace.push_back("deadlock:" + std::to_string(value)); }
void set_hook_flags(zend_long value) { trace.push_back("hooks:" + std::to_string(value)); }
void enable_preemptive_scheduler(bool value) { trace.push_back("preemptive:" + std::to_string(value)); }
}
namespace Coroutine { void set_stack_size(size_t value) { trace.push_back("stack:" + std::to_string(value)); } }
void php_swoole_name_resolver_add(zval *value) { trace.push_back("resolver-stub:" + std::to_string(value->value)); }
void zend_hash_apply(zend_array *table, int (*fn)(zval *)) { for (auto &entry : table->values) assert(fn(&entry.second) == ZEND_HASH_APPLY_KEEP); }
void zval_add_ref(zval *) {}
void zend_hash_merge(zend_array *, zend_array *, void (*)(zval *), bool overwrite) { assert(overwrite); trace.push_back("merge-stub"); }
zend_array *zend_array_dup(zend_array *table) { trace.push_back("dup-stub"); return table; }
// ACTUAL_BODY
int main() {
    const char *keys[] = {"max_coro_num", "max_coroutine", "enable_deadlock_check", "hook_flags", "enable_preemptive_scheduler", "c_stack_size", "stack_size", "name_resolver"};
    for (unsigned presence = 0; presence < 256; ++presence) {
        for (unsigned variant = 0; variant < 4; ++variant) {
            zend_array input, resolver_items, previous;
            resolver_items.values.emplace("one", zval{91, false, false, nullptr});
            resolver_items.values.emplace("two", zval{92, false, false, nullptr});
            for (unsigned i = 0; i < 8; ++i) {
                if (presence & (1u << i)) input.values.emplace(keys[i], zval{
                    i == 0 ? (variant == 0 ? -1 : variant == 1 ? 0 : 100) : ((i == 2 || i == 4) && variant == 0 ? 0 : int64_t(200 + i)),
                    variant == 3 && (i == 0 || i == 5), i == 7, i == 7 ? &resolver_items : nullptr});
            }
            PHPCoroutine::options = variant & 1 ? &previous : nullptr;
            trace.clear();
            php_swoole_set_coroutine_option(&input);
            std::cout << presence << ':' << variant << '\n';
            for (const auto &event : trace) std::cout << event << '\n';
        }
    }
}
