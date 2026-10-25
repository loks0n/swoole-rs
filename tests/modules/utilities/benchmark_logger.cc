// Complete pinned/overlaid Logger::put bodies; deterministic date/identity,
// real native mutex and private FILE custody. No elapsed clock in --check.
#include <cassert>
#include <cerrno>
#include <chrono>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <iostream>
#include <mutex>
#include <memory>
#include <stdexcept>
#include <string>
#include <unistd.h>
#include "swoole_rs_utilities.h"
#define SW_LOG_DATE_STRLEN 128
#define SW_LOG_BUFFER_SIZE (16384 + 256)
#define SW_LOG_DEBUG 0
#define SW_LOG_TRACE 1
#define SW_LOG_INFO 2
#define SW_LOG_NOTICE 3
#define SW_LOG_WARNING 4
#define SW_LOG_ERROR 5
static bool held;
static size_t reads, clock_calls;
struct TrackedMutex {
    std::mutex value;
    void lock() { value.lock(); assert(!held); held=true; }
    bool try_lock() { if (!value.try_lock()) return false; assert(!held); held=true; return true; }
    void unlock() { assert(held); held=false; value.unlock(); }
};
struct Opened {
    bool value=true;
    operator bool() const { assert(held); ++reads; return value; }
};
struct FixtureLogger {
    int log_level=0, log_rotation=0;
    bool date_with_microseconds=false, display_backtrace_=false;
    Opened opened;
    std::string date_format="M14", log_file="private-stream", log_real_file="private-stream";
    FILE *log_fp=nullptr;
    TrackedMutex lock;
    std::string gen_real_file(const std::string &path) { return path; }
    void reopen_without_lock() { throw std::runtime_error("unexpected rotation"); }
    void configure(const std::string &name) {
        log_level = name == "logger-filtered" ? SW_LOG_WARNING : SW_LOG_DEBUG;
        date_with_microseconds = name == "logger-micros";
        opened.value = name != "logger-unlocked-stream";
        log_rotation = name == "logger-stable-rotation";
    }
};
// Candidate state is the production Rust owner, with native FILE/mutex custody.
// Configuration and destruction occur outside the measured loop.
struct OwnedFixtureLogger {
    SwrUtilsLogState *state = nullptr;
    FILE *log_fp = nullptr;
    TrackedMutex lock;
    OwnedFixtureLogger() {
        assert(swr_v1_utils_log_state_create(std::string().max_size(), &state) == SWR_UTILS_STATE_OK);
        for (const auto field : {SWR_UTILS_STATE_DATE, SWR_UTILS_STATE_FILE, SWR_UTILS_STATE_REAL_FILE}) {
            const std::string value = field == SWR_UTILS_STATE_DATE ? "M14" : "private-stream";
            assert(swr_v1_utils_log_state_text_set(state, field,
                reinterpret_cast<const uint8_t *>(value.data()), value.size()) == SWR_UTILS_STATE_OK);
        }
    }
    ~OwnedFixtureLogger() { swr_v1_utils_log_state_destroy(state); }
    OwnedFixtureLogger(const OwnedFixtureLogger &) = delete;
    OwnedFixtureLogger &operator=(const OwnedFixtureLogger &) = delete;
    void configure(const std::string &name) {
        const auto set = [&](uint32_t field, int32_t value) {
            assert(swr_v1_utils_log_state_scalar_set(state, field, value) == SWR_UTILS_STATE_OK);
        };
        set(SWR_UTILS_STATE_LEVEL, name == "logger-filtered" ? SW_LOG_WARNING : SW_LOG_DEBUG);
        set(SWR_UTILS_STATE_MICROS, name == "logger-micros");
        set(SWR_UTILS_STATE_OPENED, name != "logger-unlocked-stream");
        set(SWR_UTILS_STATE_ROTATION, name == "logger-stable-rotation");
    }
    SwrUtilsLogPath *make_real_path(const char *, size_t) const {
        SwrUtilsLogPath *path = nullptr;
        assert(swr_v1_utils_log_path_create(state, 0, nullptr, 0, &path) == SWR_UTILS_STATE_OK);
        return path; // Stable-rotation fixture retains its identity path adapter.
    }
    const char *get_file() const { return swr_v1_utils_log_state_text_get(state, SWR_UTILS_STATE_FILE); }
    const char *get_real_file() const { return swr_v1_utils_log_state_text_get(state, SWR_UTILS_STATE_REAL_FILE); }
    std::string gen_real_file(const std::string &path) { return path; }
    void reopen_without_lock() { throw std::runtime_error("unexpected rotation"); }
};
inline uint32_t observed_emit_step(const SwrUtilsLogState *state, uint32_t *phase,
                                    int32_t level, uint8_t changed, uint8_t acquired, int32_t pid) {
    if (*phase == SWR_UTILS_LOG_PUT_FILE_LOCK_PHASE || *phase == SWR_UTILS_LOG_PUT_FILE_UNLOCK_PHASE) {
        assert(held && "owned opened observation before native Logger mutex");
        ++reads;
    }
    return swr_v1_utils_log_state_emit_step(state, phase, level, changed, acquired, pid);
}
inline uint32_t observed_path_step(const SwrUtilsLogState *state, uint32_t *phase,
                                   int32_t level, const SwrUtilsLogPath *path, uint8_t acquired, int32_t pid) {
    if (*phase == SWR_UTILS_LOG_PUT_FILE_LOCK_PHASE || *phase == SWR_UTILS_LOG_PUT_FILE_UNLOCK_PHASE) {
        assert(held && "owned opened observation before native Logger mutex");
        ++reads;
    }
    return swr_v1_utils_log_path_emit_step(state, phase, level, path, acquired, pid);
}
namespace fixture_clock {
struct microseconds {};
struct Duration { long long count() const { return 1234000567; } };
struct system_clock {
    struct time_point { Duration time_since_epoch() const { return {}; } };
    static time_point now() { ++clock_calls; return {}; }
    static time_t to_time_t(time_point) { return 1234; }
};
template<class T> Duration duration_cast(Duration duration) { return duration; }
}
static int swoole_get_worker_id() { return 3; }
static int swoole_get_worker_pid() { return 123; }
static char swoole_get_worker_symbol() { return '@'; }
static void swoole_print_backtrace() { throw std::runtime_error("unexpected backtrace"); }
#define sw_unlikely(x) (x)
#define swr_v1_utils_log_state_emit_step observed_emit_step
#define swr_v1_utils_log_path_emit_step observed_path_step
#include "benchmark-put.inc"
#undef swr_v1_utils_log_path_emit_step
#undef swr_v1_utils_log_state_emit_step
#undef sw_unlikely
struct Result { std::string bytes; size_t opened_reads, dates; long long elapsed_ns; };
template<class Logger> static Result run(const std::string &name, uint64_t iterations, bool measure) {
    Logger logger;
    logger.configure(name);
    std::string payload(name=="logger-truncated" ? SW_LOG_BUFFER_SIZE*2 : 96, 'x');
    FILE *stream=std::tmpfile();
    if (!stream) throw std::runtime_error("private tmpfile failed");
    logger.log_fp=stream; reads=0; clock_calls=0; held=false;
    std::chrono::steady_clock::time_point begin;
    if (measure) begin=std::chrono::steady_clock::now();
    for(uint64_t i=0;i<iterations;++i) {
        asm volatile("" ::: "memory");
        logger.put(SW_LOG_NOTICE,payload.data(),payload.size());
    }
    const auto elapsed=measure ? std::chrono::duration_cast<std::chrono::nanoseconds>(
                                    std::chrono::steady_clock::now()-begin).count() : 0;
    assert(!held);
    const size_t expected_reads=name=="logger-filtered" ? 0 : 2*iterations;
    if (reads!=expected_reads || clock_calls!=(name=="logger-filtered" ? 0 : iterations))
        throw std::runtime_error("filter/locked opened observation mismatch");
    std::rewind(stream); std::string bytes; char buffer[4096]; size_t count;
    while ((count=std::fread(buffer,1,sizeof(buffer),stream))) bytes.append(buffer,count);
    if (std::ferror(stream) || std::fclose(stream)) throw std::runtime_error("FILE custody failed");
    return {bytes,reads,clock_calls,elapsed};
}
int main(int argc,char **argv) {
    try {
        if(argc!=5) throw std::runtime_error("--check|--measure native|rust workload iterations required");
        std::string mode=argv[1],engine=argv[2],name=argv[3]; size_t consumed=0;
        const uint64_t iterations=std::stoull(argv[4],&consumed);
        if((mode!="--check" && mode!="--measure") || (engine!="native" && engine!="rust") ||
           !iterations || iterations>4096 || consumed!=std::strlen(argv[4])) throw std::runtime_error("invalid arguments/count (maximum4096)");
        if(name!="logger-filtered" && name!="logger-normal" && name!="logger-truncated" && name!="logger-micros" &&
           name!="logger-unlocked-stream" && name!="logger-stable-rotation") throw std::runtime_error("unknown logger workload");
        const auto native=run<reference::Logger>(name,1,false),rust=run<candidate::Logger>(name,1,false);
        if(native.bytes!=rust.bytes) throw std::runtime_error("complete Logger::put warmup mismatch");
        const auto result=engine=="native" ? run<reference::Logger>(name,iterations,mode=="--measure") : run<candidate::Logger>(name,iterations,mode=="--measure");
        if(result.bytes.size()!=native.bytes.size()*iterations) throw std::runtime_error("record byte count mismatch");
        for(uint64_t i=0;i<iterations;++i)
            if(result.bytes.compare(i*native.bytes.size(),native.bytes.size(),native.bytes)) throw std::runtime_error("record bytes mismatch");
        if(name=="logger-filtered" && !result.bytes.empty()) throw std::runtime_error("filtered record written");
        if(name=="logger-truncated" && native.bytes.size()!=SW_LOG_BUFFER_SIZE-1) throw std::runtime_error("truncation boundary mismatch");
        uint64_t checksum=0;for(unsigned char byte:result.bytes) checksum=checksum*33+byte;
        std::cout<<"{\"workload\":\""<<name<<"\",\"engine\":\""<<engine<<"\",\"iterations\":"<<iterations
                 <<",\"checksum\":"<<checksum<<",\"bytes\":"<<result.bytes.size()<<",\"opened_reads\":"<<result.opened_reads
                 <<",\"date_calls\":"<<result.dates<<",\"elapsed_ns\":"<<result.elapsed_ns<<"}\n";
    } catch(const std::exception &error) {std::cerr<<error.what()<<'\n';return 1;}
}
