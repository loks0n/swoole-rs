// Address::assign(url) behind a C entry point, once per engine: build.rs copies
// the pinned body (upstream) or the body with the clients overlay patch applied
// (candidate, which calls the Rust export) into SWR_URL_INC unchanged. The
// upstream build also wraps the pinned Set-Cookie split and DNS name decode.
#include <cstdint>
#include <cstring>
#include <locale>
#include <regex>
#include <stdexcept>
#include <string>
#include "swoole_rs_clients.h"

#define SWR_CAT2(a, b) a##_##b
#define SWR_CAT(a, b) SWR_CAT2(a, b)

namespace SWR_URL_ENGINE {
// As upstream swoole_socket.h (values are this shim's own), logging off.
enum SocketType {
    SW_SOCK_TCP = 1,
    SW_SOCK_UDP = 2,
    SW_SOCK_TCP6 = 3,
    SW_SOCK_UDP6 = 4,
    SW_SOCK_UNIX_STREAM = 5,
    SW_SOCK_UNIX_DGRAM = 6,
};
#define swoole_error_log(level, error, str, ...)
// Records what the URL assigns instead of resolving it.
struct Address {
    SocketType type{};
    std::string host;
    int port = 0;
    bool assign(SocketType _type, const std::string &_host, int _port) {
        type = _type;
        host = _host;
        port = _port;
        return true;
    }
    bool assign(const std::string &url);
};
#include SWR_URL_INC
#undef swoole_error_log
}  // namespace SWR_URL_ENGINE

#if SWR_URL_UPSTREAM
namespace upstream_clients {
#include "clients_dns.inc"
}
#endif

extern "C" {
// assign(url) over length bytes: 1 assigned, 0 rejected, -1 std::stoi threw.
// The host goes to host (length bytes) and its length to *host_length.
int SWR_CAT(swr_oracle_clients_url, SWR_URL_ENGINE)(
    const char *data, size_t length, int *type, int *port, char *host, size_t *host_length) {
    SWR_URL_ENGINE::Address address;
    bool assigned;
    try {
        assigned = address.assign(std::string(data, length));
    } catch (const std::exception &) {
        return -1;
    }
    *type = address.type;
    *port = address.port;
    *host_length = address.host.size();
    memcpy(host, address.host.data(), address.host.size());
    return assigned;
}

#if SWR_URL_UPSTREAM
// php_swoole_http_parse_set_cookies's split of length bytes into key, value offset and value.
void swr_oracle_clients_cookie(const char *at, size_t length, size_t *key, size_t *offset, size_t *value) {
    struct zval { int unused; };
#include "clients_cookie.inc"
    (void) zvalue;
    *key = key_len;
    *offset = p - at;
    *value = value_len;
}

// domain_decode in place over a NUL-terminated name.
void swr_oracle_clients_domain_decode(char *str) {
    upstream_clients::domain_decode(str);
}
#endif
}
