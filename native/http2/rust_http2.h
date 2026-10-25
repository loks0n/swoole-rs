#pragma once
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
#include <cctype>
#include <new>
#endif

#ifndef SW_USE_RUST_HTTP2
#error "HTTP2 Rust callers require SW_USE_RUST_HTTP2"
#endif

#ifdef __cplusplus
extern "C" {
#endif
struct SwRsHttp2ReceiveFacts {
    size_t length, buffered_length;
    uint32_t maximum, ended, end_stream, parse_body, form, multipart;
};
enum SwRsHttp2ReceiveAction {
    SW_RS_HTTP2_RECV_START, SW_RS_HTTP2_RECV_CONTEXT, SW_RS_HTTP2_RECV_BUFFER,
    SW_RS_HTTP2_RECV_RESET, SW_RS_HTTP2_RECV_REMOVE, SW_RS_HTTP2_RECV_APPEND,
    SW_RS_HTTP2_RECV_FLOW, SW_RS_HTTP2_RECV_LENGTH, SW_RS_HTTP2_RECV_END_BUFFER,
    SW_RS_HTTP2_RECV_FORM, SW_RS_HTTP2_RECV_MULTIPART, SW_RS_HTTP2_RECV_HANDLE,
    SW_RS_HTTP2_RECV_WARN, SW_RS_HTTP2_RECV_ERROR, SW_RS_HTTP2_RECV_DONE
};
uint32_t sw_rs_http2_receive_next(uint32_t, uint32_t, const struct SwRsHttp2ReceiveFacts *);
enum SwRsHttp2FileMode { SW_RS_HTTP2_FILE_EMPTY, SW_RS_HTTP2_FILE_MULTI,
    SW_RS_HTTP2_FILE_SINGLE, SW_RS_HTTP2_FILE_SKIP };
enum SwRsHttp2FileCompletion { SW_RS_HTTP2_FILE_TRAILER, SW_RS_HTTP2_FILE_CLOSE, SW_RS_HTTP2_FILE_REMOVE };
size_t sw_rs_http2_file_length(size_t, size_t);
uint32_t sw_rs_http2_file_mode(size_t, size_t);
uint32_t sw_rs_http2_file_complete(uint32_t, uint32_t);
enum SwRsHttp2DecompressAction { SW_RS_HTTP2_DECOMPRESS_ERROR, SW_RS_HTTP2_DECOMPRESS_DONE,
    SW_RS_HTTP2_DECOMPRESS_CONTINUE, SW_RS_HTTP2_DECOMPRESS_EXTEND };
struct SwRsHttp2DecompressPlan { uint32_t publish_length, action; };
void sw_rs_http2_decompress_plan(uint32_t, int32_t, size_t, size_t, uint32_t, struct SwRsHttp2DecompressPlan *);
enum SwRsHttp2ConnectionAction {
    SW_RS_HTTP2_CONN_START, SW_RS_HTTP2_CONN_CREATE, SW_RS_HTTP2_CONN_SETUP,
    SW_RS_HTTP2_CONN_SSL, SW_RS_HTTP2_CONN_PROTOCOL, SW_RS_HTTP2_CONN_CONNECT,
    SW_RS_HTTP2_CONN_RESET, SW_RS_HTTP2_CONN_INFLATE, SW_RS_HTTP2_CONN_DEFLATE,
    SW_RS_HTTP2_CONN_PREFACE, SW_RS_HTTP2_CONN_SETTINGS, SW_RS_HTTP2_CONN_PUBLISH,
    SW_RS_HTTP2_CONN_IO_ERROR, SW_RS_HTTP2_CONN_INFLATE_ERROR, SW_RS_HTTP2_CONN_DEFLATE_ERROR,
    SW_RS_HTTP2_CONN_CLOSE, SW_RS_HTTP2_CONN_ALREADY, SW_RS_HTTP2_CONN_CREATE_ERROR,
    SW_RS_HTTP2_CONN_FALSE, SW_RS_HTTP2_CONN_TRUE, SW_RS_HTTP2_CONN_CLOSE_START,
    SW_RS_HTTP2_CONN_DISCONNECT, SW_RS_HTTP2_CONN_NO_SOCKET, SW_RS_HTTP2_CONN_CLOSE_SOCKET,
    SW_RS_HTTP2_CONN_CLOSE_ERROR
};
uint32_t sw_rs_http2_connection_next(uint32_t, uint32_t, uint32_t);
void *sw_rs_http2_send_queue_new(void);
void sw_rs_http2_send_queue_delete(void *);
size_t sw_rs_http2_send_queue_len(const void *);
void *sw_rs_http2_send_queue_front(const void *);
uint32_t sw_rs_http2_send_queue_push(void *, void *);
void sw_rs_http2_send_queue_pop(void *);
struct SwRsHttp2Window { uint32_t value, increment; };
void sw_rs_http2_window_plan(uint32_t, size_t, uint32_t, uint32_t, struct SwRsHttp2Window *);
uint32_t sw_rs_http2_data_rejected(size_t, size_t, uint32_t, uint32_t);
enum SwRsHttp2FrameAction {
    SW_RS_HTTP2_SETTINGS, SW_RS_HTTP2_HEADERS, SW_RS_HTTP2_DATA, SW_RS_HTTP2_PING_REPLY,
    SW_RS_HTTP2_WINDOW_UPDATE, SW_RS_HTTP2_RESET, SW_RS_HTTP2_GOAWAY, SW_RS_HTTP2_OTHER,
    SW_RS_HTTP2_SETTINGS_ACK, SW_RS_HTTP2_PING_ACK, SW_RS_HTTP2_IGNORE_PUSH
};
enum SwRsHttp2QueueAction { SW_RS_HTTP2_QUEUE_DIRECT, SW_RS_HTTP2_QUEUE_APPEND, SW_RS_HTTP2_QUEUE_REJECT };
uint32_t sw_rs_http2_queue_action(uint32_t, size_t, uint32_t);
uint32_t sw_rs_http2_send_complete(intptr_t, size_t);
enum SwRsHttp2HeaderRole {
    SW_RS_HTTP2_REQUEST_HEADERS, SW_RS_HTTP2_RESPONSE_HEADERS,
    SW_RS_HTTP2_SERVER_HEADERS, SW_RS_HTTP2_CLIENT_HEADERS
};
enum SwRsHttp2HeaderKind {
    SW_RS_HTTP2_HEADER_OTHER, SW_RS_HTTP2_HEADER_METHOD, SW_RS_HTTP2_HEADER_PATH,
    SW_RS_HTTP2_HEADER_AUTHORITY, SW_RS_HTTP2_HEADER_CONTENT_TYPE, SW_RS_HTTP2_HEADER_COOKIE,
    SW_RS_HTTP2_HEADER_CONTENT_LENGTH, SW_RS_HTTP2_HEADER_ACCEPT_ENCODING, SW_RS_HTTP2_HEADER_STATUS,
    SW_RS_HTTP2_HEADER_CONTENT_ENCODING, SW_RS_HTTP2_HEADER_SET_COOKIE, SW_RS_HTTP2_HEADER_SERVER,
    SW_RS_HTTP2_HEADER_DATE, SW_RS_HTTP2_HEADER_HOST
};
enum SwRsHttp2MediaKind { SW_RS_HTTP2_MEDIA_OTHER, SW_RS_HTTP2_MEDIA_URLENCODED, SW_RS_HTTP2_MEDIA_MULTIPART, SW_RS_HTTP2_MEDIA_GZIP };
struct SwRsHttp2Settings {
    uint32_t header_table_size, enable_push, max_concurrent_streams;
    uint32_t init_window_size, max_frame_size, max_header_list_size;
};
struct SwRsHttp2Frame {
    uint32_t length, kind, flags, stream_id, publish_last_id, action;
};
struct SwRsHttp2SettingPlan { int32_t field; uint32_t set_value, set_window, change_deflater; };
struct SwRsHttp2Chunk { size_t length; uint32_t flags; };
struct SwRsHttp2Response { uint32_t end, ready; };
struct SwRsHttp2InflateStep { uint32_t end_headers, finish; };
void sw_rs_http2_inflate_step(uint32_t, size_t, uint32_t, struct SwRsHttp2InflateStep *);
enum SwRsHttp2RespondAction {
    SW_RS_HTTP2_RESP_START, SW_RS_HTTP2_RESP_HEADER, SW_RS_HTTP2_RESP_COMMIT_END,
    SW_RS_HTTP2_RESP_EMPTY, SW_RS_HTTP2_RESP_BODY, SW_RS_HTTP2_RESP_TRAILER,
    SW_RS_HTTP2_RESP_ERROR_CLOSE, SW_RS_HTTP2_RESP_REMOVE,
    SW_RS_HTTP2_RESP_ERROR_SHUTDOWN, SW_RS_HTTP2_RESP_SUCCESS_SHUTDOWN,
    SW_RS_HTTP2_RESP_FALSE, SW_RS_HTTP2_RESP_TRUE
};
struct SwRsHttp2RespondFacts {
    uint32_t header_sent, trailer_present, chunked, shutting_down, streams_empty;
    size_t body_length;
};
uint32_t sw_rs_http2_respond_next(uint32_t, uint32_t, const struct SwRsHttp2RespondFacts *);
struct SwRsHttp2HeaderPlan { uint32_t kind, publish_flags, suppress, capture_content_type; };
void sw_rs_http2_header_plan(uint32_t, const uint8_t *, size_t, size_t, uint32_t, struct SwRsHttp2HeaderPlan *);
uint32_t sw_rs_http2_header_defaults(uint32_t);
int32_t sw_rs_http2_response_status(int32_t);
uint32_t sw_rs_http2_content_length_rejected(uint32_t, int64_t, uint32_t);
uint32_t sw_rs_http2_media_kind(const uint8_t *, size_t);
void sw_rs_http2_pack_frame_header(uint8_t *, uint32_t, uint32_t, uint32_t, uint32_t);
uint32_t sw_rs_http2_read_u32(const uint8_t *);
void sw_rs_http2_write_u32(uint8_t *, uint32_t);
int32_t sw_rs_http2_setting_index(uint32_t id);
size_t sw_rs_http2_pack_settings(uint8_t *, size_t, const struct SwRsHttp2Settings *, uint32_t);
void sw_rs_http2_unpack_setting(const uint8_t *, uint16_t *, uint32_t *);
int32_t sw_rs_http2_decode_frame(const uint8_t *, size_t, uint32_t, uint32_t, struct SwRsHttp2Frame *);
intptr_t sw_rs_http2_frame_length(const uint8_t *, size_t);
void sw_rs_http2_setting_plan(uint32_t, uint32_t, uint32_t, uint32_t, uint32_t, struct SwRsHttp2SettingPlan *);
void sw_rs_http2_chunk(size_t, uint32_t, uint32_t, struct SwRsHttp2Chunk *);
uint32_t sw_rs_http2_window_action(size_t, uint32_t, uint32_t);
uint32_t sw_rs_http2_stream_flags(uint32_t, uint32_t);
uint32_t sw_rs_http2_headers_flags(uint32_t, uint32_t, uint32_t);
uint32_t sw_rs_http2_request_value_default(uint32_t, size_t);
uint32_t sw_rs_http2_authority_with_port(uint32_t, int32_t);
uint32_t sw_rs_http2_write_allowed(uint32_t, uint32_t);
uint32_t sw_rs_http2_stream_update(uint32_t, uint32_t, uint32_t);
void sw_rs_http2_response(uint32_t, uint32_t, uint32_t, uint32_t, struct SwRsHttp2Response *);
const char *sw_rs_http2_type_name(int32_t);
uint32_t sw_rs_http2_color_group(int32_t);
#ifdef __cplusplus
}

namespace swoole { namespace http2 {
// Translation executes natively, only after the fallible Rust call has returned.
static inline bool rust_send_queue_allocated(bool allocated) {
    if (allocated) { return true; }
    auto handler = std::get_new_handler();
    if (!handler) { throw std::bad_alloc(); }
    handler();  // Native retry/exception/bailout; the Rust allocation query has returned.
    return false;
}
template<class Payload> class RustSendQueue {
    void *handle_;
  public:
    RustSendQueue() : handle_(nullptr) {
        while (!rust_send_queue_allocated((handle_ = sw_rs_http2_send_queue_new()) != nullptr)) {}
    }
    ~RustSendQueue() { sw_rs_http2_send_queue_delete(handle_); }
    RustSendQueue(const RustSendQueue &) = delete;
    RustSendQueue &operator=(const RustSendQueue &) = delete;
    size_t size() const { return sw_rs_http2_send_queue_len(handle_); }
    // Zend allocation returns non-NULL or bails out; no borrowed Rust reference escapes.
    Payload *front_or_null() const { return static_cast<Payload *>(sw_rs_http2_send_queue_front(handle_)); }
    // Non-NULL payload remains native-owned and valid through send/suspend/reentry uses.
    void push(Payload *payload) {
        while (!rust_send_queue_allocated(sw_rs_http2_send_queue_push(handle_, payload))) {}
    }
    void pop() { sw_rs_http2_send_queue_pop(handle_); }
};
static inline SwRsHttp2Window rust_window_debit(uint32_t current, size_t amount, uint32_t initial) {
    SwRsHttp2Window plan;
    sw_rs_http2_window_plan(current, amount, initial, 0, &plan);
    return plan;
}
static inline uint32_t rust_window_credit(uint32_t current, uint32_t amount) {
    SwRsHttp2Window plan;
    sw_rs_http2_window_plan(current, amount, 0, 1, &plan);
    return plan.value;
}
// Native locale semantics are copied facts; byte classification and effect policy live in Rust.
static inline size_t rust_fold_header(const char *bytes, size_t length, uint8_t (&folded)[33]) {
    size_t n = length < sizeof(folded) ? length : sizeof(folded);
    for (size_t i = 0; i < n; ++i) { folded[i] = std::tolower((unsigned char) bytes[i]); }
    return n;
}
static inline SwRsHttp2HeaderPlan rust_header_plan(SwRsHttp2HeaderRole role, const char *name, size_t length, bool can_capture = false) {
    uint8_t folded[33];
    auto n = rust_fold_header(name, length, folded);
    SwRsHttp2HeaderPlan plan;
    sw_rs_http2_header_plan(role, folded, n, length, can_capture, &plan);
    return plan;
}
static inline uint32_t rust_header_kind(SwRsHttp2HeaderRole role, const char *name, size_t length) {
    return rust_header_plan(role, name, length).kind;
}
static inline uint32_t rust_media_kind(const char *value, size_t length) {
    uint8_t folded[33];
    auto n = rust_fold_header(value, length, folded);
    return sw_rs_http2_media_kind(folded, n);
}
static inline void rust_frame_header(char *out, uint8_t type, uint32_t length, uint8_t flags, uint32_t stream_id) {
    sw_rs_http2_pack_frame_header((uint8_t *) out, type, length, flags, stream_id);
}
// One native store; member selection is a mechanical adapter, never a shadow settings object.
static inline uint32_t &rust_setting_field(Settings &settings, int32_t index) {
    static uint32_t Settings::*const fields[] = {
        &Settings::header_table_size, &Settings::enable_push, &Settings::max_concurrent_streams,
        &Settings::init_window_size, &Settings::max_frame_size, &Settings::max_header_list_size
    };
    return settings.*fields[index];
}
} }
#endif
