// Real public framing/MIME consumers. `check` never consults a clock.
#include "swoole_protocol.h"
#include "swoole_string.h"
#include "swoole_mime_type.h"
#include <chrono>
#include <iostream>
using namespace swoole;
static uint64_t packets, total;
static int package(const Protocol *, network::Socket *, const RecvData *r) {
    packets++; total += r->info.len; return 0;
}
int main(int argc, char **argv) {
    if (argc != 3) return 2;
    std::string kind = argv[1]; bool check = std::string(argv[2]) == "check";
    uint64_t loops = check ? 1 : std::stoull(argv[2]);
    if (!loops || loops > 10000000) return 3;
    swoole_init(); swoole_set_log_level(SW_LOG_ERROR);
    int64_t ns = 0;
    {
    Protocol p{}; network::Socket socket{}; String buffer(1024 * 1024);
    p.onPackage = package; p.get_package_length = Protocol::default_length_func;
    p.package_length_type = 'N'; p.package_length_size = 4; p.package_body_offset = 4;
    p.package_max_length = 1024 * 1024; p.package_eof_len = 2; memcpy(p.package_eof, "\r\n", 2);
    const char length_data[] = "\0\0\0\4test";
    const char eof_data[] = "foobar\r\n";
    std::string names[] = {"index.HTML", "a.jpg", "foo.tar.gz", "file.unknown", "filename", "/path/file.css", "movie.MP4", "data.JSON"};
    std::string large(65536, 'a');
    if (kind == "length-large") { auto length = htonl(65532); memcpy(&large[0], &length, 4); }
    else { large[65534] = '\r'; large[65535] = '\n'; }
    auto start = check ? std::chrono::steady_clock::time_point{} : std::chrono::steady_clock::now();
    for (uint64_t i = 0; i < loops; i++) {
        if (kind == "length" || kind == "length-large") {
            size_t size = kind == "length" ? 8 : large.size();
            for (int n = 0; n < 8; n++) memcpy(buffer.str + n * size, kind == "length" ? length_data : large.data(), size);
            buffer.length = 8 * size; buffer.offset = 0; socket.skip_recv = 1;
            if (p.recv_with_length_protocol(&socket, &buffer) || buffer.length || socket.recv_wait) return 4;
        } else if (kind == "eof" || kind == "eof-large") {
            size_t size = kind == "eof" ? 8 : large.size();
            for (int n = 0; n < 8; n++) memcpy(buffer.str + n * size, kind == "eof" ? eof_data : large.data(), size);
            buffer.length = 8 * size; buffer.offset = 0;
            if (p.recv_split_by_eof(&socket, &buffer) || buffer.length) return 5;
        } else if (kind == "mime") {
            for (const auto &name: names) { const auto &value = mime_type::get(name); total += value.size(); }
        } else if (kind == "unpack") {
            for (char format: std::string("cCsSnviIlLNVqQJP")) total += uint64_t(swoole_unpack(format, length_data));
        } else return 6;
    }
    if (!check) ns = std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - start).count();
    if ((kind == "length" || kind == "eof" || kind == "length-large" || kind == "eof-large") &&
        (packets != loops * 8 || total != loops * (kind.find("large") == std::string::npos ? 64 : 524288))) return 7;
    if (!total) return 8;
    }
    swoole_clean();
    std::cout << "{\"nanoseconds\":" << ns << ",\"operations\":" << loops * (kind == "unpack" ? 16 : 8) << ",\"checksum\":" << total << ",\"errors\":0}" << std::endl;
}
