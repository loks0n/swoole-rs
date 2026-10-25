// Actual MIME get API; bound only native C++ allocations during each lookup.
#include "swoole_mime_type.h"
#include <algorithm>
#include <cstdlib>
#include <iostream>
#include <new>

static bool tracking;
static size_t largest, allocations, ceiling = 128;
void *operator new(size_t n) {
    if (tracking) { largest = std::max(largest, n); allocations++; if (ceiling && n > ceiling) throw std::bad_alloc(); }
    void *p = std::malloc(n ? n : 1); if (!p) throw std::bad_alloc(); return p;
}
void operator delete(void *p) noexcept { std::free(p); }
void operator delete(void *p, size_t) noexcept { std::free(p); }
int main(int argc, char **argv) {
    if (argc > 1) ceiling = std::stoull(argv[1]);
    bool passed = true;
    for (const auto &suffix: {std::string("TXT"), std::string(70, 'X'), std::string()}) {
        std::string filename(1024 * 1024, 'p'); filename += '.'; filename += suffix;
        allocations = largest = 0; bool threw = false; const std::string *value = nullptr;
        tracking = true;
        try { value = &swoole::mime_type::get(filename); }
        catch (const std::bad_alloc &) { threw = true; }
        tracking = false;
        bool matches = value && *value == (suffix == "TXT" ? "text/plain" : "application/octet-stream");
        passed = passed && !threw && matches;
        std::cout << "{\"suffix_bytes\":" << suffix.size() << ",\"filename_bytes\":" << filename.size()
                  << ",\"allocation_ceiling\":" << ceiling << ",\"largest_new\":" << largest << ",\"allocations\":" << allocations
                  << ",\"bad_alloc\":" << (threw ? "true" : "false")
                  << ",\"value_matches\":" << (matches ? "true" : "false") << "}\n";
    }
    return passed ? 0 : 1;
}
