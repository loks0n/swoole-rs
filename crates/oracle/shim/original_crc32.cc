#include "test_core.h"
#include "swoole_hash.h"
#include "crc32_test.cpp"

extern "C" int swr_original_crc32_failures() {
    original_hash_crc32();
    return failures;
}
