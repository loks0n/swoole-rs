// Stand-in for upstream core-tests/include/test_core.h: just enough of GoogleTest
// to run unmodified original assertions and count their failures.
#pragma once
#include <cstddef>
#include <cstring>
#include <string>

using uchar = unsigned char;
static int failures = 0;

#define TEST(suite, name) static void original_##suite##_##name()
#define ASSERT_GT(a, b) do { if (!((a) > (b))) ++failures; } while (0)
#define ASSERT_EQ(a, b) do { if (!((a) == (b))) ++failures; } while (0)

// Deterministic replacement for the random-byte fixture.
inline size_t swoole_random_bytes(char *out, size_t n) {
    for (size_t i = 0; i < n; ++i) out[i] = static_cast<char>(i * 37 + 19);
    return n;
}
