// Controlled effects through exact extracted pinned/patched base.cc bodies.
// This is not a whole Swoole/Logger/std-RNG integration or sanitizer gate.
#include "swoole_rs_corebase.h"
#include <cassert>
#include <cerrno>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <fcntl.h>
#include <iostream>
#include <new>
#include <stdexcept>
#include <string>
#include <sys/types.h>
#include <vector>

static bool fail_allocation = false;
void *operator new(std::size_t size) {
    if (fail_allocation) { fail_allocation = false; throw std::bad_alloc(); }
    if (void *p = std::malloc(size ? size : 1)) return p;
    throw std::bad_alloc();
}
void operator delete(void *p) noexcept { std::free(p); }
void operator delete(void *p, std::size_t) noexcept { std::free(p); }

struct Read { ssize_t count; unsigned word; int error; };
struct Context {
    std::vector<std::string> events;
    std::deque<int> opens, draws;
    std::deque<Read> reads;
    bool throw_rng = false, throw_warning = false, fail_append = false;
    int draws_until_exception = -1, draws_until_append_failure = -1;
};
static Context *active;
static int controlled_open(const char *path, int flags) {
    assert(std::string(path) == "/dev/urandom" && flags == O_RDONLY);
    active->events.emplace_back("open");
    assert(!active->opens.empty()); int fd = active->opens.front(); active->opens.pop_front(); return fd;
}
static ssize_t controlled_read(int fd, void *buffer, size_t size) {
    assert(fd == 42 && size == sizeof(unsigned));
    active->events.emplace_back("read");
    assert(!active->reads.empty()); auto row = active->reads.front(); active->reads.pop_front();
    if (row.count > 0) std::memcpy(buffer, &row.word, size_t(row.count));
    errno = row.error; return row.count;
}
static int controlled_draw(int min, int max) {
    active->events.push_back("draw:" + std::to_string(min) + ":" + std::to_string(max));
    if (active->throw_rng || active->draws_until_exception == 0) throw std::runtime_error("controlled RNG initialization exception");
    assert(!active->draws.empty()); int draw = active->draws.front(); active->draws.pop_front();
    assert(draw >= min && draw <= max);
    if (active->draws_until_exception > 0) --active->draws_until_exception;
    if (active->fail_append || active->draws_until_append_failure == 0) fail_allocation = true;
    else if (active->draws_until_append_failure > 0) --active->draws_until_append_failure;
    return draw;
}
static void controlled_warning(const char *function) {
    active->events.push_back(std::string("warning:") + function + ":" + std::to_string(errno));
    if (active->throw_warning) throw std::runtime_error("controlled warning exception");
}
#define SW_ERR -1
#define open controlled_open
#define read controlled_read
#define swoole_rand controlled_draw
#define swoole_sys_warning(...) controlled_warning(__func__)
namespace original {
#include "random-original.inc"
}
namespace selected {
#include "random-selected.inc"
}
#undef open
#undef read
#undef swoole_rand
#undef swoole_sys_warning

struct Engine {
    int (*system)(int, int);
    void (*buffer)(char *, size_t);
    void (*append)(std::string &, size_t);
};
static std::vector<std::string> exercise(Engine engine) {
    Context c; active = &c;
    c.opens = {-1, -1, 42}; c.draws = {5};
    c.throw_rng = true;
    try { engine.system(4, 9); assert(false); } catch (const std::runtime_error &) {}
    c.throw_rng = false;
    assert(engine.system(4, 9) == 5);
    c.reads = {{-1, 0, EINTR}, {2, 1234, EDOM}, {4, UINT32_MAX, 0}};
    assert(engine.system(4, 9) == -1);
    assert(engine.system(4, 9) == -1);
    assert(engine.system(-100, 100) == int(-100 + int64_t(UINT32_MAX) % 201));
    c.throw_warning = true; c.reads = {{-1, 0, EPERM}};
    try { engine.system(4, 9); assert(false); } catch (const std::runtime_error &) {}
    c.throw_warning = false; c.reads = {{4, 0, 0}};
    assert(engine.system(4, 9) == 4); // same cached fd after warning exception
    const std::vector<std::string> expected = {
        "open", "draw:4:9", "open", "draw:4:9", "open", "read",
        "warning:swoole_system_random:" + std::to_string(EINTR), "read",
        "warning:swoole_system_random:" + std::to_string(EDOM), "read", "read",
        "warning:swoole_system_random:" + std::to_string(EPERM), "read"};
    assert(c.events == expected && c.opens.empty() && c.draws.empty() && c.reads.empty());
    auto all = c.events;
    for (size_t len : {size_t(0), size_t(6)}) {
        c.events.clear(); c.draws = {0, 25, 26, 51, 52, 61};
        char out[9]; std::memset(out, 0xa5, sizeof(out));
        engine.buffer(out + 1, len);
        assert(uint8_t(out[0]) == 0xa5 && uint8_t(out[len + 2]) == 0xa5 && out[len + 1] == 0);
        assert(std::string(out + 1) == (len ? "AZaz09" : ""));
        assert(c.events.size() == len);
        all.insert(all.end(), c.events.begin(), c.events.end());
        c.events.clear(); c.draws = {0, 25, 26, 51, 52, 61};
        std::string text = "prefix:"; engine.append(text, len);
        assert(text == (len ? "prefix:AZaz09" : "prefix:") && c.events.size() == len);
        all.insert(all.end(), c.events.begin(), c.events.end());
    }
    // A later draw fails after three successful stores, not before them.
    c.events.clear(); c.draws = {0, 25, 26}; c.draws_until_exception = 3;
    char partial[9]; std::memset(partial, 0xa5, sizeof(partial));
    try { engine.buffer(partial + 1, 6); assert(false); } catch (const std::runtime_error &) {}
    assert(std::memcmp(partial + 1, "AZa", 3) == 0);
    for (size_t i : {size_t(0), size_t(4), size_t(5), size_t(6), size_t(7), size_t(8)})
        assert(uint8_t(partial[i]) == 0xa5); // no premature NUL or later store
    assert(c.events == std::vector<std::string>(4, "draw:0:61") && c.draws.empty());
    all.insert(all.end(), c.events.begin(), c.events.end());
    c.events.clear(); c.draws = {0, 25, 26}; c.draws_until_exception = 3;
    std::string prefix = "prefix:";
    try { engine.append(prefix, 6); assert(false); } catch (const std::runtime_error &) {}
    assert(prefix == "prefix:AZa");
    assert(c.events == std::vector<std::string>(4, "draw:0:61") && c.draws.empty());
    all.insert(all.end(), c.events.begin(), c.events.end());
    c.draws_until_exception = -1;
    c.events.clear(); c.draws = {0}; c.fail_append = true;
    std::string text(200, 'p'); text.resize(text.capacity(), 'p'); const std::string before(text);
    try { engine.append(text, 20); assert(false); } catch (const std::bad_alloc &) {}
    c.fail_append = false;
    assert(!fail_allocation && text == before && c.draws.empty());
    assert(c.events == std::vector<std::string>{"draw:0:61"});
    all.insert(all.end(), c.events.begin(), c.events.end());
    c.events.clear(); c.draws = {0, 25, 26, 51}; c.draws_until_append_failure = 2;
    std::string later(200, 'p'); later.resize(later.capacity() - 2, 'p');
    const std::string expected_prefix = later + "AZ";
    try { engine.append(later, 20); assert(false); } catch (const std::bad_alloc &) {}
    c.draws_until_append_failure = -1;
    assert(!fail_allocation && later == expected_prefix);
    assert(c.events == std::vector<std::string>(3, "draw:0:61"));
    assert(c.draws == std::deque<int>{51}); // no fourth draw after third append fails
    all.insert(all.end(), c.events.begin(), c.events.end());
    return all;
}
int main() {
    auto native = exercise({original::swoole_system_random, original::swoole_random_string, original::swoole_random_string});
    auto rust = exercise({selected::swoole_system_random, selected::swoole_random_string, selected::swoole_random_string});
    assert(native == rust);
    std::cout << "controlled exact-body random effects PASS " << native.size() << " events per engine\n";
}
