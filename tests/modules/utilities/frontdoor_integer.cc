// Exact defined Native usual integer comparison, no Logger/IO/failure effects.
#include <cassert>
#include <cstdint>
#include <climits>
#include <initializer_list>
#include <cstdio>
static unsigned checks;
enum SmallLevel { small_zero = 0, small_five = 5 };
enum WideLevel : uint64_t { wide_zero = 0, wide_five = 5, wide_max = UINT64_MAX };
#include "swoole_rs_utilities.h"
template<class T> static void compare(std::initializer_list<T> levels) {
    for (auto level : levels) {
        for (int threshold : {INT_MIN, -1, 0, 1, 5, 6, INT_MAX}) {
            SwrLogFrontdoor state = {};
            assert(swr_v2_utils_log_frontdoor_step(&state, 7, 0, 0, 0, 0).action == 1);
            assert(swr_v2_utils_log_frontdoor_step(&state, 7, 0, 0, 0, 0).action == 2);
            auto facts = swoole_rs_utilities::log_level_facts(level, threshold);
            auto next = swr_v2_utils_log_frontdoor_step(&state, 7, facts.first, facts.second, facts.unsigned_width, facts.high);
            // Keep the actual original expression, including usual promotions.
            assert((next.action == 4) == (level >= threshold));
            ++checks;
        }
    }
}
int main() {
    compare<int8_t>({INT8_MIN, -1, 0, 1, 5, INT8_MAX});
    compare<uint8_t>({0, 1, 5, UINT8_MAX});
    compare<int16_t>({INT16_MIN, -1, 0, 1, 5, INT16_MAX});
    compare<uint16_t>({0, 1, 5, UINT16_MAX});
    compare<int32_t>({INT32_MIN, -1, 0, 1, 5, INT32_MAX});
    compare<uint32_t>({0, 1, 5, UINT32_MAX});
    compare<int64_t>({INT64_MIN, -1, 0, 1, 5, INT64_MAX});
    compare<uint64_t>({0, 1, 5, UINT64_C(1) << 63, UINT64_MAX});
#ifdef __SIZEOF_INT128__
    const unsigned __int128 umax = ~static_cast<unsigned __int128>(0);
    const __int128 smax = static_cast<__int128>(umax >> 1);
    const __int128 large = __int128(1) << 100;
    compare<__int128>({-smax - 1, -1, 0, 1, 5, smax, large, -large});
    compare<unsigned __int128>({0, 1, 5, static_cast<unsigned __int128>(large), umax});
#endif
    compare<SmallLevel>({small_zero, small_five});
    compare<WideLevel>({wide_zero, wide_five, wide_max});
    std::printf("%u\n", checks);

}
