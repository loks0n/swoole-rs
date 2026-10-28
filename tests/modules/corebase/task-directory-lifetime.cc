// SPDX-License-Identifier: Apache-2.0
// C++ new failure inside swoole_set_task_tmpdir (v6.2.4 builds the path as a std::string).
#include "swoole.h"
#include <cstdio>
#include <cstdlib>
#include <new>
#include <stdexcept>
#include <string>
#include <unistd.h>

static bool fail_new;
static unsigned new_calls;
void *operator new(std::size_t size) {
    if (fail_new) { ++new_calls; throw std::bad_alloc(); }
    if (void *result = std::malloc(size ? size : 1)) return result;
    throw std::bad_alloc();
}
void *operator new[](std::size_t size) { return ::operator new(size); }
void operator delete(void *ptr) noexcept { std::free(ptr); }
void operator delete[](void *ptr) noexcept { std::free(ptr); }
void operator delete(void *ptr, std::size_t) noexcept { std::free(ptr); }
void operator delete[](void *ptr, std::size_t) noexcept { std::free(ptr); }
static void require_at(bool condition, int line) {
    if (!condition) throw std::runtime_error("task-directory lifetime witness failed at line " + std::to_string(line));
}
#define require(condition) require_at((condition), __LINE__)
int main() {
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    char path[] = "/tmp/swr-corebase-task-life-XXXXXX";
    require(mkdtemp(path));
    const std::string dir(path), formatted = dir + "/" SW_TASK_TMP_FILE;
    swoole_init();
    FILE *sink = std::tmpfile(); require(sink); SwooleG.logger->set_stream(sink);

    SwooleG.task_tmpfile = "unchanged";
    bool caught = false; new_calls = 0; fail_new = true;
    try { swoole_set_task_tmpdir(dir); } catch (const std::bad_alloc &) { caught = true; }
    fail_new = false;
    require(caught);
    require(new_calls == 1);
    require(SwooleG.task_tmpfile == "unchanged");
    require(swoole_set_task_tmpdir(dir) && SwooleG.task_tmpfile == formatted);
    std::puts("string-copy-failure:old-global,recovered");

    // Two components, each under NAME_MAX, so mkdir succeeds and only the length rejects.
    const std::string half(SW_TASK_TMP_PATH_SIZE / 2, 'r'), long_dir = dir + "/" + half + "/" + half;
    require(!swoole_set_task_tmpdir(long_dir) && SwooleG.task_tmpfile == long_dir + "/" SW_TASK_TMP_FILE);
    std::puts("length-reject-after-publication");
    swoole_clean(); std::fclose(sink);
    require(rmdir(long_dir.c_str()) == 0 && rmdir((dir + "/" + half).c_str()) == 0 && rmdir(path) == 0);
}
