// Request framing from http.cc behind C entry points, once per engine: build.rs
// copies the pinned bodies (upstream) or the bodies with the http overlay patch
// applied (candidate, which calls the Rust exports) into SWR_FRAME_INC unchanged.
// The facade gives them upstream's Request fields and String's str/length/offset.
#include <cctype>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <string>
#include <strings.h>
#include <sys/types.h>
#include "swoole_rs_http.h"

#define SWR_CAT2(a, b) a##_##b
#define SWR_CAT(a, b) SWR_CAT2(a, b)

namespace SWR_FRAME_ENGINE {
using uchar = unsigned char;
// As upstream include/swoole.h, swoole_log.h (tracing off), swoole_config.h and swoole_http2.h.
enum { SW_OK = 0, SW_ERR = -1 };
#define SW_LOOP_N(n) for (decltype(n) i = 0; i < n; i++)
#define SW_STRL(s) s, sizeof(s) - 1
#define SW_STR_ISTARTS_WITH(str, len, const_sub_str) swoole_str_istarts_with(str, len, SW_STRL(const_sub_str))
#define swoole_trace_log(what, str, ...)
#define SW_HTTP_CHUNK_EOF "0\r\n\r\n"
#define SW_HTTP2_PRI_STRING "PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n"
__attribute__((unused)) static inline unsigned int swoole_str_istarts_with(const char *pstr, size_t plen, const char *sstr, size_t slen) {
    return (plen >= slen) && (strncasecmp(pstr, sstr, slen) == 0);
}
#include "http_frame_enums.inc"
struct String {
    char *str;
    size_t length;
    off_t offset;
};
struct Request {
    uint8_t method;
    uint8_t version;
    uchar excepted : 1;
    uchar known_length : 1;
    uint32_t url_offset_;
    uint32_t url_length_;
    uint32_t request_line_length_;
    uint32_t header_length_;
    uint64_t content_length_;
    String *buffer_;
    int get_protocol();
    int get_header_length();
    int get_chunked_body_length();
    bool has_expect_header() const;
    std::string get_header(const char *name) const;
};
#include SWR_FRAME_INC
}  // namespace SWR_FRAME_ENGINE

extern "C" {
using SWR_FRAME_ENGINE::Request;
using SWR_FRAME_ENGINE::String;

// See swoole_rs_oracle::http_frame::State.
struct swr_oracle_http_request {
    size_t offset;
    uint64_t content_length;
    uint32_t method, version, excepted, known_length, url_offset, url_length, line_length, header_length;
};

// operation 0 get_protocol, 1 get_header_length, 2 get_chunked_body_length; data
// has a spare NUL after length, as a received String keeps spare capacity.
int SWR_CAT(swr_oracle_http_frame, SWR_FRAME_ENGINE)(uint32_t operation, char *data, size_t length,
                                                     swr_oracle_http_request *state) {
    String buffer{data, length, static_cast<off_t>(state->offset)};
    Request request{};
    request.method = state->method;
    request.version = state->version;
    request.excepted = state->excepted;
    request.known_length = state->known_length;
    request.url_offset_ = state->url_offset;
    request.url_length_ = state->url_length;
    request.request_line_length_ = state->line_length;
    request.header_length_ = state->header_length;
    request.content_length_ = state->content_length;
    request.buffer_ = &buffer;
    int result = operation == 0 ? request.get_protocol()
                 : operation == 1 ? request.get_header_length()
                                  : request.get_chunked_body_length();
    *state = {static_cast<size_t>(buffer.offset), request.content_length_, request.method, request.version,
              request.excepted, request.known_length, request.url_offset_, request.url_length_,
              request.request_line_length_, request.header_length_};
    return result;
}

bool SWR_CAT(swr_oracle_http_expect, SWR_FRAME_ENGINE)(char *data, size_t length) {
    String buffer{data, length, 0};
    Request request{};
    request.buffer_ = &buffer;
    return request.has_expect_header();
}

// Copies get_header(name) into output (capacity length); returns its size.
size_t SWR_CAT(swr_oracle_http_header, SWR_FRAME_ENGINE)(char *data, size_t length, uint32_t url_offset,
                                                        uint32_t url_length, uint32_t header_length,
                                                        const char *name, char *output) {
    String buffer{data, length, 0};
    Request request{};
    request.url_offset_ = url_offset;
    request.url_length_ = url_length;
    request.header_length_ = header_length;
    request.buffer_ = &buffer;
    std::string value = request.get_header(name);
    memcpy(output, value.data(), value.size());
    return value.size();
}

const char *SWR_CAT(swr_oracle_http_method, SWR_FRAME_ENGINE)(int method) {
    return SWR_FRAME_ENGINE::get_method_string(method);
}
}
