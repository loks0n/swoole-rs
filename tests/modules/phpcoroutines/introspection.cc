// Exact ordinary trace bodies with inert executor/getter/trace effects; no Zend VM trace or output.
#include <cassert>
#include <cstdint>
#include <iostream>
#include <string>
#include <vector>
#include "swoole_rs_phpcoroutines.h"
using zend_long = long;
struct zend_execute_data { int id; } original_executor{11}, target_executor{22};
zend_execute_data *current_executor = &original_executor;
#define EG(name) current_executor
struct PHPContext { zend_execute_data *execute_data; } context{&target_executor};
struct zval { bool value; } output;
zval *return_value = &output;
std::vector<std::string> trace;
zend_long parsed_cid;
#define PHP_METHOD(class_name, name) void name()
#define DEBUG_BACKTRACE_PROVIDE_OBJECT 1
#define ZEND_PARSE_PARAMETERS_START(minimum, maximum)
#define Z_PARAM_OPTIONAL
#define Z_PARAM_LONG(value) value = !std::string(#value).compare("cid") ? parsed_cid : 5;
#define ZEND_PARSE_PARAMETERS_END_EX(action)
#define RETURN_FALSE do { assert(false); return; } while (false)
#define RETVAL_FALSE do { assert(false); } while (false)
#define UNEXPECTED(value) (value)
#define SW_ERROR_CO_NOT_EXISTS 1
void swoole_set_last_error(int) { assert(false); }
namespace PHPCoroutine {
long get_cid() { trace.push_back("cid-stub"); return 7; }
PHPContext *get_context_by_cid(long cid) { trace.push_back("context-stub:" + std::to_string(cid)); return &context; }
}
void zend_fetch_debug_backtrace(zval *value, int skip, zend_long options, zend_long limit) {
    assert(value == &output && options == 5 && limit == 5);
    trace.push_back("fetch-stub:" + std::to_string(current_executor->id) + ":" + std::to_string(skip));
}
void sw_php_print_backtrace_impl(int skip, int options, int limit) {
    assert(options == 3 && limit == 4);
    trace.push_back("print-stub:" + std::to_string(current_executor->id) + ":" + std::to_string(skip));
}
// ACTUAL_TRACE_BODIES
int main() {
    for (long cid : {-1, 0, 7, 8}) {
        parsed_cid = cid; current_executor = &original_executor;
        getBackTrace(); assert(current_executor == &original_executor);
        for (bool present : {false, true}) {
            sw_php_print_backtrace(cid, 3, 4, present ? &output : nullptr);
            assert(current_executor == &original_executor);
        }
    }
    for (const auto &value : trace) std::cout << value << '\n';
#ifdef SWOOLE_RS_PHPCOROUTINES
    // Missing/false decisions are copied facts only. Never execute a native error branch.
    for (bool result : {false, true}) {
        uint32_t stage = 0;
        assert(swr_v1_phpcoroutines_trace(&stage, 8, 0, 1).action == SWR_CORO_TRACE_CID);
        assert(swr_v1_phpcoroutines_trace(&stage, 8, 7, 1).action == SWR_CORO_TRACE_CONTEXT);
        assert(swr_v1_phpcoroutines_trace(&stage, 8, 0, 1).action == SWR_CORO_TRACE_MISSING);
        assert(swr_v1_phpcoroutines_trace(&stage, 8, 0, 1).action == SWR_CORO_TRACE_RETURN_PRESENCE);
        assert(swr_v1_phpcoroutines_trace(&stage, 8, result, 1).action == (result ? SWR_CORO_TRACE_FALSE : SWR_CORO_TRACE_DONE));
    }
#endif
}
