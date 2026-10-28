// SPDX-License-Identifier: Apache-2.0
// Real native task-directory filesystem, exception and publication witnesses.
#include "swoole.h"
#include "swoole_api.h"
#include "swoole_string.h"
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <dirent.h>
#include <stdexcept>
#include <string>
#include <sys/stat.h>
#include <unistd.h>

static void require_at(bool condition, int line) {
    if (!condition) throw std::runtime_error("task-directory witness failed at line " + std::to_string(line));
}
#define require(condition) require_at((condition), __LINE__)
static void remove_tree(const std::string &path) {
    struct stat info;
    if (lstat(path.c_str(), &info) != 0) return;
    if (!S_ISDIR(info.st_mode)) { unlink(path.c_str()); return; }
    DIR *directory = opendir(path.c_str());
    if (!directory) return;
    while (auto *entry = readdir(directory)) {
        if (!std::strcmp(entry->d_name, ".") || !std::strcmp(entry->d_name, "..")) continue;
        remove_tree(path + "/" + entry->d_name);
    }
    closedir(directory); rmdir(path.c_str());
}
struct Scratch {
    std::string root;
    Scratch() {
        char path[] = "/tmp/swr-corebase-task-XXXXXX";
        char *result = mkdtemp(path); require(result); root = result;
    }
    ~Scratch() { remove_tree(root); }
};
static std::string template_for(const std::string &path) {
    return std::string(path.c_str()) + "/" SW_TASK_TMP_FILE;
}
static std::string sized_path(const std::string &root, size_t length) {
    std::string path = root;
    while (path.size() < length) {
        size_t remaining = length - path.size();
        require(remaining >= 2);
        size_t count = remaining > 80 ? 79 : remaining - 1;
        if (remaining - count - 1 == 1) --count;
        path += '/' + std::string(count, 'x');
    }
    return path;
}
static bool exists_dir(const std::string &path) {
    struct stat info; return stat(path.c_str(), &info) == 0 && S_ISDIR(info.st_mode);
}
int main(int argc, char **argv) {
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    Scratch scratch;
    swoole_init();
    FILE *sink = std::tmpfile(); require(sink);
    SwooleG.logger->set_stream(sink);
    SwooleG.task_tmpfile = "original-publication";
    sw_tg_buffer()->format("original-buffer");
    bool caught = false;
    try { swoole_set_task_tmpdir(""); } catch (const std::out_of_range &) { caught = true; }
    require(caught && SwooleG.task_tmpfile == "original-publication"
            && sw_tg_buffer()->to_std_string() == "original-buffer");
    std::puts("empty:out-of-range,no-publication,no-format");
    require(!swoole_set_task_tmpdir("relative") && SwooleG.task_tmpfile == "original-publication");
    std::puts("relative:reject,old-publication");
    require(swoole_set_task_tmpdir(scratch.root) && swoole_get_task_tmpdir() == template_for(scratch.root));
    std::puts("existing:accepted,template-published");
    std::string nested = scratch.root + "/new/child";
    require(swoole_set_task_tmpdir(nested) && exists_dir(nested)
            && swoole_get_task_tmpdir() == template_for(nested));
    std::puts("missing:recursive-mkdir,template-published");
    std::string file = scratch.root + "/file";
    FILE *handle = std::fopen(file.c_str(), "wb"); require(handle); std::fclose(handle);
    require(swoole_set_task_tmpdir(file) && swoole_get_task_tmpdir() == template_for(file));
    std::puts("readable-file:accepted-without-directory-check");
    std::string prior = SwooleG.task_tmpfile;
    require(!swoole_set_task_tmpdir(file + "/child") && SwooleG.task_tmpfile == prior);
    std::puts("file-parent:reject,old-publication");
    std::string nul = scratch.root + std::string("\0ignored", 8);
    // v6.2.4 checks access() on the C-string prefix but publishes the whole string.
    require(swoole_set_task_tmpdir(nul) && swoole_get_task_tmpdir() == nul + "/" SW_TASK_TMP_FILE);
    std::puts("embedded-nul:prefix-checked,raw-string-published");
    std::string long_nul = scratch.root + std::string(1, '\0') + std::string(512, 'z');
    require(!swoole_set_task_tmpdir(long_nul) && swoole_get_task_tmpdir() == long_nul + "/" SW_TASK_TMP_FILE);
    std::puts("embedded-nul-long:raw-length-rejected,published");
    SwooleG.task_tmpfile = scratch.root;
    require(swoole_set_task_tmpdir(swoole_get_task_tmpdir())
            && swoole_get_task_tmpdir() == template_for(scratch.root));
    std::puts("getter-alias:fresh-global-length,publication");
    std::string trailing = scratch.root + "/";
    require(swoole_set_task_tmpdir(trailing) && swoole_get_task_tmpdir() == template_for(trailing));
    std::puts("trailing-slash:double-slash-preserved");
    for (size_t total : {size_t(SW_TASK_TMP_PATH_SIZE - 1), size_t(SW_TASK_TMP_PATH_SIZE)}) {
        std::string dir = sized_path(scratch.root, total - std::strlen(SW_TASK_TMP_FILE) - 1);
        require(swoole_set_task_tmpdir(dir) == (total < SW_TASK_TMP_PATH_SIZE));
        require(exists_dir(dir) && swoole_get_task_tmpdir() == template_for(dir)
                && swoole_get_task_tmpdir().size() == total);
        std::printf("length%zu:%s,created,published\n", total, total < SW_TASK_TMP_PATH_SIZE ? "accepted" : "rejected");
    }
    std::fflush(sink); std::rewind(sink);
    std::string logged; char buffer[1024]; size_t count;
    while ((count = std::fread(buffer, 1, sizeof(buffer), sink))) logged.append(buffer, count);
    if (argc == 2) {
        FILE *raw = std::fopen(argv[1], "wb"); require(raw);
        require(std::fwrite(logged.data(), 1, logged.size(), raw) == logged.size());
        require(std::fclose(raw) == 0);
    }
    // Ignore only the logger's date/process prefix. Check every complete payload,
    // including level, facade, private path, order, duplicates and extra lines.
    std::string payloads;
    for (size_t start = 0; start < logged.size();) {
        size_t end = logged.find('\n', start);
        require(end != std::string::npos && logged[start] == '[');
        size_t prefix = logged.find("]\t", start);
        require(prefix != std::string::npos && prefix < end);
        payloads.append(logged, prefix + 2, end - prefix - 1);
        start = end + 1;
    }
    require(payloads == "WARNING\tswoole_set_task_tmpdir(): wrong absolute path 'relative'\n"
            "WARNING\tswoole_mkdir_recursive(): mkdir('" + file + "/child') failed, Error: "
            + std::strerror(ENOTDIR) + "[" + std::to_string(ENOTDIR) + "]\n"
            "WARNING\tswoole_set_task_tmpdir(): create task tmp dir('" + file + "/child') failed\n"
            "WARNING\tswoole_set_task_tmpdir(): task tmp_dir is too large, the max size is '255'\n"
            "WARNING\tswoole_set_task_tmpdir(): task tmp_dir is too large, the max size is '255'\n");
    std::puts("warnings:five-exact-payloads,ordered,no-extras");
    const std::string bad_parent = file + "/child";
    const std::string too_long = sized_path(scratch.root,
        SW_TASK_TMP_PATH_SIZE - std::strlen(SW_TASK_TMP_FILE) - 1);
    for (int level : {SW_LOG_ERROR, SW_LOG_NONE}) {
        require(ftruncate(fileno(sink), 0) == 0); std::rewind(sink);
        swoole_set_log_level(level);
        SwooleG.task_tmpfile = "logging-publication";
        swoole_set_last_error(1234567); std::strcpy(sw_error, "logging-sentinel");
        errno = EDOM;
        require(!swoole_set_task_tmpdir("relative") && errno == EDOM
                && swoole_get_last_error() == 1234567 && std::string(sw_error) == "logging-sentinel"
                && SwooleG.task_tmpfile == "logging-publication");
        require(!swoole_set_task_tmpdir(bad_parent) && swoole_get_last_error() == ENOTDIR
                && SwooleG.task_tmpfile == "logging-publication");
        const std::string expected_error = level == SW_LOG_NONE ? "logging-sentinel" :
            "swoole_mkdir_recursive(): mkdir('" + bad_parent + "') failed, Error: "
                + std::strerror(ENOTDIR) + "[" + std::to_string(ENOTDIR) + "]";
        require(std::string(sw_error) == expected_error);
        errno = EDOM;
        require(!swoole_set_task_tmpdir(too_long) && errno == EDOM
                && swoole_get_last_error() == ENOTDIR && std::string(sw_error) == expected_error
                && SwooleG.task_tmpfile == template_for(too_long));
        require(std::fflush(sink) == 0 && std::ftell(sink) == 0);
        std::printf("logging-%s:no-output,relative-preserves-errno,mkdir-publishes-error,lazy-format,long-publishes\n",
                    level == SW_LOG_NONE ? "none" : "error");
    }
    swoole_clean(); std::fclose(sink);
    require(!SwooleG.init && !SwooleG.logger && !SwooleTG.buffer_stack);
    std::puts("cleanup:native-globals-cleared");
}
