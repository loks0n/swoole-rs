#ifndef SWOOLE_RS_HTTP_H
#define SWOOLE_RS_HTTP_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct { size_t offset, length; } swr_v1_http_span;

enum swr_v1_http_request_action {
    SWR_HTTP_REQUEST_DONE=0, SWR_HTTP_REQUEST_MAKE_PARSER=1, SWR_HTTP_REQUEST_SET_DATA=2,
    SWR_HTTP_REQUEST_NEW_BODY=3, SWR_HTTP_REQUEST_APPEND_BODY=4, SWR_HTTP_REQUEST_SAVE_BUFFER=5,
    SWR_HTTP_REQUEST_TRIM_BUFFER=6, SWR_HTTP_REQUEST_USE_BODY=7, SWR_HTTP_REQUEST_TMP_NAME=8,
    SWR_HTTP_REQUEST_NEW_UPLOAD=9, SWR_HTTP_REQUEST_UPLOAD_MAX=10, SWR_HTTP_REQUEST_TRUE=11,
    SWR_HTTP_REQUEST_WARN=12, SWR_HTTP_REQUEST_FALSE=13, SWR_HTTP_REQUEST_DELETE_BODY=14,
    SWR_HTTP_REQUEST_RESTORE_BUFFER=15, SWR_HTTP_REQUEST_CLEAR_SAVED=16, SWR_HTTP_REQUEST_OBSERVE_FILE=17,
    SWR_HTTP_REQUEST_CLOSE=18, SWR_HTTP_REQUEST_UNLINK=19, SWR_HTTP_REQUEST_FREE_PARSER=20,
    SWR_HTTP_REQUEST_NULL_PARSER=21, SWR_HTTP_REQUEST_DELETE_UPLOAD=22, SWR_HTTP_REQUEST_NULL_UPLOAD=23,
    SWR_HTTP_REQUEST_DELETE_FORM=24, SWR_HTTP_REQUEST_NULL_FORM=25, SWR_HTTP_REQUEST_DESTROY=26
};
const uint32_t *swr_v1_http_request_lifecycle(uint32_t, uint32_t, size_t *);
const uint32_t *swr_v2_http_multipart_upload(uint32_t, uint32_t, const uint8_t *, size_t, size_t *);


typedef struct swr_v2_http_tasks swr_v2_http_tasks;
typedef struct { int64_t offset; size_t length; char part_header[256]; } swr_v2_http_static_task;
swr_v2_http_tasks *swr_v2_http_tasks_new(void);
void swr_v2_http_tasks_drop(swr_v2_http_tasks *);
int32_t swr_v2_http_tasks_begin(swr_v2_http_tasks *);
int32_t swr_v2_http_tasks_push(swr_v2_http_tasks *);
size_t swr_v2_http_tasks_count(const swr_v2_http_tasks *);
int32_t swr_v2_http_tasks_copy(const swr_v2_http_tasks *, size_t, swr_v2_http_static_task *);
int32_t swr_v2_http_tasks_clear(swr_v2_http_tasks *);
int32_t swr_v2_http_tasks_snapshot(const swr_v2_http_tasks *, swr_v2_http_static_task *, size_t, size_t *);

typedef struct swr_v2_http_directory swr_v2_http_directory;
swr_v2_http_directory *swr_v2_http_directory_new(void);
void swr_v2_http_directory_drop(swr_v2_http_directory *);
int32_t swr_v2_http_directory_clone(const swr_v2_http_directory *, swr_v2_http_directory **);
int32_t swr_v2_http_directory_scan_append(swr_v2_http_directory *, const uint8_t *, size_t);
void swr_v2_http_directory_scan_finish(swr_v2_http_directory *);
int32_t swr_v2_http_directory_insert(swr_v2_http_directory *, const uint8_t *, size_t);
size_t swr_v2_http_directory_count(const swr_v2_http_directory *);
int32_t swr_v2_http_directory_contains(const swr_v2_http_directory *, const uint8_t *, size_t);

typedef struct { size_t cursor, total; uint32_t started, done; } swr_v1_http_range_state;
typedef struct {
    const uint8_t *data; size_t length;
} swr_v1_http_range_text;
typedef struct {
    swr_v1_http_range_text boundary, mime;
    size_t offset, length, filesize; uint32_t part, separator;
} swr_v1_http_range_format_input;
typedef struct {
    size_t content_length, last_length, task_count, filesize, end_length;
    uint32_t phase; int32_t status; uint32_t if_range, modified;
} swr_v1_http_range_finish_state;
int32_t swr_v1_http_range_format(const swr_v1_http_range_format_input *, uint8_t *, size_t, size_t *);
int32_t swr_v2_http_tasks_prepare(swr_v2_http_tasks *, int64_t, size_t, const swr_v1_http_range_format_input *, size_t *);
int32_t swr_v1_http_range_finish(swr_v1_http_range_finish_state *);
int32_t swr_v1_http_range_next(const uint8_t *, size_t, size_t, swr_v1_http_range_state *, swr_v1_http_span *);
typedef struct {
    size_t offset; uint64_t content_length;
    uint32_t method, version, excepted, url_offset, url_length, line_length, header_length, known_length;
} swr_v1_http_frame_state;
typedef struct { size_t line_offset, line_length, chunk_length, next; uint64_t body_length; } swr_v1_http_chunk_result;
int32_t swr_v1_http_chunk_step(const uint8_t *, size_t, size_t, size_t, uint32_t, swr_v1_http_chunk_result *);
int32_t swr_v1_http_frame(const uint8_t *, size_t, swr_v1_http_frame_state *, uint32_t);
int32_t swr_v1_http_expect(const uint8_t *, size_t);
int32_t swr_v1_http_header_value(const uint8_t *, size_t, size_t, size_t, const uint8_t *, size_t, swr_v1_http_span *);
typedef struct {
    uint32_t phase, has_file, flags;
    size_t buffer_length, maximum, upload_size, upload_maximum, length;
    int64_t written;
} swr_v1_http_multipart_data_state;
int32_t swr_v1_http_multipart_data(swr_v1_http_multipart_data_state *);
int32_t swr_v1_http_multipart_result(int64_t, size_t, uint32_t);
int32_t swr_v1_http_multipart_disposition(const uint8_t *, size_t);
int32_t swr_v1_http_multipart_filename(uint8_t *, size_t);
typedef struct { size_t cursor; uint64_t content_length; uint32_t flags, number_errors; } swr_v1_http_header_state;
typedef struct { size_t key_offset, key_length, value_offset, value_length; uint32_t has_value; } swr_v1_http_cookie;
int32_t swr_v1_http_header_info(const uint8_t *, size_t, size_t, swr_v1_http_header_state *, swr_v1_http_span *);
int32_t swr_v1_http_cookie_next(uint8_t *, size_t, size_t *, swr_v1_http_cookie *);
// Invocation-local Rust policy state; no resource owner or pointer is retained.
typedef struct { uint32_t phase, source_inside; size_t source_offset, required, cursor; swr_v1_http_cookie cookie; } swr_v2_http_cookie_flow_state;
int32_t swr_v2_http_cookie_flow(swr_v2_http_cookie_flow_state *, const uint8_t *, size_t, uint8_t *, size_t, uint32_t, uint32_t);
typedef struct { const uint8_t *data; size_t length; } swr_v1_http_proxy_text;
typedef struct { uint32_t phase; size_t index, count; } swr_v2_http_rewrite_state;
int32_t swr_v2_http_rewrite_step(swr_v2_http_rewrite_state *, size_t, uint32_t, const swr_v1_http_proxy_text *, const swr_v1_http_proxy_text *, size_t *);
typedef struct {
    swr_v1_http_proxy_text url, pattern, replacement;
} swr_v1_http_rewrite_input;
int32_t swr_v1_http_rewrite_rule(const uint8_t *, size_t, swr_v1_http_span *, uint32_t *);
int32_t swr_v1_http_rewrite_literal(const swr_v1_http_rewrite_input *, uint8_t *, size_t, size_t *);
typedef struct {
    swr_v1_http_proxy_text target, host, version, authorization;
    int32_t port; uint32_t authenticated;
} swr_v1_http_proxy_request;
typedef struct {
    swr_v1_http_proxy_text status, date, modified, content_type, software, page;
    int64_t content_length, range_offset; size_t range_length, filesize;
    uint32_t variant, keep_alive, range_kind;
} swr_v1_http_static_header;
/* Static response selection scratch; values are copied only at their phase.
 * No native owner/borrow/callback enters Rust. See contract.md for effect order. */
typedef struct { uint32_t phase, head, range_kind; } swr_v1_http_static_selection;
enum swr_v1_http_static_select_action {
    SWR_HTTP_SELECT_SKIP=0, SWR_HTTP_SELECT_STATUS=1, SWR_HTTP_SELECT_NOT_FOUND=2,
    SWR_HTTP_SELECT_DATES=3, SWR_HTTP_SELECT_CHECK_MODIFIED=4, SWR_HTTP_SELECT_NOT_MODIFIED=5,
    SWR_HTTP_SELECT_INDEX=6, SWR_HTTP_SELECT_INSPECT_INDEX=7, SWR_HTTP_SELECT_AUTOINDEX=8,
    SWR_HTTP_SELECT_FILE=9, SWR_HTTP_SELECT_FILE_HEADER=10, SWR_HTTP_SELECT_READY=11
};
int32_t swr_v1_http_static_select(swr_v1_http_static_selection *, size_t, int32_t);
enum swr_v1_http_static_body_action {
    SWR_HTTP_BODY_DONE=0, SWR_HTTP_BODY_ALLOCATE=1, SWR_HTTP_BODY_PART_HEADER=2,
    SWR_HTTP_BODY_FILE=3, SWR_HTTP_BODY_END_PART=4, SWR_HTTP_BODY_FREE=5,
    SWR_HTTP_BODY_KEEP_ALIVE=6, SWR_HTTP_BODY_CLOSE=7
};
typedef struct { size_t count, cursor; uint32_t phase, head; } swr_v1_http_static_body_state;
int32_t swr_v1_http_static_body(swr_v1_http_static_body_state *, size_t, uint32_t);
enum swr_v1_http_date_action {
    SWR_HTTP_DATE_IGNORE=0, SWR_HTTP_DATE_GMT=1, SWR_HTTP_DATE_UTC=2,
    SWR_HTTP_DATE_RFC850=3, SWR_HTTP_DATE_ASCTIME=4, SWR_HTTP_DATE_FILE_GMT=5,
    SWR_HTTP_DATE_PARSED_TIME=6, SWR_HTTP_DATE_FILE_TIME=7, SWR_HTTP_DATE_MATCH=8
};
typedef struct {
    uint32_t phase, kind, valid; size_t length;
    int64_t timezone, file_mtime, value, parsed_time;
} swr_v1_http_conditional_state;
const char *swr_v1_http_date_format(uint32_t);
int32_t swr_v1_http_conditional(swr_v1_http_conditional_state *);
enum swr_v1_http_path_action {
    SWR_HTTP_PATH_SKIP=0, SWR_HTTP_PATH_SERVE=1, SWR_HTTP_PATH_LOCATIONS=2,
    SWR_HTTP_PATH_DIRECTORY=3, SWR_HTTP_PATH_STAT=4, SWR_HTTP_PATH_CANONICAL=5,
    SWR_HTTP_PATH_MIME=6, SWR_HTTP_PATH_ERROR=7
};
enum swr_v1_http_path_fact {
    SWR_HTTP_PATH_HAS_LOCATIONS=1, SWR_HTTP_PATH_STAT_OK=2, SWR_HTTP_PATH_CANONICAL_OK=4,
    SWR_HTTP_PATH_LINK=8, SWR_HTTP_PATH_IS_DIRECTORY=16, SWR_HTTP_PATH_FILE=32,
    SWR_HTTP_PATH_INDEX=64, SWR_HTTP_PATH_AUTOINDEX=128, SWR_HTTP_PATH_MIME_OK=256
};
typedef struct {
    swr_v1_http_proxy_text path, entry, css, powered;
    uint32_t part;
} swr_v1_http_index_page_input;
int32_t swr_v1_http_index_page(const swr_v1_http_index_page_input *, uint8_t *, size_t, size_t *);
int32_t swr_v2_http_directory_page(const swr_v2_http_directory *, size_t, const swr_v1_http_index_page_input *, uint8_t *, size_t, size_t *);

typedef struct { uint32_t phase, last; size_t url_length, filename_length; } swr_v1_http_static_path_state;
int32_t swr_v1_http_static_index_path(uint8_t *, size_t, size_t, const uint8_t *, size_t);
int32_t swr_v1_http_static_location(const uint8_t *, size_t, const uint8_t *, size_t, swr_v1_http_static_path_state *);
int32_t swr_v1_http_static_path(const uint8_t *, size_t, const uint8_t *, size_t, uint8_t *, size_t, swr_v1_http_static_path_state *, uint32_t);
typedef struct {
    uint32_t action, effects;
    const uint8_t *data;
    size_t length;
} swr_v1_http_multipart_action;
const swr_v1_http_multipart_action *swr_v1_http_multipart_emit(uint32_t, uint32_t, size_t *);
size_t swr_v1_http_multipart_body_length(size_t, size_t);
int32_t swr_v1_http_transport_route(uint32_t, uint32_t);
int32_t swr_v1_http_proxy_auth_enabled(size_t, size_t);
int32_t swr_v1_http_index_file(uint32_t *, uint32_t);
int32_t swr_v1_http_unknown_status(int32_t, uint8_t *, size_t, size_t *);
const uint8_t *swr_v1_http_static_boundary(size_t, size_t *);
const uint8_t *swr_v1_http_static_content_prefix(size_t);
int32_t swr_v1_http_static_content_type(const swr_v1_http_proxy_text *, uint8_t *, size_t, size_t *);
int32_t swr_v1_http_static_path_check(const uint8_t *, size_t, const uint8_t *, size_t, uint32_t);
int32_t swr_v1_http_static_catch(uint32_t, int32_t *);
int32_t swr_v1_http_static_headers(const swr_v1_http_static_header *, uint8_t *, size_t, size_t *);
int32_t swr_v2_http_proxy_authorization(const swr_v1_http_proxy_text *, uint8_t *, size_t *);
int32_t swr_v1_http_proxy_credentials(const swr_v1_http_proxy_text *, uint8_t *, size_t *);
int32_t swr_v1_http_proxy_pack(const swr_v1_http_proxy_request *, uint8_t *, size_t, size_t *);
int32_t swr_v1_http_proxy_handshake(const uint8_t *, size_t);
const char *swr_v1_http_status(int32_t);
const char *swr_v2_http_status_message(int32_t);
int32_t swr_v1_http_method(const uint8_t *, size_t);
const char *swr_v1_http_method_string(int32_t);
int32_t swr_v1_http_url_capacity(const uint8_t *, size_t, size_t *);
int32_t swr_v1_http_url_encode(const uint8_t *, size_t, uint8_t *, size_t, size_t *);
int32_t swr_v1_http_url_decode(uint8_t *, size_t, size_t *);
int32_t swr_v1_http_boundary(const uint8_t *, size_t, size_t, swr_v1_http_span *);
#ifdef __cplusplus
}
#endif
#endif
