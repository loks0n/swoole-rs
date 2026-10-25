#ifndef SWOOLE_RS_HTTP_REQUEST_V2_H
#define SWOOLE_RS_HTTP_REQUEST_V2_H
#include "swoole_rs_http.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef struct swr_v2_http_request swr_v2_http_request;
typedef struct swr_v2_http_request_text_snapshot swr_v2_http_request_text_snapshot;
typedef struct {
    uint64_t content_length;
    size_t upload_size, upload_maximum;
    uint32_t method, version, flags, url_offset, url_length, maximum, line_length,
        header_length, has_form, boundary_length;
} swr_v2_http_request_observation;
typedef struct { swr_v1_http_span boundary; uint32_t number_errors; } swr_v2_http_request_header_result;
enum swr_v2_http_request_flag {
    SWR_HTTP_REQUEST_V2_EXCEPTED=1, SWR_HTTP_REQUEST_V2_TOO_LARGE=2,
    SWR_HTTP_REQUEST_V2_UNAVAILABLE=4, SWR_HTTP_REQUEST_V2_HEADER_PARSED=8,
    SWR_HTTP_REQUEST_V2_DISPATCHED=16, SWR_HTTP_REQUEST_V2_MULTIPART_HEADER=32,
    SWR_HTTP_REQUEST_V2_KNOWN=64, SWR_HTTP_REQUEST_V2_KEEPALIVE=128,
    SWR_HTTP_REQUEST_V2_CHUNKED=256, SWR_HTTP_REQUEST_V2_NOBODY=512
};
enum swr_v2_http_request_control_kind {
    SWR_HTTP_REQUEST_V2_CLEAN=0, SWR_HTTP_REQUEST_V2_MAXIMUM=1,
    SWR_HTTP_REQUEST_V2_ADVANCE_HEADER=2, SWR_HTTP_REQUEST_V2_DISPATCH=3,
    SWR_HTTP_REQUEST_V2_DISCARD_FORM=4, SWR_HTTP_REQUEST_V2_CLEAR_EXCEPTED=5,
    SWR_HTTP_REQUEST_V2_SET_EXCEPTED=6, SWR_HTTP_REQUEST_V2_EMIT=7,
    SWR_HTTP_REQUEST_V2_RESET_UPLOAD=8, SWR_HTTP_REQUEST_V2_UPLOAD_MAXIMUM=9,
    SWR_HTTP_REQUEST_V2_ADMIT_FORM=10, SWR_HTTP_REQUEST_V2_ACTIVATE_FORM=11,
    SWR_HTTP_REQUEST_V2_DESTROY_FORM_TEXT=12
};
swr_v2_http_request *swr_v2_http_request_new(void);
void swr_v2_http_request_drop(swr_v2_http_request *);
int32_t swr_v2_http_request_observe(const swr_v2_http_request *, swr_v2_http_request_observation *);
int32_t swr_v2_http_request_control(swr_v2_http_request *, uint32_t, uint64_t, uint64_t);
const uint32_t *swr_v2_http_request_lifecycle(const swr_v2_http_request *, uint32_t, uint32_t, size_t *);
int32_t swr_v2_http_request_frame(swr_v2_http_request *, uint32_t, const uint8_t *, size_t, size_t, size_t *);
int32_t swr_v2_http_request_headers(swr_v2_http_request *, uint32_t, const uint8_t *, size_t, swr_v2_http_request_header_result *);
int32_t swr_v2_http_request_header(const swr_v2_http_request *, const uint8_t *, size_t, const uint8_t *, size_t, swr_v1_http_span *);
int32_t swr_v2_http_request_text_set(swr_v2_http_request *, uint32_t, const uint8_t *, size_t);
int32_t swr_v2_http_request_text_copy(const swr_v2_http_request *, uint32_t, uint8_t *, size_t, size_t *);
int32_t swr_v2_http_request_text_snapshot_new(const swr_v2_http_request *, uint32_t, uint8_t *, size_t, swr_v1_http_proxy_text *, swr_v2_http_request_text_snapshot **);
void swr_v2_http_request_text_snapshot_drop(swr_v2_http_request_text_snapshot *);
const uint32_t *swr_v2_http_request_upload_plan(const swr_v2_http_request *, uint32_t, uint32_t, size_t *);
int32_t swr_v2_http_request_upload_template(swr_v2_http_request *, uint8_t *, size_t);
int32_t swr_v2_http_request_data(swr_v2_http_request *, uint32_t, uint32_t, size_t, size_t, int64_t);
int32_t swr_v2_http_request_chunk(swr_v2_http_request *, uint32_t, const uint8_t *, size_t, size_t, swr_v1_http_chunk_result *);
#ifdef __cplusplus
}
#include "swoole_http.h"
namespace swoole {
struct Connection;
namespace http_server {
// Actual Native resource custody only; all logical facts/form/name/template
// bytes live in the opaque Rust owner. No legacy object, scalar or string mirror.
class RequestV2 {
    swr_v2_http_request *owner_;
    String *buffer_ = nullptr;        // Borrowed Native receive buffer, or owned body during multipart.
    String *saved_ = nullptr;         // Original borrowed Native receive buffer during multipart.
    String *upload_ = nullptr;        // Owned Native String used by external tempfile/parser effects.
    multipart_parser *parser_ = nullptr;
    const char *boundary_ = nullptr;  // Captured Native buffer backing at the original header point.
    void control(uint32_t operation, uint64_t value=0, uint64_t auxiliary=0);
    int frame(uint32_t operation);
    swr_v2_http_request_observation observe() const;
    int emit(multipart_parser *, uint32_t kind, const char *at=nullptr, size_t length=0);
    static int on_header_field(multipart_parser *, const char *, size_t);
    static int on_header_value(multipart_parser *, const char *, size_t);
    static int on_data(multipart_parser *, const char *, size_t);
    static int on_header_complete(multipart_parser *);
    static int on_data_end(multipart_parser *);
    static int on_part_begin(multipart_parser *);
    static int on_body_end(multipart_parser *);
  public:
    RequestV2();
    ~RequestV2();
    RequestV2(const RequestV2 &) = delete;
    RequestV2 &operator=(const RequestV2 &) = delete;
    String *buffer() const { return buffer_; }
    void set_buffer(String *value) { buffer_ = value; }
    uint8_t method() const { return static_cast<uint8_t>(observe().method); }
    uint32_t url_offset() const { return observe().url_offset; }
    uint32_t url_length() const { return observe().url_length; }
    uint32_t header_length() const { return observe().header_length; }
    uint32_t max_length() const { return observe().maximum; }
    uint64_t content_length() const { return observe().content_length; }
    bool has_form() const { return observe().has_form != 0; }
    bool flag(uint32_t value) const { return (observe().flags & value) != 0; }
    bool excepted() const { return flag(SWR_HTTP_REQUEST_V2_EXCEPTED); }
    bool too_large() const { return flag(SWR_HTTP_REQUEST_V2_TOO_LARGE); }
    bool unavailable() const { return flag(SWR_HTTP_REQUEST_V2_UNAVAILABLE); }
    bool header_parsed() const { return flag(SWR_HTTP_REQUEST_V2_HEADER_PARSED); }
    bool tried_to_dispatch() const { return flag(SWR_HTTP_REQUEST_V2_DISPATCHED); }
    bool multipart_header_parsed() const { return flag(SWR_HTTP_REQUEST_V2_MULTIPART_HEADER); }
    bool known_length() const { return flag(SWR_HTTP_REQUEST_V2_KNOWN); }
    bool keep_alive() const { return flag(SWR_HTTP_REQUEST_V2_KEEPALIVE); }
    bool chunked() const { return flag(SWR_HTTP_REQUEST_V2_CHUNKED); }
    bool nobody_chunked() const { return flag(SWR_HTTP_REQUEST_V2_NOBODY); }
    void set_max_length(uint32_t value) { control(SWR_HTTP_REQUEST_V2_MAXIMUM,value); }
    void advance_header_length(uint32_t value) { control(SWR_HTTP_REQUEST_V2_ADVANCE_HEADER,value); }
    void mark_dispatched() { control(SWR_HTTP_REQUEST_V2_DISPATCH); }
    void discard_form() { control(SWR_HTTP_REQUEST_V2_DESTROY_FORM_TEXT); control(SWR_HTTP_REQUEST_V2_DISCARD_FORM); }
    void clean() { control(SWR_HTTP_REQUEST_V2_CLEAN); }
    int get_protocol();
    int get_header_length();
    int get_chunked_body_length();
    void parse_header_info();
    bool parse_multipart_data(String *);
    bool init_multipart_parser(const Server *);
    void destroy_multipart_parser();
    std::string get_header(const char *name) const;
    bool has_expect_header() const;
};
}
}
#endif
#endif
