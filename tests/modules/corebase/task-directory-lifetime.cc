// SPDX-License-Identifier: Apache-2.0
// Defined native allocator callbacks, fresh TLS lookup and C++new prefixes.
#include "swoole.h"
#include "swoole_string.h"
#include <cstdio>
#include <cstdlib>
#include <new>
#include <stdexcept>
#include <string>
#include <unistd.h>

static bool fail_new, fail_reserve, swap_buffer;
static unsigned new_calls, reserve_calls;
static swoole::String *replacement;
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
static void require(bool condition) {
    if (!condition) throw std::runtime_error("task-directory lifetime witness failed");
}
static void *resize(void *ptr, size_t size) {
    ++reserve_calls;
    if (fail_reserve) return nullptr;
    void *result = std::realloc(ptr, size);
    if (swap_buffer) SwooleTG.buffer_stack = replacement;
    return result;
}
int main() {
    char path[] = "/tmp/swr-corebase-task-life-XXXXXX";
    require(mkdtemp(path));
    const std::string dir(path), formatted = dir + "/" SW_TASK_TMP_FILE;
    swoole_init();
    FILE *sink = std::tmpfile(); require(sink); SwooleG.logger->set_stream(sink);
    auto *original = SwooleTG.buffer_stack;
    const swoole::Allocator allocator{std::malloc, std::calloc, resize, std::free};
    auto *first = new swoole::String(16, &allocator);
    first->append("old", 3);
    char *old_bytes = first->str; size_t old_capacity = first->size;
    SwooleTG.buffer_stack = first; SwooleG.task_tmpfile = "unchanged";
    bool caught = false;
    reserve_calls = 0; fail_reserve = true;
    try { swoole_set_task_tmpdir(dir); } catch (const std::bad_alloc &) { caught = true; }
    fail_reserve = false;
    require(caught && reserve_calls == 1 && first->str == old_bytes && first->size == old_capacity
            && first->to_std_string() == "old" && SwooleG.task_tmpfile == "unchanged");
    SwooleTG.buffer_stack = original; delete first;
    std::puts("reserve-failure:one-real-realloc,buffer-and-global-unchanged");

    first = new swoole::String(512);
    SwooleTG.buffer_stack = first; SwooleG.task_tmpfile = "unchanged";
    caught = false; new_calls = 0; fail_new = true;
    try { swoole_set_task_tmpdir(dir); } catch (const std::bad_alloc &) { caught = true; }
    fail_new = false;
    require(caught && new_calls == 1 && first->to_std_string() == formatted
            && SwooleG.task_tmpfile == "unchanged");
    require(swoole_set_task_tmpdir(dir) && SwooleG.task_tmpfile == formatted);
    SwooleTG.buffer_stack = original; delete first;
    std::puts("string-copy-failure:formatted-buffer,old-global,recovered");

    first = new swoole::String(16, &allocator);
    const std::string alternate(SW_TASK_TMP_PATH_SIZE, 'r');
    replacement = new swoole::String(alternate);
    SwooleTG.buffer_stack = first; SwooleG.task_tmpfile = "unchanged";
    reserve_calls = 0; swap_buffer = true;
    bool result = swoole_set_task_tmpdir(dir);
    swap_buffer = false;
    require(!result && reserve_calls == 1 && SwooleTG.buffer_stack == replacement
            && first->to_std_string() == formatted && replacement->to_std_string() == alternate
            && SwooleG.task_tmpfile == alternate);
    SwooleTG.buffer_stack = original; delete first; delete replacement; replacement = nullptr;
    std::puts("allocator-publishes-second-buffer:fresh-lookup,length-reject-after-publication");
    swoole_clean(); std::fclose(sink); require(rmdir(path) == 0);
}
