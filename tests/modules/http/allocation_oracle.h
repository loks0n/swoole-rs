#pragma once
#include <cstdlib>
#include <new>
namespace allocation {
thread_local bool active = false;
thread_local size_t count = 0, fail = 0, sizes[128];
void begin(size_t nth) { count = 0; fail = nth; active = true; }
void end() { active = false; }
}
void *operator new(size_t size) {
    if (allocation::active) {
        size_t n = ++allocation::count;
        if (n <= 128) allocation::sizes[n - 1] = size;
        if (n == allocation::fail) throw std::bad_alloc();
    }
    if (void *p = std::malloc(size ? size : 1)) return p;
    throw std::bad_alloc();
}
void operator delete(void *p) noexcept { std::free(p); }
void *operator new[](size_t n) { return ::operator new(n); }
void operator delete[](void *p) noexcept { ::operator delete(p); }
void operator delete(void *p, size_t) noexcept { ::operator delete(p); }
void operator delete[](void *p, size_t) noexcept { ::operator delete(p); }
