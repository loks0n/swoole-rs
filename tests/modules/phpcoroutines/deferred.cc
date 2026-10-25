// Inert ordinary defer registration and LIFO custody, never Zend callback execution.
#include <cassert>
#include <cstdint>
#include <iostream>
#include <new>
#include <stack>
#include "swoole_rs_phpcoroutines.h"
namespace zend { struct Function { unsigned id; }; }
namespace swoole {}
// SELECTED_OWNER
struct PHPContext {
#ifdef SWOOLE_RS_PHPCOROUTINES
    swoole::PHPCoroutineDeferredTasks *defer_tasks = nullptr;
#else
    std::stack<zend::Function *> *defer_tasks = nullptr;
#endif
} context;
namespace PHPCoroutine {
PHPContext *get_context() { return &context; }
void defer(zend::Function *);
}
using namespace swoole;
// ACTUAL_BODY
bool take(zend::Function **result) {
#ifdef SWOOLE_RS_PHPCOROUTINES
    return context.defer_tasks->pop(result);
#else
    if (context.defer_tasks->empty()) return false;
    *result = context.defer_tasks->top();
    context.defer_tasks->pop();
    return true;
#endif
}
int main() {
    zend::Function functions[4096];
    for (unsigned i = 0; i < 4096; ++i) {
        functions[i].id = i;
        PHPCoroutine::defer(&functions[i]);
    }
    zend::Function *function = nullptr;
    for (unsigned remaining = 4096; remaining > 0; --remaining) {
        assert(take(&function) && function == &functions[remaining - 1]);
        std::cout << function->id << '\n';
        if (remaining == 4096) {
            // Separate metadata insertion after pop, no callback or coroutine.
            PHPCoroutine::defer(&functions[0]);
            PHPCoroutine::defer(&functions[1]);
            assert(take(&function) && function == &functions[1]);
            assert(take(&function) && function == &functions[0]);
        }
    }
    function = &functions[2];
    assert(!take(&function) && function == &functions[2]);
    delete context.defer_tasks;
    context.defer_tasks = nullptr;
}
