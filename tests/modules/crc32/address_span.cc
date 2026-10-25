// Real pinned Address methods + kernel recvfrom; every compared span initialized.
#include "swoole_socket.h"
#include "swoole_hash.h"
#include <thread>
#include <vector>
#include <string>
#include <iostream>
#include <sys/un.h>
#include <sys/wait.h>

using swoole::network::Address;
uint32_t original_crc32(const char *, size_t);
struct Result { std::string name, bytes; uint32_t crc; size_t length; };
static std::string hex(const char *p, size_t n) {
    const char *digits = "0123456789abcdef";
    std::string out;
    for (size_t i = 0; i < n; ++i) {
        const auto b = static_cast<unsigned char>(p[i]);
        out += digits[b >> 4]; out += digits[b & 15];
    }
    return out;
}
static Result capture(const char *name, const Address &address) {
    const char *bytes = address.get_addr();
    const auto expected = original_crc32(bytes, address.len);
    assert(swoole_crc32(bytes, address.len) == expected);
    return {name, hex(bytes, address.len), expected, address.len};
}
static Address ipv6(const char *text) {
    Address address{};
    address.type = SW_SOCK_UDP6;
    address.len = sizeof(address.addr.inet_v6);
    assert(inet_pton(AF_INET6, text, &address.addr.inet_v6.sin6_addr) == 1);
    return address;
}
int main(int argc, char **argv) {
    assert(argc == 2);
    std::vector<Result> rows;
    auto short_address = ipv6("::1");
    auto long_address = ipv6("ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff");
    rows.push_back(capture("ipv6-fresh", short_address));
    rows.push_back(capture("ipv6-long", long_address));
    rows.push_back(capture("ipv6-short-after-long", short_address));
    assert(rows[0].bytes != rows[2].bytes && rows[0].crc != rows[2].crc);
    Result child_thread;
    std::thread thread([&] { child_thread = capture("ipv6-fresh-thread", short_address); });
    thread.join();
    assert(child_thread.bytes == rows[0].bytes && child_thread.crc == rows[0].crc);
    rows.push_back(child_thread);
    const auto dirty = rows[2].crc;
    const auto child = fork();
    assert(child >= 0);
    if (child == 0) {
        const auto value = capture("fork", short_address);
        _exit(value.crc == dirty ? 0 : 1);
    }
    int status = -1;
    assert(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0);

    const auto server_path = std::string(argv[1]) + "/s";
    const auto client_path = std::string(argv[1]) + "/c";
    sockaddr_un server{}, client{};
    assert(server_path.size() + 1 < sizeof(server.sun_path));
    assert(client_path.size() + 1 < sizeof(client.sun_path));
    server.sun_family = client.sun_family = AF_UNIX;
    memcpy(server.sun_path, server_path.c_str(), server_path.size() + 1);
    memcpy(client.sun_path, client_path.c_str(), client_path.size() + 1);
    const auto server_length = offsetof(sockaddr_un, sun_path) + server_path.size() + 1;
    const auto client_length = offsetof(sockaddr_un, sun_path) + client_path.size() + 1;
#ifdef __APPLE__
    server.sun_len = server_length; client.sun_len = client_length;
#endif
    const int server_fd = socket(AF_UNIX, SOCK_DGRAM, 0), client_fd = socket(AF_UNIX, SOCK_DGRAM, 0);
    assert(server_fd >= 0 && client_fd >= 0);
    assert(bind(server_fd, reinterpret_cast<sockaddr *>(&server), server_length) == 0);
    assert(bind(client_fd, reinterpret_cast<sockaddr *>(&client), client_length) == 0);
    timeval timeout{2, 0};
    assert(setsockopt(server_fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) == 0);
    for (const unsigned char sentinel : {0xa5, 0x5a}) {
        Address received;
        memset(&received, sentinel, sizeof(received));
        received.type = SW_SOCK_UNIX_DGRAM;
        received.len = sizeof(received.addr);
        assert(sendto(client_fd, "x", 1, 0, reinterpret_cast<sockaddr *>(&server), server_length) == 1);
        char payload;
        assert(recvfrom(server_fd, &payload, 1, 0, &received.addr.ss, &received.len) == 1 && payload == 'x');
        // Only defined short paths: never read beyond the sun_path array.
        assert(received.len <= sizeof(received.addr.un.sun_path));
        rows.push_back(capture(sentinel == 0xa5 ? "unix-prefill-a5" : "unix-prefill-5a", received));
    }
    assert(rows[4].bytes != rows[5].bytes && rows[4].crc != rows[5].crc);
    close(server_fd); close(client_fd); unlink(server_path.c_str()); unlink(client_path.c_str());
    std::cout << "{\"passed\":true,\"fork_copy\":true,\"rows\":[";
    bool first = true;
    for (const auto &row : rows) {
        if (!first) std::cout << ',';
        first = false;
        std::cout << "{\"name\":\"" << row.name << "\",\"bytes\":\"" << row.bytes << "\",\"length\":"
                  << row.length << ",\"crc32\":" << row.crc << '}';
    }
    std::cout << "]}" << std::endl;
}
