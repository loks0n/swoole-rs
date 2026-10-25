#include "rng_bodies.h"
#include <array>
#include <iostream>
#include <stdexcept>

static void check(bool value, const char *message) {
    if (!value) throw std::runtime_error(message);
}
#define RUN_RNG_CASE(ns, mode) \
    ns::seed = seed; ns::position = 0; ns::draws.clear(); \
    std::string mode = "SwooleBoundary"; \
    ns::swoole_random_string(mode, size_t(24)); \
    check(ns::position == 24, "positive append draw count"); \
    const auto mode##_draws = ns::draws; \
    ns::seed = seed; ns::position = 0; ns::draws.clear(); \
    std::array<char,39> mode##_buffer; mode##_buffer.fill(char(0xa5)); \
    ns::swoole_random_string(mode##_buffer.data(), size_t(24)); \
    check(ns::position == 24 && ns::draws == mode##_draws, "positive buffer draw sequence"); \
    check(mode##_buffer[24] == 0, "positive buffer terminator"); \
    for (size_t i=25;i<mode##_buffer.size();++i) check(static_cast<unsigned char>(mode##_buffer[i]) == 0xa5, "untouched scratch suffix"); \
    check(mode == std::string("SwooleBoundary") + std::string(mode##_buffer.data(),24), "append/buffer boundary byte equivalence")

int main() try {
    for (size_t seed=0;seed<62;++seed) {
        RUN_RNG_CASE(original, expected);
        RUN_RNG_CASE(selected, actual);
        check(expected == actual && expected_draws == actual_draws, "pinned/production Rust planner result and draws");
        check(expected.size()==38, "normal multipart boundary size");
        for (const auto &draw: expected_draws) check(draw.first==0 && draw.second==61, "frozen RNG bounds");
    }
    std::cout << "{\"positive_streams\":62,\"overload_runs_per_stream\":4,\"random_length\":24,\"errors\":0}\n";
    return 0;
} catch(const std::exception &error) { std::cerr<<error.what()<<'\n';return 1; }
