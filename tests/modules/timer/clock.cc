// Actual complete src/os/timer.cc, with only its setitimer execution boundary captured.
#include "swoole_timer.h"
#include <sys/time.h>
#include <cerrno>
#include <climits>
#include <iostream>
#include <initializer_list>

static itimerval observed;
static int calls, selected, syscall_result;
static int record_setitimer(int which, const itimerval *value, itimerval *) {
    ++calls;
    selected = which;
    observed = *value;
    if (syscall_result < 0) errno = EINTR;
    return syscall_result;
}
#define setitimer record_setitimer
#include SWR_TIMER_OS_SOURCE
#undef setitimer

int main() {
    for (long delay : {LONG_MIN, -1001L, -1L, 0L, 1L, 999L, 1000L, 1001L, LONG_MAX}) {
        for (int result : {-1, 0}) {
            syscall_result = result;
            calls = 0;
            errno = EDOM;
            const int status = swoole::SystemTimer_set(nullptr, delay);
            const int error = errno;
            std::cout << "system\t" << delay << '\t' << result << '\t' << status << '\t' << error
                      << '\t' << calls << '\t' << selected << '\t' << observed.it_interval.tv_sec
                      << '\t' << observed.it_interval.tv_usec << '\t' << observed.it_value.tv_sec
                      << '\t' << observed.it_value.tv_usec << '\n';
        }
    }
    for (long seconds : {-1000L, -1L, 0L, 1L, LONG_MAX / 2}) {
        for (long nanos : {-999999999L, -1L, 0L, 1L, 999999999L, 1000000000L, 1999999999L, 2000000000L, 4294967295000000000L, 4294967296000000000L, 4294967297000000000L}) {
            for (int64_t add : std::initializer_list<int64_t>{INT64_MIN, -1001001L, -1001L, -1000L, -999L, -1L, 0L, 1L, 999L, 1000L, 1001L, 1001001L, INT64_MAX}) {
                timespec value{seconds, nanos};
                errno = EDOM;
                swoole::realtime_add(&value, add);
                const int error = errno;
                std::cout << "add\t" << seconds << '\t' << nanos << '\t' << add << '\t'
                          << value.tv_sec << '\t' << value.tv_nsec << '\t' << error << '\n';
            }
        }
    }
    // Actual unchanged native acquisition; compare only a clock-bracket predicate,
    // never elapsed performance or equality of separate wall-clock reads.
    const auto before = std::chrono::system_clock::now();
    timespec value{};
    errno = EDOM;
    swoole::realtime_get(&value);
    const int error = errno;
    const auto after = std::chrono::system_clock::now();
    const auto stamp = std::chrono::seconds(value.tv_sec) + std::chrono::nanoseconds(value.tv_nsec);
    const bool inside = before.time_since_epoch() <= stamp && stamp <= after.time_since_epoch();
    std::cout << "get\t" << inside << '\t' << error << '\n';
    return inside ? 0 : 1;
}
