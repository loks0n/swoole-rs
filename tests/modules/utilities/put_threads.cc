#include <array>
#include <atomic>
#include <cassert>
#include <cerrno>
#include <chrono>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <iostream>
#include <mutex>
#include <memory>
#include <string>
#include <thread>
#include <unistd.h>
#include <vector>
#include "swoole_rs_utilities.h"
#define SW_LOG_DATE_STRLEN 128
#define SW_LOG_BUFFER_SIZE (16384 + 256)
#define SW_LOG_DEBUG 0
#define SW_LOG_TRACE 1
#define SW_LOG_INFO 2
#define SW_LOG_NOTICE 3
#define SW_LOG_WARNING 4
#define SW_LOG_ERROR 5
static thread_local bool mutex_held;
static thread_local int writer_id;
static thread_local size_t opened_reads;
struct TrackedMutex {
    std::mutex native;
    void lock() { native.lock(); assert(!mutex_held); mutex_held=true; }
    bool try_lock() { if (!native.try_lock()) return false; assert(!mutex_held); mutex_held=true; return true; }
    void unlock() { assert(mutex_held); mutex_held=false; native.unlock(); }
};
struct ObservedOpened {
    bool value=true;
    operator bool() const { assert(mutex_held && "opened read before Logger mutex"); ++opened_reads; return value; }
};
struct FixtureLogger {
    int log_level=0, log_rotation=0;
    bool date_with_microseconds=false, display_backtrace_=false;
    ObservedOpened opened;
    std::string date_format="M14", log_file, log_real_file;
    FILE *log_fp=nullptr;
    TrackedMutex lock;
    std::string gen_real_file(const std::string &) { std::abort(); }
    void reopen_without_lock() { std::abort(); }
};
// The native localtime static-buffer race is outside this test. Keep calendar
// conversion on the native side with one thread-local tm, and a literal format.
static std::tm *thread_localtime(const time_t *value) {
    static thread_local std::tm result;
    return localtime_r(value, &result);
}
static int swoole_get_worker_id() { return writer_id; }
static int swoole_get_worker_pid() { return 123; }
static char swoole_get_worker_symbol() { return '%'; }
static void swoole_print_backtrace() { std::abort(); }
static size_t sw_snprintf(char *output, size_t capacity, const char *format, ...) {
    va_list args; va_start(args, format); const int n=vsnprintf(output, capacity, format, args); va_end(args);
    if (n < 0) return 0;
    return static_cast<size_t>(n) >= capacity ? capacity-1 : static_cast<size_t>(n);
}
#ifdef M14_STATE_ABI2
#include "put_state_threads.h"
#endif
#include "put-oracle.inc"
#ifdef M14_STATE_ABI2
#undef swr_v1_utils_log_state_emit_step
#endif
static constexpr size_t writers=4, records=4096, switches=1024;
template<class Logger> void run() {
    Logger logger;
    std::array<FILE *, 2> streams{{std::tmpfile(), std::tmpfile()}};
    assert(streams[0] && streams[1]); logger.log_fp=streams[0];
    std::atomic<size_t> ready{0}; std::atomic<bool> start{false};
    std::array<size_t, writers> observed{};
    std::vector<std::thread> threads;
    for (size_t writer=0; writer<writers; ++writer) {
        threads.emplace_back([&, writer] {
            writer_id=static_cast<int>(writer); opened_reads=0;
            ready.fetch_add(1);
            while (!start.load()) std::this_thread::yield();
            for (size_t record=0; record<records; ++record) {
                const auto payload="#M14:"+std::to_string(writer)+"-"+std::to_string(record)+"#";
                logger.put(SW_LOG_NOTICE, payload.data(), payload.size());
                assert(!mutex_held);
            }
            observed[writer]=opened_reads;
        });
    }
    threads.emplace_back([&] {
        ready.fetch_add(1);
        while (!start.load()) std::this_thread::yield();
        for (size_t step=0; step<switches; ++step) {
            logger.lock.lock();
            // Models native stream publication under Logger's mutex. No
            // unprotected mutation of date/rotation/threshold/backtrace fields.
            logger.log_fp=streams[step%2]; logger.opened.value=(step%3)!=0;
            logger.lock.unlock();
            std::this_thread::yield();
        }
    });
    while (ready.load()!=writers+1) std::this_thread::yield();
    start.store(true);
    for (auto &thread: threads) thread.join();
    std::array<std::vector<bool>, writers> seen;
    for (auto &rows: seen) rows.resize(records, false);
    size_t total=0;
    for (FILE *stream: streams) {
        std::rewind(stream);
        char line[256]; std::array<int, writers> previous{{-1,-1,-1,-1}};
        while (std::fgets(line, sizeof(line), stream)) {
            int prefix=-1, writer=-1, record=-1, consumed=0;
            assert(std::sscanf(line, "[M14 %%123.%d]\tNOTICE\t#M14:%d-%d#\n%n", &prefix, &writer, &record, &consumed)==3);
            assert(consumed==static_cast<int>(std::strlen(line)) && consumed>0 && line[consumed-1]=='\n');
            assert(writer>=0 && writer<static_cast<int>(writers) && prefix==writer);
            assert(record>=0 && record<static_cast<int>(records) && record>previous[writer]);
            assert(!seen[writer][record]); seen[writer][record]=true; previous[writer]=record; ++total;
        }
        assert(!std::ferror(stream)); assert(std::fclose(stream)==0);
    }
    assert(total==writers*records);
    for (size_t writer=0;writer<writers;++writer) {
        assert(observed[writer]==2*records);
        for (bool present: seen[writer]) assert(present);
    }
}
int main() {
    run<reference::Logger>(); run<candidate::Logger>();
    std::cout << "{\"engines\":2,\"writers_per_engine\":" << writers
              << ",\"records_per_engine\":" << writers*records
              << ",\"locked_opened_reads_per_engine\":" << writers*records*2
              << ",\"stream_switches_per_engine\":" << switches << "}\n";
}
