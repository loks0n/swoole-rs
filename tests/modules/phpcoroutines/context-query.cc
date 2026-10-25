// Exact ordinary PHP binding bodies with inert native contexts/object effects, never Zend/GC/Coroutine execution.
#include <cassert>
#include <cstdint>
#include <iostream>
#include <string>
#include <vector>
#include "swoole_rs_phpcoroutines.h"
using zend_long = long;
std::vector<std::string> trace;
struct zend_object { unsigned refs; } existing_object, initialized_object;
struct zval { zend_object *object; } output;
zval *return_value = &output;
struct PHPContext { zend_object *context; } context;
zend_long parsed_cid;
int class_entry;
int *swoole_coroutine_context_ce = &class_entry;
#define INVALID_PTR (-1)
#define SW_ERROR_CO_NOT_EXISTS 1
#define E_WARNING 1
#define EXPECTED(value) (value)
#define UNEXPECTED(value) (value)
#define PHP_METHOD(class_name, name) void name()
#define ZEND_PARSE_PARAMETERS_START(minimum, maximum)
#define Z_PARAM_OPTIONAL
#define Z_PARAM_LONG(value) value = parsed_cid;
#define ZEND_PARSE_PARAMETERS_END_EX(action)
#define Z_OBJ_P(value) ((value)->object)
#define RETURN_FALSE do { assert(false); return; } while (false)
#define RETURN_NULL() do { assert(false); return; } while (false)
#define RETURN_LONG(value) do { trace.push_back("long:" + std::to_string(value)); return; } while (false)
#define RETURN_OBJ(value) do { return_value->object = (value); trace.push_back("object:" + std::to_string((value)->refs)); return; } while (false)
#define GC_ADDREF(value) addref(value)
void addref(zend_object *value) {
    assert(value == &existing_object || value == &initialized_object);
    trace.push_back("addref"); ++value->refs;
}
void object_init_ex(zval *value, int *entry) {
    assert(entry == &class_entry); trace.push_back("init-object-stub"); value->object = &initialized_object;
}
void swoole_set_last_error(int) { assert(false); }
void php_swoole_fatal_error(int, const char *) { assert(false); }
namespace Coroutine {
void *get_current_task() { trace.push_back("current-task-stub"); return &context; }
void *get_task_by_cid(long cid) { trace.push_back("by-id-stub:" + std::to_string(cid)); return &context; }
}
namespace PHPCoroutine {
long get_pcid(long cid) { trace.push_back("parent-stub:" + std::to_string(cid)); return 9; }
ssize_t get_stack_usage(long cid) { trace.push_back("stack-stub:" + std::to_string(cid)); return 48; }
}
// ACTUAL_QUERY_BODIES
int main() {
    for (bool present : {false, true}) for (long cid : {0, 7, 8}) {
        parsed_cid = cid; existing_object.refs = 4; initialized_object.refs = 1;
        context.context = present ? &existing_object : nullptr; output.object = nullptr;
        getContext();
        assert(context.context == (present ? &existing_object : &initialized_object));
        assert(output.object == context.context && output.object->refs == (present ? 5u : 2u));
        getPcid(); getStackUsage();
    }
    for (const auto &event : trace) std::cout << event << '\n';
#ifdef SWOOLE_RS_PHPCOROUTINES
    // Stopped error/warning paths are copied scalar decisions only, never original/selected native execution.
    uint32_t stage = 0;
    assert(swr_v1_phpcoroutines_context_query(SWR_CORO_QUERY_CONTEXT, &stage, -1, 0) == SWR_CORO_QUERY_BY_ID);
    assert(swr_v1_phpcoroutines_context_query(SWR_CORO_QUERY_CONTEXT, &stage, -1, 0) == SWR_CORO_QUERY_MISSING);
    stage = 0;
    assert(swr_v1_phpcoroutines_context_query(SWR_CORO_QUERY_CONTEXT, &stage, 0, 0) == SWR_CORO_QUERY_CURRENT);
    assert(swr_v1_phpcoroutines_context_query(SWR_CORO_QUERY_CONTEXT, &stage, 0, 1) == SWR_CORO_QUERY_CHECK_DESTROYED);
    assert(swr_v1_phpcoroutines_context_query(SWR_CORO_QUERY_CONTEXT, &stage, 0, 1) == SWR_CORO_QUERY_DESTROYED);
    assert(swr_v1_phpcoroutines_context_query(SWR_CORO_QUERY_PARENT, nullptr, 0, 0) == SWR_CORO_QUERY_FALSE);
    assert(swr_v1_phpcoroutines_context_query(SWR_CORO_QUERY_STACK, nullptr, 0, -1) == SWR_CORO_QUERY_FALSE);
#endif
}
