// Exact random bodies + real preserved native logger/error authority.
// Controlled entropy failures; not a full selected Swoole/PHP build.
#include "swoole.h"
#include "swoole_rs_corebase.h"
#include <cassert>
#include <cerrno>
#include <cstring>
#include <dlfcn.h>
#include <fcntl.h>
#include <fstream>
#include <iostream>
#include <string>
#include <unistd.h>
static int opens, reads, error_code;
static ssize_t read_count;
static int controlled_open(const char *path, int flags) {
    assert(std::strcmp(path, "/dev/urandom") == 0 && flags == O_RDONLY);
    ++opens; return 42;
}
static ssize_t controlled_read(int fd, void *out, size_t size) {
    assert(fd == 42 && size == sizeof(unsigned)); ++reads;
    if (read_count > 0) std::memset(out, 0, size_t(read_count));
    errno = error_code; return read_count;
}
#define open controlled_open
#define read controlled_read
#ifdef SELECTED
#include "random-selected.inc"
#else
#include "random-original.inc"
#endif
#undef open
#undef read
int main(int argc, char **argv) {
    assert(argc == 2);
    Dl_info image{}; assert(dladdr(reinterpret_cast<void *>(sw_logger), &image) != 0);
    std::cout << "native_logger_image=" << image.dli_fname << "\n";
    swoole_init();
    for (int level : {SW_LOG_WARNING, SW_LOG_ERROR, SW_LOG_NONE}) {
        auto path = std::string(argv[1]) + "." + std::to_string(level);
        auto *logger = sw_logger(); logger->set_level(level); assert(logger->open(path.c_str()));
        std::string expected_log;
        for (int err : {EINTR, EDOM, EACCES}) {
            error_code = err; read_count = err == EINTR ? -1 : err == EDOM ? 2 : 0;
            std::strcpy(sw_error, "sentinel"); swoole_set_last_error(0);
            assert(swoole_system_random(10, 20) == -1);
            int returned_errno = errno; assert(swoole_get_last_error() == err);
            auto payload = std::string("swoole_system_random(): read() from /dev/urandom failed, Error: ")
                           + swoole_strerror(err) + "[" + std::to_string(err) + "]";
            assert(std::string(sw_error) == (level == SW_LOG_NONE ? "sentinel" : payload));
            if (level == SW_LOG_WARNING) expected_log += payload + "\n";
            std::cout << "state " << level << " " << err << " " << returned_errno << " "
                      << swoole_get_last_error() << " " << sw_error << "\n";
        }
        logger->close(); std::ifstream input(path); std::string line, actual;
        while (std::getline(input, line)) {
            auto prefix = line.find("]\tWARNING\t"); assert(prefix != std::string::npos);
            actual += line.substr(prefix + std::strlen("]\tWARNING\t")) + "\n";
        }
        assert(actual == expected_log);
    }
    assert(opens == 1 && reads == 9); swoole_clean();
    std::cout << "actual native logger random-read failure PASS9state rows/engine\n";
}
