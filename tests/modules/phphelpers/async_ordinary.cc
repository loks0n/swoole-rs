// Complete original/selected common helper, ordinary Native effect recorders.
// No PHP callback, DB/vendor, coroutine, yield, failure/reentry or lifetime runs.
#include "swoole_rs_phphelpers.h"
#include <cassert>
#include <functional>
#include <iostream>
#include <string>
#include <vector>
static std::vector<std::string> trace;
static bool context, dispatch_result;
static bool swoole_coroutine_is_in() { trace.push_back("context"); return context; }
namespace swoole { namespace coroutine {
static bool async(const std::function<void(void)> &) { trace.push_back("dispatch"); return dispatch_result; }
} }
namespace reference {
#include "async-reference.inc"
}
namespace candidate {
#include "async-selected.inc"
}
int main() {
    size_t cases = 0;
    for (bool blocking : {false, true}) for (bool active : {false, true}) for (bool result : {false, true}) {
        context = active;
        dispatch_result = result;
        std::function<void(void)> record = [] { trace.push_back("direct"); };
        trace.clear();
        bool expected = reference::php_swoole_async(blocking, record);
        const auto before = trace;
        trace.clear();
        bool actual = candidate::php_swoole_async(blocking, record);
        assert(actual == expected && trace == before);
        if (blocking) assert((trace == std::vector<std::string>{"direct"}));
        else if (active) assert((trace == std::vector<std::string>{"context", "dispatch"}));
        else assert((trace == std::vector<std::string>{"context", "direct"}));
        assert(actual == (blocking || !active || result));
        ++cases;
    }
    std::cout << "{\"ordinary_dispatch_cases\":" << cases << ",\"native_runtime_executed\":false}\n";
}
