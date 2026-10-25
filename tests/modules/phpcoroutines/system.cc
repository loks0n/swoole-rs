// Normal frontend bodies with inert file/timer effects. No filesystem or sleep.
#include <cassert>
#include <cstdint>
#include <fcntl.h>
#include <cstring>
#include <sys/socket.h>
#include <netinet/in.h>
#include <iostream>
#include <limits>
#include <string>
#include <sys/file.h>
#include <sys/statvfs.h>
#include <vector>
#include "swoole_rs_phpcoroutines.h"
using zend_long = int64_t;
constexpr int SW_FILE_LOCK = LOCK_EX, SW_FILE_APPEND = 8;
constexpr double SW_TIMER_MIN_SEC = 0.001;
std::vector<std::string> trace;
const char path_arg[] = "ordinary-file";
char data_arg[] = {'a', '\0', 'b'};
zend_long parsed_flags, parsed_family = AF_INET;
zend_long parsed_long(const char *name) {
    if (!std::strcmp(name, "flags")) return parsed_flags;
    if (!std::strcmp(name, "family")) return parsed_family;
    return !std::strcmp(name, "socktype") ? zend_long(SOCK_STREAM) : zend_long(IPPROTO_TCP);
}
char service_arg[] = "svc";
void parse_string(const char *name, char *&value, size_t &length) {
    bool service = !std::strcmp(name, "service");
    value = service ? service_arg : data_arg;
    length = service ? sizeof(service_arg)-1 : sizeof(data_arg);
}
#define PHP_METHOD(class_name, method) void method()
#define PHP_FUNCTION(name) void name()
#define ZEND_PARSE_PARAMETERS_START(min, max)
#define Z_PARAM_PATH(value, length) value = const_cast<char *>(path_arg); length = sizeof(path_arg) - 1; (void)length;
#define Z_PARAM_STRING(value, length) parse_string(#value, value, length); (void)length;
#define Z_PARAM_LONG(value) value = parsed_long(#value);
#define Z_PARAM_DOUBLE(value) value = 0.125;
#define Z_PARAM_OPTIONAL
#define ZEND_PARSE_PARAMETERS_END_EX(value)
#define RETURN_FALSE return
#define RETURN_LONG(value) do { trace.push_back("long:" + std::to_string(value)); return; } while (false)
#define RETURN_BOOL(value) do { trace.push_back(std::string("bool:") + ((value) ? "true" : "false")); return; } while (false)
#define RETVAL_STRINGL(value, length) trace.push_back("binary:" + std::to_string(length) + ":" + std::to_string((value)[1]));
#define RETURN_STRINGL(value, length) do { RETVAL_STRINGL(value, length); return; } while (false)
#define UNEXPECTED(value) (value)
#define ZEND_TOSTR(value) "0.001"
#define E_WARNING 1
void zend_value_error(const char *) { assert(false); }
void php_swoole_fatal_error(int, const char *) { assert(false); }
struct Buffer { char *str; size_t length; };
namespace Coroutine {
void get_current_safe() { trace.push_back("safe-current-stub"); }
}
namespace System {
std::string gethostbyname(const std::string &domain, zend_long family, double timeout) {
    assert(domain == std::string(data_arg, sizeof(data_arg)) && family == parsed_family && timeout == 0.125);
    trace.push_back("host-stub:" + std::to_string(family));
    return std::string(data_arg, sizeof(data_arg));
}
std::vector<std::string> getaddrinfo(const char *host, zend_long family, zend_long socktype, zend_long protocol,
                                   const std::string &service, double timeout) {
    assert(host == data_arg && family == parsed_family && socktype == SOCK_STREAM && protocol == IPPROTO_TCP);
    assert(service == service_arg && timeout == 0.125);
    trace.push_back("addrinfo-stub:" + std::to_string(family));
    return {std::string(data_arg, sizeof(data_arg)), "", "127.0.0.1"};
}
Buffer *read_file(const char *path, int lock) {
    assert(std::string(path) == path_arg);
    trace.push_back("read-stub:" + std::to_string(lock));
    static Buffer result{data_arg, sizeof(data_arg)};
    return &result;
}
ssize_t write_file(const char *path, const char *data, size_t length, int lock, int flags) {
    assert(std::string(path) == path_arg && data == data_arg && length == sizeof(data_arg));
    trace.push_back("write-stub:" + std::to_string(lock) + ":" + std::to_string(flags));
    return ssize_t(length);
}
int sleep(double seconds) { assert(seconds == 0.125); trace.push_back("sleep-stub"); return 0; }
}
void *return_value = nullptr;
void array_init(void *) { trace.push_back("array"); }
template<class T> void add_assoc_long(void *, const char *key, T value) { trace.push_back(std::string(key) + ":" + std::to_string(value)); }
void add_next_index_stringl(void *, const char *data, size_t length) {
    std::string item = "item:" + std::to_string(length);
    for (size_t i = 0; i < length; ++i) item += ":" + std::to_string(static_cast<unsigned char>(data[i]));
    trace.push_back(item);
}
int swoole_coroutine_statvfs(const char *path, struct statvfs *value) {
    assert(std::string(path) == path_arg);
    *value = {};
    value->f_bsize = 1024;
    value->f_frsize = 1025;
    value->f_blocks = 1026;
    value->f_bfree = 1027;
    value->f_bavail = 1028;
    value->f_files = 1029;
    value->f_ffree = 1030;
    value->f_favail = 1031;
    value->f_fsid = 1032;
    value->f_flag = 1033;
    value->f_namemax = 1034;
    trace.push_back("statvfs-stub");
    return 0;
}
// ACTUAL_BODIES
int main() {
    for (zend_long flags : {zend_long(0), zend_long(SW_FILE_LOCK), zend_long(SW_FILE_APPEND),
                           zend_long(SW_FILE_APPEND | SW_FILE_LOCK), zend_long(-1),
                           std::numeric_limits<zend_long>::min(), std::numeric_limits<zend_long>::max()}) {
        parsed_flags = flags;
        readFile();
        writeFile();
    }
    statvfs();
    sleep();
    for (zend_long family : {zend_long(AF_INET), zend_long(AF_INET6)}) {
        parsed_family = family;
        swoole_coroutine_gethostbyname();
        getaddrinfo();
    }
    for (const auto &event : trace) std::cout << event << '\n';
#ifdef SWOOLE_RS_PHPCOROUTINES
    // Invalid/empty result choices are copied facts only; no native warning/error/IO branch executes.
    assert(swr_v1_phpcoroutines_system_address(0, AF_INET, AF_INET, AF_INET6) == SWR_CORO_ADDRESS_EMPTY);
    assert(swr_v1_phpcoroutines_system_address(3, -1, AF_INET, AF_INET6) == SWR_CORO_ADDRESS_FAMILY);
    assert(swr_v1_phpcoroutines_system_complete(SWR_CORO_RESULT_READ, nullptr, 0, 0).action == SWR_CORO_RESULT_FALSE);
    assert(swr_v1_phpcoroutines_system_complete(SWR_CORO_RESULT_WRITE, nullptr, -1, 0).action == SWR_CORO_RESULT_FALSE);
    assert(swr_v1_phpcoroutines_system_complete(SWR_CORO_RESULT_HOST, nullptr, 0, 0).action == SWR_CORO_RESULT_FALSE);
    swr_phpcoroutines_result_state state{};
    assert(swr_v1_phpcoroutines_system_complete(SWR_CORO_RESULT_ADDRINFO, &state, 0, 0).action == SWR_CORO_RESULT_FALSE);
    const swr_phpcoroutines_file_config config{SW_FILE_LOCK, SW_FILE_APPEND, O_CREAT | O_WRONLY | O_NOFOLLOW, O_APPEND, O_TRUNC};
    assert(!swr_v1_phpcoroutines_system_file(0, 0, &config).accepted);
    for (double seconds : {0.0, 0.001, 0.125, -1.0, std::numeric_limits<double>::infinity(),
                           -std::numeric_limits<double>::infinity(), std::numeric_limits<double>::quiet_NaN()}) {
        assert(bool(swr_v1_phpcoroutines_system_sleep(seconds, SW_TIMER_MIN_SEC)) == !(seconds < SW_TIMER_MIN_SEC));
    }
#endif
}
