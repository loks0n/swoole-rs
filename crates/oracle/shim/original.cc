#include "test_core.h"
#include "core-tests/src/protocol/base64.cpp"

extern "C" int swr_original_base64_failures() {
    original_base64_encode();
    original_base64_decode();
    return failures;
}
