// SPDX-License-Identifier: Apache-2.0
// Linux executable syscall witnesses. Effects publish a real native logger
// during host discovery, after Global reset; no fixed files/ports or real limits
// are changed. This is bounded interposition, not general syscall failure proof.
#include "swoole.h"
#include "swoole_api.h"
#include <cerrno>
#include <cstdio>
#include <cstdint>
#include <dlfcn.h>
#include <stdexcept>
#include <string>
#include <sys/resource.h>
#include <unistd.h>

static bool active, fail_cpu, fail_limit, facts_ok;
static unsigned cpu_queries, limit_queries;
static rlim_t current_limit;
static FILE *sink;
static swoole::Logger *published;
static void require(bool condition) {
    if (!condition) throw std::runtime_error("init host-effects witness failed");
}
extern "C" long sysconf(int name) noexcept {
    if (active && name == _SC_NPROCESSORS_ONLN) {
        ++cpu_queries;
        if (cpu_queries == 1) {
            facts_ok = facts_ok && SwooleG.init && SwooleG.running && SwooleG.enable_coroutine
                && SwooleG.std_allocator.malloc && SwooleG.stdout_ == stdout && SwooleG.fatal_error
                && !SwooleG.logger && !SwooleTG.buffer_stack && sw_error[0] == '\0';
            published = new swoole::Logger();
            published->set_stream(sink);
            SwooleG.logger = published;
        } else {
            facts_ok = facts_ok && cpu_queries == 2 && SwooleG.logger == published;
        }
        if (fail_cpu) { errno = EIO; return -1; }
        return cpu_queries == 1 ? 2 : 3; // SW_MAX re-evaluates the selected arm
    }
    static auto original = reinterpret_cast<long (*)(int)>(dlsym(RTLD_NEXT, "sysconf"));
    return original(name);
}
extern "C" int getrlimit(__rlimit_resource_t resource, struct rlimit *value) noexcept {
    if (active && resource == RLIMIT_NOFILE) {
        ++limit_queries;
        facts_ok = facts_ok && limit_queries == 1 && SwooleG.logger == published
            && SwooleTG.buffer_stack && SwooleG.memory_pool
            && SwooleG.max_sockets == SW_MAX_SOCKETS_DEFAULT && SwooleG.task_tmpfile.empty()
            && SwooleG.bug_report_message.empty();
        if (fail_limit) { errno = EMFILE; return -1; }
        value->rlim_cur = value->rlim_max = current_limit;
        return 0;
    }
    static auto original = reinterpret_cast<int (*)(__rlimit_resource_t, struct rlimit *)>(dlsym(RTLD_NEXT, "getrlimit"));
    return original(resource, value);
}

static void run(unsigned index, rlim_t limit, bool cpu_failure, bool limit_failure) {
    sink = std::tmpfile(); require(sink);
    published = nullptr; cpu_queries = limit_queries = 0; facts_ok = true;
    current_limit = limit; fail_cpu = cpu_failure; fail_limit = limit_failure;
    swoole_set_last_error(0);
    active = true;
    swoole_init();
    active = false;
    const uint32_t narrowed = static_cast<uint32_t>(limit);
    const uint32_t expected = limit_failure ? SW_MAX_SOCKETS_DEFAULT :
        (narrowed < SW_SESSION_LIST_SIZE ? narrowed : SW_SESSION_LIST_SIZE);
    require(facts_ok && limit_queries == 1 && SwooleG.logger == published
            && SwooleG.cpu_num == (cpu_failure ? 1 : 3)
            && cpu_queries == (cpu_failure ? 1 : 2) && SwooleG.max_sockets == expected
            && !SwooleG.task_tmpfile.empty() && !SwooleG.bug_report_message.empty());
    if (limit_failure) {
        const std::string message = std::string("swoole_init(): getrlimit() failed, Error: ")
            + swoole_strerror(EMFILE) + "[" + std::to_string(EMFILE) + "]";
        require(swoole_get_last_error() == EMFILE && swoole_get_last_error_msg() == message);
        std::fflush(sink); std::rewind(sink); char bytes[4096] = {};
        const size_t length = std::fread(bytes, 1, sizeof(bytes) - 1, sink);
        const std::string logged(bytes, length);
        require(logged.find(message) != std::string::npos
                && logged.find(message, logged.find(message) + 1) == std::string::npos);
    }
    // The repeated guard must bypass every intercepted discovery/syscall.
    active = true; swoole_init(); active = false;
    require(cpu_queries == (cpu_failure ? 1 : 2) && limit_queries == 1 && SwooleG.logger == published);
    if (limit_failure)
        std::printf("case%u:cpu3,queries2,sockets%u,warning-original-identity,errno-published,continued\n", index, expected);
    else
        std::printf("case%u:cpu%u,queries%u,sockets%u,fresh-logger,guard-published\n", index,
                    SwooleG.cpu_num, cpu_queries, expected);
    swoole_clean(); std::fclose(sink); sink = nullptr;
    require(!SwooleG.init && !SwooleG.logger && !SwooleG.memory_pool && !SwooleTG.buffer_stack);
}
int main() {
    const rlim_t values[] = {0, 1, 1023, 1024, SW_SESSION_LIST_SIZE, SW_SESSION_LIST_SIZE + 1,
        UINT32_MAX, (static_cast<rlim_t>(1) << 32) | 5, RLIM_INFINITY};
    for (unsigned i = 0; i < sizeof(values) / sizeof(values[0]); ++i) run(i, values[i], false, false);
    run(9, 65535, true, false);
    run(10, 0, false, true);
}
