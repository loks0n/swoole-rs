// Exact original/selected base.cc output bodies with the unchanged native RNG.
// A bounded isolated runtime gate, not a full Swoole/PHP or performance gate.
#include "swoole_rs_corebase.h"
#include <array>
#include <cassert>
#include <cerrno>
#include <climits>
#include <cstdint>
#include <cstring>
#include <fcntl.h>
#include <iostream>
#include <random>
#include <string>
#include <sys/types.h>
#include <sys/wait.h>
#include <thread>
#include <unistd.h>
#include <vector>

static unsigned warnings;
#define SW_ERR -1
#define swoole_sys_warning(...) (++warnings)
namespace original {
int swoole_rand(int, int);
#include "random-original.inc"
#include "random-native-rng.inc"
}
namespace selected {
int swoole_rand(int, int);
#include "random-selected.inc"
#include "random-native-rng.inc"
}
#undef swoole_sys_warning
struct Engine {
    int (*system)(int, int);
    int (*rng)(int, int);
    void (*buffer)(char *, size_t);
    void (*append)(std::string &, size_t);
};
static bool alphabet(char c) {
    return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9');
}
static void strings(Engine e) {
    for (size_t n : {size_t(0), size_t(1), size_t(62), size_t(1023), size_t(4096)}) {
        std::vector<char> out(n + 3, char(0xa5));
        e.buffer(out.data() + 1, n);
        assert(uint8_t(out[0]) == 0xa5 && uint8_t(out[n + 2]) == 0xa5 && out[n + 1] == 0);
        for (size_t i = 1; i <= n; ++i) assert(alphabet(out[i]));
        std::string value = "prefix:"; e.append(value, n);
        assert(value.size() == n + 7 && value.substr(0, 7) == "prefix:");
        for (size_t i = 7; i < value.size(); ++i) assert(alphabet(value[i]));
    }
}
static void exercise(Engine e) {
    // Fresh native thread-local random_device/mt19937/distribution initialization.
    std::vector<std::thread> workers;
    for (unsigned i = 0; i < 4; ++i) workers.emplace_back([e] { strings(e); });
    for (auto &thread : workers) thread.join();
    strings(e);
    for (auto range : {std::array<int, 2>{1, 2}, {-100, 100}, {INT_MIN, INT_MIN + 100}, {INT_MAX - 100, INT_MAX}}) {
        for (unsigned i = 0; i < 64; ++i) {
            int v = e.system(range[0], range[1]);
            assert(v >= range[0] && v <= range[1]);
        }
    }
    // Native TLS is already initialized. A fork copies the generator state;
    // each process must observe the same next output sequence independently.
    (void) e.rng(0, 61);
    int channel[2]; assert(pipe(channel) == 0);
    pid_t child = fork(); assert(child >= 0);
    std::array<char, 512> bytes{};
    if (child == 0) {
        close(channel[0]); e.buffer(bytes.data(), bytes.size() - 1);
        ssize_t n = write(channel[1], bytes.data(), bytes.size());
        close(channel[1]); _exit(n == ssize_t(bytes.size()) ? 0 : 7);
    }
    close(channel[1]); std::array<char, 512> received{}; size_t offset = 0;
    while (offset < received.size()) {
        ssize_t n = read(channel[0], received.data() + offset, received.size() - offset);
        if (n < 0 && errno == EINTR) continue;
        assert(n > 0); offset += size_t(n);
    }
    close(channel[0]); int status; assert(waitpid(child, &status, 0) == child);
    assert(WIFEXITED(status) && WEXITSTATUS(status) == 0);
    e.buffer(bytes.data(), bytes.size() - 1); assert(bytes == received);
}
int main() {
    exercise({original::swoole_system_random, original::swoole_rand,
              original::swoole_random_string, original::swoole_random_string});
    exercise({selected::swoole_system_random, selected::swoole_rand,
              selected::swoole_random_string, selected::swoole_random_string});
    assert(warnings == 0);
    std::cout << "actual native RNG/entropy bounded gate PASS both engines: fresh TLS, strings, ranges, fork inheritance\n";
}
