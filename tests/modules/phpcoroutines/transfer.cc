// Inert positive copied-structure controls. No Zend VM/output/allocator or callbacks execute.
#include <cassert>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>
#include "swoole_rs_phpcoroutines.h"
#define UNEXPECTED(v) (v)
std::vector<std::string> trace;
template<class T> T &observe(const char *name, T &value) { trace.push_back(name); return value; }
struct Buffer { uintptr_t data; size_t count; };
struct zend_output_globals { struct { int elements; } handlers; uintptr_t payload; };
struct Fields {
    uintptr_t bailout, vm_stack_top, vm_stack_end, vm_stack, vm_stack_page_size, current_execute_data;
    uintptr_t jit_trace_num, error_handling, exception_class, exception, stack_base, stack_limit;
    int error_reporting;
};
struct Basic { int serialize_lock; Buffer serialize, unserialize; };
static Fields eg;
static Basic bg;
static zend_output_globals og, stash;
#define EG(name) observe("eg:" #name, eg.name)
#define BG(name) observe("bg:" #name, bg.name)
#define OG(name) observe("og:" #name, og.name)
#define SWOG (&og)
void *emalloc(size_t size) { assert(size == sizeof(stash)); trace.push_back("copy-slot"); return &stash; }
void efree(void *value) { assert(value == &stash); trace.push_back("release-slot"); }
void php_output_activate() { trace.push_back("activate-output-model"); og = {}; }
struct PHPContext {
    uintptr_t bailout, vm_stack_top, vm_stack_end, vm_stack, vm_stack_page_size, execute_data;
    uintptr_t jit_trace_num, error_handling, exception_class, exception, stack_base, stack_limit;
#ifdef SWOOLE_RS_PHPCOROUTINES
    swr_phpcoroutines_scheduler_phase in_silence, enable_scheduler, fiber_init_notified;
    swr_phpcoroutines_error_cell ori_error_reporting, tmp_error_reporting;
    swr_phpcoroutines_parent_cell pcid;
    swr_phpcoroutines_clock_cell last_msec;
#else
    bool in_silence;
    int ori_error_reporting, tmp_error_reporting;
#endif
    zend_output_globals *output_ptr;
    int serialize_lock;
    Buffer serialize, unserialize;
};
// ACTUAL_METADATA_HELPER
#ifdef SWOOLE_RS_PHPCOROUTINES
#define PHASE(value) ((value).started)
#define SCALAR(item) ((item).value)
#else
#define PHASE(value) (value)
#define SCALAR(value) (value)
#endif
struct PHPCoroutine {
    static void save_vm_stack(PHPContext *ctx);
    static void restore_vm_stack(PHPContext *ctx);
    static void save_og(PHPContext *ctx);
    static void restore_og(PHPContext *ctx);
    static void save_bg(PHPContext *ctx);
    static void restore_bg(PHPContext *ctx);
    static void save_context(PHPContext *ctx);
    static void restore_context(PHPContext *ctx);
};
// ACTUAL_TRANSFER_BODIES
int main() {
    static PHPContext ctx;
    for (unsigned bits = 0; bits < 32; ++bits) {
        trace.clear();
        ctx = {};
        PHASE(ctx.in_silence) = bits & 1; SCALAR(ctx.ori_error_reporting) = 77;
        eg = {1,2,3,4,5,6,7,8,9,10,11,12,99};
        og = {{bits & 2 ? 3 : 0}, 123};
        bg = {bits & 4 ? 7 : 0, {bits & 8 ? 19u : 0u, 31}, {bits & 16 ? 23u : 0u, 37}};
        PHPCoroutine::save_context(&ctx);
        assert(ctx.bailout == 1 && ctx.execute_data == 6 && ctx.exception == 10);
#ifdef ZEND_CHECK_STACK_LIMIT
        assert(ctx.stack_base == 11 && ctx.stack_limit == 12);
#else
        assert(ctx.stack_base == 0 && ctx.stack_limit == 0);
#endif
        assert(SCALAR(ctx.tmp_error_reporting) == (PHASE(ctx.in_silence) ? 99 : 0));
        assert(eg.error_reporting == (PHASE(ctx.in_silence) ? 77 : 99));
        assert((ctx.output_ptr != nullptr) == bool(bits & 2));
        assert(ctx.serialize_lock == (bits & 4 ? 7 : 0));
        assert(ctx.serialize.data == (bits & 8 ? 19u : 0u));
        assert(ctx.unserialize.data == (bits & 16 ? 23u : 0u));
        eg = {}; bg = {}; og = {};
        PHPCoroutine::restore_context(&ctx);
        assert(eg.bailout == 1 && eg.current_execute_data == 6 && eg.exception == 10);
#ifdef ZEND_CHECK_STACK_LIMIT
        assert(eg.stack_base == 11 && eg.stack_limit == 12);
#else
        assert(eg.stack_base == 0 && eg.stack_limit == 0);
#endif
        assert(eg.error_reporting == (PHASE(ctx.in_silence) ? 99 : 0));
        assert(og.handlers.elements == (bits & 2 ? 3 : 0));
        assert(og.payload == (bits & 2 ? 123u : 0u));
        assert(!ctx.output_ptr && !ctx.serialize_lock && !ctx.serialize.data && !ctx.unserialize.data);
        assert(bg.serialize_lock == (bits & 4 ? 7 : 0));
        assert(bg.serialize.data == (bits & 8 ? 19u : 0u));
        assert(bg.unserialize.data == (bits & 16 ? 23u : 0u));
        std::cout << bits << ':' << eg.error_reporting << ':' << og.payload << ':'
                  << bg.serialize_lock << ':' << bg.serialize.data << ':' << bg.unserialize.data << '\n';
        for (const auto &effect : trace) std::cout << effect << '\n';
    }
}
