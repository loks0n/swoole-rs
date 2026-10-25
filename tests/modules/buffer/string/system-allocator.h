#pragma once
#include <cstddef>
struct AllocationEvent { char operation; size_t size; bool failed; bool moved; };
struct AllocationTrace { AllocationEvent events[128]; size_t count; size_t live; };
extern "C" void swr_test_allocator_begin(long fail_after);
extern "C" AllocationTrace swr_test_allocator_end();
extern "C" bool swr_test_allocator_live(const void *pointer);
