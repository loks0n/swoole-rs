// Process-local test interposition. No callback, container, I/O or allocation in tracing.
#include "system-allocator.h"
#include <algorithm>
#include <cerrno>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <unistd.h>
#ifdef __APPLE__
#include <malloc/malloc.h>
static void *real_malloc(size_t n) { return malloc_zone_malloc(malloc_default_zone(), n); }
static void *real_calloc(size_t n, size_t s) { return malloc_zone_calloc(malloc_default_zone(), n, s); }
static void *real_realloc(void *p, size_t n) { return malloc_zone_realloc(malloc_default_zone(), p, n); }
static void real_free(void *p) { if (p) malloc_zone_free(malloc_zone_from_ptr(p), p); }
#else
// Supported Linux lane is glibc. Its backend symbols avoid recursive dlsym allocation.
extern "C" void *__libc_malloc(size_t);
extern "C" void *__libc_calloc(size_t, size_t);
extern "C" void *__libc_realloc(void *, size_t);
extern "C" void __libc_free(void *);
static auto real_malloc = __libc_malloc;
static auto real_calloc = __libc_calloc;
static auto real_realloc = __libc_realloc;
static auto real_free = __libc_free;
#endif
namespace {
struct Owner { void *pointer; size_t size; };
thread_local bool active;
thread_local long remaining;
thread_local AllocationTrace trace;
thread_local Owner owners[64];
Owner *find(const void *p) { for (auto &owner : owners) if (p && owner.pointer == p) return &owner; return nullptr; }
void remember(void *p, size_t n) {
    if (!p) return;
    for (auto &owner : owners) if (!owner.pointer) { owner = {p, n}; ++trace.live; return; }
    _exit(91);
}
void forget(Owner *owner) { if (owner) { *owner = {}; --trace.live; } }
bool failure() {
    if (remaining < 0) return false;
    if (remaining-- != 0) return false;
    errno = ENOMEM; return true; // Fail once; exception allocation can then proceed.
}
void event(char op, size_t n, bool failed, bool moved = false) {
    if (trace.count == 128) _exit(92);
    trace.events[trace.count++] = {op, n, failed, moved};
}
}
extern "C" void swr_test_allocator_begin(long fail_after) {
    if (active) _exit(93);
    trace = {}; for (auto &owner : owners) owner = {};
    remaining = fail_after; active = true;
}
extern "C" AllocationTrace swr_test_allocator_end() { active = false; return trace; }
extern "C" bool swr_test_allocator_live(const void *p) { return find(p) != nullptr; }
extern "C" void *swr_test_malloc(size_t n) {
    if (!active) return real_malloc(n);
    bool failed = failure(); void *p = failed ? nullptr : real_malloc(n);
    event('m', n, !p); remember(p, n); return p;
}
extern "C" void *swr_test_calloc(size_t n, size_t s) {
    if (!active) return real_calloc(n, s);
    bool overflow = s && n > SIZE_MAX / s;
    bool failed = failure(); void *p = failed ? nullptr : real_calloc(n, s);
    event('c', overflow ? SIZE_MAX : n * s, !p); remember(p, overflow ? 0 : n * s); return p;
}
extern "C" void *swr_test_realloc(void *p, size_t n) {
    if (!active) return real_realloc(p, n);
    if (failure()) { event('r', n, true); return nullptr; }
    Owner *old = find(p); void *q;
    if (old && n) {
        // Moving realloc is conforming: old storage remains live until allocation succeeds.
        q = real_malloc(n);
        if (q) { std::memcpy(q, p, std::min(old->size, n)); real_free(p); forget(old); }
    } else {
        q = real_realloc(p, n);
        // Host realloc(p,0) semantics are intentionally observed, not emulated.
#ifdef __APPLE__
        if (q) forget(old);
#else
        if (q || (p && n == 0)) forget(old);
#endif
    }
    event('r', n, !q, p && q && p != q); if (q) remember(q, n); return q;
}
extern "C" void swr_test_free(void *p) {
    if (active) { event('f', 0, false); forget(find(p)); }
    real_free(p);
}
#ifdef __APPLE__
#define INTERPOSE(replacement, original) \
    __attribute__((used)) static const struct { const void *replace; const void *with; } \
    interpose_##original __attribute__((section("__DATA,__interpose"))) = \
        {reinterpret_cast<const void *>(&replacement), reinterpret_cast<const void *>(&original)};
INTERPOSE(swr_test_malloc, malloc)
INTERPOSE(swr_test_calloc, calloc)
INTERPOSE(swr_test_realloc, realloc)
INTERPOSE(swr_test_free, free)
#else
extern "C" void *malloc(size_t n) noexcept { return swr_test_malloc(n); }
extern "C" void *calloc(size_t n, size_t s) noexcept { return swr_test_calloc(n, s); }
extern "C" void *realloc(void *p, size_t n) noexcept { return swr_test_realloc(p, n); }
extern "C" void free(void *p) noexcept { swr_test_free(p); }
#endif
