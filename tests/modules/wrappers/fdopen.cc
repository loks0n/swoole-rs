// Actual generated wrapper translation unit; only native fault boundaries vary.
#include "swoole_http.h"
#include "swoole_server.h"
#include "swoole_llhttp.h"
#include "thirdparty/multipart_parser.h"
#include "swoole_rs_wrappers.h"
#include <dlfcn.h>
#include <iostream>
#include <cstdlib>
#include <new>

static bool registration_case, success_case, write_case, partial_write, track_new;
static size_t fail_at = 1, allocation_count;
void *operator new(size_t n) {
    if (track_new && ++allocation_count == fail_at && registration_case) { errno = ENOMEM; throw std::bad_alloc(); }
    void *p = std::malloc(n ? n : 1); if (!p) throw std::bad_alloc(); return p;
}
void operator delete(void *p) noexcept { std::free(p); }
void operator delete(void *p, size_t) noexcept { std::free(p); }
static int created_fd = -1, warning_errno;
static std::string created_path;
static int capture_tmpfile(char *path) {
    created_fd = swoole_tmpfile(path);
    if (created_fd >= 0) created_path = path;
    return created_fd;
}
static FILE *instrument_fdopen(int fd, const char *mode) {
    if (!registration_case && !success_case && !write_case) { errno = EMFILE; return nullptr; }
    FILE *fp = fdopen(fd, mode); if (fp) track_new = true; return fp;
}
static size_t instrument_fwrite(const void *data, size_t size, size_t count, FILE *fp) {
    if (write_case) { errno = ENOSPC; return partial_write && count ? count - 1 : 0; }
    return fwrite(data, size, count, fp);
}
static void capture_warning(const char *, ...) { warning_errno = errno; }
#undef swoole_sys_warning
#define swoole_sys_warning(...) capture_warning(__VA_ARGS__)
#define swoole_tmpfile capture_tmpfile
#define fdopen instrument_fdopen
#define fwrite instrument_fwrite
#include "candidate-http.inc"
#undef fwrite
#undef fdopen
#undef swoole_tmpfile

int main(int argc, char **argv) {
    registration_case = argc > 1 && std::string(argv[1]) == "map-registration";
    partial_write = argc > 1 && std::string(argv[1]) == "short-write";
    write_case = partial_write || (argc > 1 && std::string(argv[1]) == "write");
    success_case = argc > 1 && std::string(argv[1]) == "success";
    if (argc > 2) fail_at = std::stoul(argv[2]);
    Dl_info library{};
    if (!dladdr(reinterpret_cast<const void *>(&swr_v1_wrappers_request_new), &library) || !library.dli_fname) return 2;
    swoole_init();
    bool fd_closed = false, unlinked = false, empty = false, allocation_thrown = false, registered = false, error_marker = false; int result = -999, allocation_errno = 0;
    {
        swoole::http_server::ContextImpl implementation;
        if (!implementation.state) return 3;
        swoole::http_server::Context context(nullptr, 0, &implementation);
        swr_v1_wrappers_disposition_begin(implementation.state);
        if (swr_v1_wrappers_parameter(implementation.state, (const uint8_t *) "filename", 8,
                                             (const uint8_t *) "x.bin", 5) ||
            swr_v1_wrappers_disposition_end(implementation.state)) return 4;
        implementation.mt_parser = multipart_parser_init("abc", 3, &swoole::http_server::mt_parser_settings);
        if (!implementation.mt_parser) return 5;
        implementation.mt_parser->data = &context;
        try { result = swoole::http_server::multipart_body_on_header_complete(implementation.mt_parser); }
        catch (const std::bad_alloc &) { allocation_thrown = true; allocation_errno = errno; }
        track_new = false;
        if (write_case && result == 0) {
            result = swoole::http_server::multipart_body_on_data(implementation.mt_parser, "abc", 3);
            error_marker = context.files.size() == 1 && context.files.begin()->second == "ERROR(1)";
        }
        empty = context.files.empty();
        registered = context.files.size() == 1 && context.files.begin()->second == created_path;
    }
    errno = 0;
    fd_closed = created_fd >= 0 && fcntl(created_fd, F_GETFD) == -1 && errno == EBADF;
    errno = 0;
    unlinked = !created_path.empty() && access(created_path.c_str(), F_OK) == -1 && errno == ENOENT;
    // A failed pre-fix witness cleans only the exact file it created, after
    // recording the failure. This is not counted as implementation cleanup.
    if (!created_path.empty() && !unlinked) unlink(created_path.c_str());
    swoole_clean();
    bool passed = fd_closed && unlinked && (write_case ? error_marker && result == 0 && !allocation_thrown && warning_errno == ENOSPC : registration_case ? empty && allocation_thrown && allocation_errno == ENOMEM : success_case ? registered && result == 0 && !allocation_thrown : empty && result == 0 && !allocation_thrown && warning_errno == EMFILE);
    std::cout << "{\"passed\":" << (passed ? "true" : "false")
              << ",\"error_marker\":" << (error_marker ? "true" : "false")
              << ",\"allocation_count\":" << allocation_count << ",\"registered\":" << (registered ? "true" : "false")
              << ",\"allocation_thrown\":" << (allocation_thrown ? "true" : "false") << ",\"allocation_errno\":" << allocation_errno
              << ",\"callback_return\":" << result << ",\"fd_closed\":" << (fd_closed ? "true" : "false")
              << ",\"temp_unlinked\":" << (unlinked ? "true" : "false")
              << ",\"files_map_empty\":" << (empty ? "true" : "false")
              << ",\"warning_errno\":" << warning_errno << ",\"expected_errno\":" << (write_case ? ENOSPC : EMFILE)
              << ",\"rust_library\":\"" << library.dli_fname << "\"}\n";
    return passed ? 0 : 1;
}
