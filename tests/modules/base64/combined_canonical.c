/* Canonical sequential consumer of the real combined Cargo FFI archive. */
#include "swoole_rs.h"
#include "swoole_rs_base64.h"
#include "swoole_rs_crc32.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static const char alphabet[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
static size_t encode_oracle(const uint8_t *input, size_t length, uint8_t *output) {
    uint32_t accumulator = 0;
    unsigned bits = 0;
    size_t written = 0;
    for (size_t i = 0; i < length; ++i) {
        accumulator = (accumulator << 8) | input[i];
        bits += 8;
        while (bits >= 6) {
            bits -= 6;
            output[written++] = (uint8_t) alphabet[(accumulator >> bits) & 63];
        }
    }
    if (bits) output[written++] = (uint8_t) alphabet[(accumulator << (6 - bits)) & 63];
    while (written % 4) output[written++] = '=';
    output[written] = 0;
    return written;
}
static uint32_t crc_oracle(const uint8_t *input, size_t length) {
    uint32_t crc = UINT32_MAX;
    for (size_t i = 0; i < length; ++i) {
        crc ^= input[i];
        for (unsigned bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ (UINT32_C(0xedb88320) * (crc & 1));
    }
    return ~crc;
}
static void canary(const uint8_t *buffer, size_t begin, size_t end) {
    for (size_t i = begin; i < end; ++i) assert(buffer[i] == 0xa5);
}
int main(void) {
    assert(swr_v1_abi_version() == 1);
    assert(swr_v1_feature_bits() == 24);
    uint8_t input[65536 + 16], coded[87417], decoded[87417], expected[87417];
    const size_t extra[] = {255, 256, 257, 1023, 1024, 1025, 4095, 4096, 4097, 65536};
    size_t cases = 0;
    for (size_t i = 0; i < sizeof(input); ++i) input[i] = (uint8_t) (i * 37 + 19);
    for (size_t index = 1; index <= 129 + sizeof(extra) / sizeof(extra[0]); ++index) {
        const size_t length = index <= 129 ? index : extra[index - 130];
        for (size_t offset = 0; offset < 16; ++offset) {
            const size_t count = encode_oracle(input + offset, length, expected);
            memset(coded, 0xa5, sizeof(coded));
            memset(decoded, 0xa5, sizeof(decoded));
            assert(swr_v1_base64_encode(input + offset, length, coded + offset) == count);
            assert(memcmp(coded + offset, expected, count + 1) == 0);
            canary(coded, 0, offset);
            canary(coded, offset + count + 1, sizeof(coded));
            assert(swr_v1_base64_decode(coded + offset, count, decoded + offset) == length);
            assert(memcmp(decoded + offset, input + offset, length) == 0);
            assert(decoded[offset + length] == 0);
            canary(decoded, 0, offset);
            canary(decoded, offset + length + 1, sizeof(decoded));
            assert(swr_v1_crc32(input + offset, length) == crc_oracle(input + offset, length));
            ++cases;
        }
    }
    printf("{\"passed\":true,\"canonical_cases\":%zu,\"abi_version\":1,\"feature_bits\":24,\"timed\":false}\n", cases);
    return 0;
}
