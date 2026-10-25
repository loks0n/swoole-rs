// Actual public Logger consumers; external runtime adapters are supplied by the
// standalone gate, never used as evidence for the production global/PHP world.
#include "swoole_process_pool.h"
#include <cassert>
#include <cstdarg>
#include <fstream>
#include <iostream>
#include <thread>
#include <ctime>
#include <vector>
#include <dirent.h>
#include <sys/stat.h>

thread_local swoole::ThreadGlobal SwooleTG{};
thread_local char sw_error[SW_ERROR_MSG_SIZE];
static swoole::Logger *active;
static unsigned backtraces;
swoole::Logger *sw_logger() { return active; }
int swoole_get_log_level() { return active ? active->get_level() : SW_LOG_NONE; }
bool swoole_is_ignored_error(int) { return false; }
const char *swoole_strerror(int error) { return strerror(error); }
swoole::WorkerId swoole_get_worker_id() { return 7; }
pid_t swoole_get_worker_pid() { return 123; }
char swoole_get_worker_symbol() { return 'W'; }
void swoole_print_backtrace() { ++backtraces; }
void swoole_redirect_stdout(int fd) {
    assert(dup2(fd, STDOUT_FILENO) >= 0);
    assert(dup2(fd, STDERR_FILENO) >= 0);
}
size_t sw_snprintf(char *buffer, size_t size, const char *format, ...) {
    va_list args;
    va_start(args, format);
    int n = vsnprintf(buffer, size, format, args);
    va_end(args);
    return n < 0 ? 0 : std::min(size - 1, static_cast<size_t>(n));
}
static std::string read(const std::string &path) {
    std::ifstream input(path);
    return {std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
}
int main(int argc, char **argv) {
    assert(argc == 2);
    const std::string path = std::string(argv[1]) + "/logger.txt";
    unsigned checks = 0;
    {
        swoole::Logger logger;
        active = &logger;
        assert(!logger.is_opened() && logger.get_level() == SW_LOG_INFO);
        assert(std::string(logger.get_file()).empty());
        assert(std::string(logger.get_real_file()).empty());
        logger.set_level(-100); assert(logger.get_level() == SW_LOG_DEBUG);
        logger.set_level(100); assert(logger.get_level() == SW_LOG_NONE);
        logger.reset(); assert(logger.get_level() == SW_LOG_INFO);
        checks += 5;
        assert(logger.open(path.c_str()));
        assert(std::string(logger.get_file()) == path);
        assert(std::string(logger.get_real_file()) == path);
        const char *stable = logger.get_file();
        logger.set_level(SW_LOG_INFO);
        assert(stable == logger.get_file());
        logger.put(SW_LOG_INFO, "first", 5);
        logger.reopen();
        assert(logger.is_opened() && std::string(logger.get_file()) == path);
        logger.put(SW_LOG_INFO, "second", 6);
        logger.close();
        assert(!logger.is_opened() && std::string(logger.get_file()).empty());
        assert(std::string(logger.get_real_file()) == path);
        auto content = read(path);
        assert(content.find("first") != std::string::npos && content.find("second") != std::string::npos);
        checks += 8;
        FILE *stream = tmpfile(); assert(stream);
        logger.set_stream(stream);
        logger.put(SW_LOG_INFO, "stream", 6);
        assert(backtraces == 0);
        logger.display_backtrace();
        logger.put(SW_LOG_DEBUG, "filtered", 8); assert(backtraces == 0);
        logger.put(SW_LOG_INFO, "enabled", 7); assert(backtraces == 1);
        logger.reset(); logger.put(SW_LOG_INFO, "reset", 5); assert(backtraces == 2);
        logger.close(); // Unowned set_stream FILE is retained and stays open.
        assert(fseek(stream, 0, SEEK_SET) == 0);
        char buffer[2048]{};
        auto count = fread(buffer, 1, sizeof(buffer) - 1, stream);
        std::string output(buffer, count);
        assert(output.find("stream") != std::string::npos);
        assert(output.find("filtered") == std::string::npos);
        logger.set_stream(stdout);
        fclose(stream);
        checks += 7;
        logger.set_rotation(SW_LOG_ROTATION_DAILY);
        assert(logger.open(path.c_str()));
        std::string resolved = logger.get_real_file();
        assert(resolved.find(path + ".") == 0);
        logger.reopen(); assert(resolved == logger.get_real_file());
        logger.close();
        logger.reset();
        assert(logger.set_date_format("%Y"));
        logger.set_date_with_microseconds(true);
        assert(logger.open(path.c_str()));
        assert(logger.redirect_stdout_and_stderr(true));
        assert(write(STDOUT_FILENO, "redirect-out\n", 13) == 13);
        assert(write(STDERR_FILENO, "redirect-err\n", 13) == 13);
        assert(logger.redirect_stdout_and_stderr(false));
        logger.close();
        content = read(path);
        assert(content.find("redirect-out\n") != std::string::npos);
        assert(content.find("redirect-err\n") != std::string::npos);
        checks += 9;
        active = nullptr;
    }
    // Destruction releases strings/state, preserving explicit close admission:
    // it must not close an unowned stream.
    FILE *external = tmpfile(); assert(external);
    { swoole::Logger logger; logger.set_stream(external); }
    assert(fputs("alive", external) >= 0); fclose(external); ++checks;
    // set_stream must close an owned file before publishing an unowned stream.
    {
        swoole::Logger logger;
        FILE *stream = tmpfile(); assert(stream);
        assert(logger.open(path.c_str()));
        logger.set_stream(stream);
        assert(!logger.is_opened() && std::string(logger.get_file()).empty());
        assert(std::string(logger.get_real_file()) == path);
        logger.put(SW_LOG_INFO, "replacement", 11);
        assert(fseek(stream, 0, SEEK_SET) == 0);
        char buffer[256]{};
        assert(fread(buffer, 1, sizeof(buffer) - 1, stream) > 0);
        assert(std::string(buffer).find("replacement") != std::string::npos);
        logger.set_stream(stdout);
        fclose(stream);
    }
    // One writer owns calendar calls; SINGLE rotation means reopen does not
    // share localtime's static tm. Only put/reopen run concurrently, as allowed.
    constexpr unsigned records = 1024, reopens = 128;
    const std::string concurrent = std::string(argv[1]) + "/concurrent.txt";
    {
        swoole::Logger logger;
        assert(logger.open(concurrent.c_str()));
        std::thread writer([&] {
            for (unsigned i = 0; i < records; ++i) {
                auto content = "#owned:" + std::to_string(i) + "#";
                logger.put(SW_LOG_INFO, content.data(), content.size());
            }
        });
        std::thread reopener([&] {
            for (unsigned i = 0; i < reopens; ++i) logger.reopen();
        });
        writer.join(); reopener.join();
        logger.close();
    }
    std::ifstream input(concurrent);
    std::string line;
    unsigned seen = 0;
    while (std::getline(input, line)) {
        assert(line.find("\tINFO\t#owned:" + std::to_string(seen) + "#") != std::string::npos);
        ++seen;
    }
    assert(seen == records);
    unsigned path_values = 0;
    {
        swoole::Logger logger;
        const std::vector<std::string> names = {"", "a", std::string(255, 'x'),
            std::string("a\0b", 3), std::string("\xff\x80", 2), "relative/./../name"};
        for (int rotation : {-7, 0, 1, 2, 3, 4, 99}) {
            logger.set_rotation(rotation);
            const char *format = rotation == 1 ? "%Y%m" : rotation == 3 ? "%Y%m%d%H" :
                                 rotation == 4 ? "%Y%m%d%H%M" : "%Y%m%d";
            for (const auto &name : names) {
                const auto before = time(nullptr);
                const auto value = logger.gen_real_file(name);
                const auto after = time(nullptr);
                const auto expected = [&](time_t now) {
                    char date[16];
                    const size_t length = std::strftime(date, sizeof(date), format, std::localtime(&now));
                    return name + "." + std::string(date, length);
                };
                assert(value == expected(before) || value == expected(after));
                ++path_values;
            }
        }
        const std::string long_path = std::string(argv[1]) + "/" + std::string(180, 'p');
        logger.reset();
        assert(logger.open(long_path.c_str()));
        logger.put(SW_LOG_INFO, "before-capture", 14);
        logger.reopen();
        assert(std::string(logger.get_file()) == long_path && logger.is_opened());
        logger.put(SW_LOG_INFO, "after-capture", 13);
        logger.close();
        assert(std::string(logger.get_real_file()) == long_path);
        const auto content = read(long_path);
        assert(content.find("before-capture") != std::string::npos);
        assert(content.find("after-capture") != std::string::npos);
    }
    // Exercise actual filesystem effects for every rotation selector. Each
    // iteration owns a fresh Logger and basename, so native and selected runs
    // observe independent files while the same exact record assertions apply.
    unsigned rotation_io = 0;
    for (int rotation : {-7, 0, 1, 2, 3, 4, 99}) {
        for (const auto &name : std::vector<std::string>{"ordinary", std::string(180, 'p'),
                                                       std::string("utf8-\xc3\xa9", 7)}) {
            swoole::Logger logger;
            const auto directory = std::string(argv[1]) + "/io-" + std::to_string(rotation_io);
            assert(mkdir(directory.c_str(), 0700) == 0);
            const auto basename = directory + "/" + name;
            logger.set_rotation(rotation);
            const auto before = time(nullptr);
            assert(logger.open(basename.c_str()));
            const auto after = time(nullptr);
            const std::string opened = logger.get_real_file();
            const auto expected = [&](time_t now) {
                if (rotation == 0) return basename;
                const char *format = rotation == 1 ? "%Y%m" : rotation == 3 ? "%Y%m%d%H" :
                                     rotation == 4 ? "%Y%m%d%H%M" : "%Y%m%d";
                char date[16];
                const auto length = std::strftime(date, sizeof(date), format, std::localtime(&now));
                return basename + "." + std::string(date, length);
            };
            assert(opened == expected(before) || opened == expected(after));
            assert(std::string(logger.get_file()) == basename && logger.is_opened());
            logger.put(SW_LOG_INFO, "path-record-before", 18);
            logger.reopen();
            assert(std::string(logger.get_file()) == basename && logger.is_opened());
            const std::string reopened = logger.get_real_file();
            logger.put(SW_LOG_INFO, "path-record-after", 17);
            logger.close();
            assert(!logger.is_opened() && std::string(logger.get_file()).empty());
            assert(std::string(logger.get_real_file()) == reopened);
            // Read every generated file, allowing a real calendar rollover
            // between open, put and reopen without accepting missing records.
            unsigned before_count = 0, after_count = 0, lines = 0;
            DIR *files = opendir(directory.c_str()); assert(files);
            while (auto *entry = readdir(files)) {
                const std::string filename = entry->d_name;
                if (filename == "." || filename == "..") continue;
                assert(filename == name || filename.find(name + ".") == 0);
                const auto content = read(directory + "/" + filename);
                for (char byte : content) if (byte == '\n') ++lines;
                for (size_t at = 0; (at = content.find("\tINFO\tpath-record-before\n", at)) != std::string::npos; ++at)
                    ++before_count;
                for (size_t at = 0; (at = content.find("\tINFO\tpath-record-after\n", at)) != std::string::npos; ++at)
                    ++after_count;
            }
            assert(closedir(files) == 0 && lines == 2);
            assert(before_count == 1 && after_count == 1);
            ++rotation_io;
        }
    }
    std::cout << "{\"public_checks\":" << checks << ",\"backtrace_effects\":" << backtraces
              << ",\"stream_replacement\":true,\"concurrent_records\":" << records
              << ",\"reopen_cycles\":" << reopens << ",\"path_values\":" << path_values
              << ",\"rotation_io\":" << rotation_io << ",\"long_path_reopen\":true}\n";
}
