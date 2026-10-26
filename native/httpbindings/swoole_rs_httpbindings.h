#ifndef SWOOLE_RS_HTTPBINDINGS_H
#define SWOOLE_RS_HTTPBINDINGS_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct { const uint8_t *data; size_t length; } swr_v1_httpbindings_text;
typedef struct {
    swr_v1_httpbindings_text fields[6];
    int64_t expires; uint32_t flags; double age;
} swr_v1_httpbindings_cookie_input;
typedef struct {
    uint32_t kind; swr_v1_httpbindings_text text; int64_t value;
} swr_v1_httpbindings_action;
enum {
    SWR_HTTPBINDINGS_APPEND = 1, SWR_HTTPBINDINGS_WARN = 2,
    SWR_HTTPBINDINGS_ENCODE = 3, SWR_HTTPBINDINGS_APPEND_ENCODED = 4,
    SWR_HTTPBINDINGS_FREE_ENCODED = 5, SWR_HTTPBINDINGS_FORMAT_DATE = 6,
    SWR_HTTPBINDINGS_APPEND_DATE = 7, SWR_HTTPBINDINGS_FREE_DATE = 8,
    SWR_HTTPBINDINGS_READ_AGE = 9, SWR_HTTPBINDINGS_APPEND_AGE = 10,
    SWR_HTTPBINDINGS_DONE = 11
};
int32_t swr_v1_httpbindings_cookie(const swr_v1_httpbindings_cookie_input *, uint32_t *, swr_v1_httpbindings_action *);
enum {
    SWR_HTTPBINDINGS_HEADER_APPEND = 0, SWR_HTTPBINDINGS_HEADER_COOKIE = 1,
    SWR_HTTPBINDINGS_HEADER_UPGRADE = 2, SWR_HTTPBINDINGS_HEADER_FORM = 3,
    SWR_HTTPBINDINGS_HEADER_MULTIPART = 4, SWR_HTTPBINDINGS_HEADER_COMPRESSION = 5
};
int32_t swr_v1_httpbindings_request_option(swr_v1_httpbindings_text, uint32_t);
int32_t swr_v1_httpbindings_compression(swr_v1_httpbindings_text, uint32_t);
swr_v1_httpbindings_text swr_v1_httpbindings_encoding(int32_t, uint32_t);
int32_t swr_v1_httpbindings_form_source(uint32_t);
int32_t swr_v1_httpbindings_body_prefix(swr_v1_httpbindings_text, uint32_t, size_t *);
int32_t swr_v1_httpbindings_request_header(swr_v1_httpbindings_text, swr_v1_httpbindings_text, uint32_t, uint32_t);
int32_t swr_v1_httpbindings_request_key(swr_v1_httpbindings_text);
int32_t swr_v1_httpbindings_tokens(uint8_t *, size_t, const uint8_t *, size_t, uint32_t);
typedef struct { size_t path_length, query_offset, query_length; } swr_v1_httpbindings_url;
typedef struct { size_t offset, length; } swr_v1_httpbindings_trimmed;
int32_t swr_v1_httpbindings_request_url(swr_v1_httpbindings_text, swr_v1_httpbindings_url *);
int32_t swr_v1_httpbindings_trim_quotes(uint8_t *, size_t, swr_v1_httpbindings_trimmed *);
int32_t swr_v1_httpbindings_codec(int32_t, uint32_t, uint32_t, size_t, uint32_t);
int32_t swr_v1_httpbindings_codec_level(int32_t, int32_t, int32_t, int32_t);
int32_t swr_v1_httpbindings_response_header(swr_v1_httpbindings_text);
enum {
 SWR_HTTPBINDINGS_WRITE_HTTP2=1, SWR_HTTPBINDINGS_WRITE_BUFFER,
 SWR_HTTPBINDINGS_WRITE_HEADER, SWR_HTTPBINDINGS_WRITE_READ,
 SWR_HTTPBINDINGS_WRITE_EMPTY, SWR_HTTPBINDINGS_WRITE_CHUNK,
 SWR_HTTPBINDINGS_WRITE_HEADER_FAILED
};
int32_t swr_v1_httpbindings_write(uint32_t *, uint32_t);
enum {
 SWR_HTTPBINDINGS_FILE_HTTP2=40, SWR_HTTPBINDINGS_FILE_READ_HEADERS,
 SWR_HTTPBINDINGS_FILE_MIME, SWR_HTTPBINDINGS_FILE_HEADER,
 SWR_HTTPBINDINGS_FILE_SEND, SWR_HTTPBINDINGS_FILE_HEADER_FAILED,
 SWR_HTTPBINDINGS_FILE_CLOSE_FAILED, SWR_HTTPBINDINGS_FILE_MARK_END,
 SWR_HTTPBINDINGS_FILE_CLOSE_DONE, SWR_HTTPBINDINGS_FILE_DONE
};
int32_t swr_v1_httpbindings_file(uint32_t *, uint32_t);
int32_t swr_v1_httpbindings_file_range(int64_t, int64_t, int64_t, int64_t *);
int32_t swr_v1_httpbindings_response_key(uint8_t *, size_t);
typedef struct { uint32_t entry, alias, stage; } swr_v1_httpbindings_settings_cursor;
enum {
 SWR_HTTPBINDINGS_SETTING_LOOKUP=1, SWR_HTTPBINDINGS_SETTING_COOKIE,
 SWR_HTTPBINDINGS_SETTING_POST, SWR_HTTPBINDINGS_SETTING_FILES,
 SWR_HTTPBINDINGS_SETTING_COMPRESSION, SWR_HTTPBINDINGS_SETTING_LEVEL,
 SWR_HTTPBINDINGS_SETTING_MINIMUM, SWR_HTTPBINDINGS_SETTING_TYPES,
 SWR_HTTPBINDINGS_SETTING_WEBSOCKET, SWR_HTTPBINDINGS_SETTING_UPLOAD,
 SWR_HTTPBINDINGS_SETTING_DONE
};
int32_t swr_v1_httpbindings_settings(swr_v1_httpbindings_settings_cursor *, uint32_t, uint32_t, swr_v1_httpbindings_action *);
uint32_t swr_v1_httpbindings_server_level(int64_t);
int32_t swr_v1_httpbindings_handler(swr_v1_httpbindings_text, swr_v1_httpbindings_text);
typedef struct {int32_t per_process,system,timeout,bad_ssl,canceled;} swr_v1_httpbindings_accept_errors;
int32_t swr_v1_httpbindings_accept(uint32_t,int64_t,int32_t,const swr_v1_httpbindings_accept_errors *);
#ifdef __cplusplus
}
#endif
#endif
