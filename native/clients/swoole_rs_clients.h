/* SPDX-License-Identifier: Apache-2.0 */
#ifndef SWOOLE_RS_CLIENTS_H
#define SWOOLE_RS_CLIENTS_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
enum swr_v1_clients_object_action {
    SWR_CLIENTS_OBJECT_RETURN=0, SWR_CLIENTS_OBJECT_FD_STREAM=1,
    SWR_CLIENTS_OBJECT_FD_DGRAM=2, SWR_CLIENTS_OBJECT_MAKE=3,
    SWR_CLIENTS_OBJECT_INITIALIZE=4, SWR_CLIENTS_OBJECT_WARN=5,
    SWR_CLIENTS_OBJECT_STREAM=6, SWR_CLIENTS_OBJECT_DGRAM=7,
    SWR_CLIENTS_OBJECT_ASYNC=8, SWR_CLIENTS_OBJECT_SYNC=9,
    SWR_CLIENTS_OBJECT_DOMAIN=10, SWR_CLIENTS_OBJECT_PROTOCOL=11,
    SWR_CLIENTS_OBJECT_ASSERT=12, SWR_CLIENTS_OBJECT_CLOSE=13,
    SWR_CLIENTS_OBJECT_BUFFER=14, SWR_CLIENTS_OBJECT_ASYNC_FREE=15,
    SWR_CLIENTS_OBJECT_ADVANCE=16, SWR_CLIENTS_OBJECT_SYNC_DELETE=17
};
struct swr_v1_clients_object_plan { uint32_t action, stage; };
struct swr_v1_clients_object_plan swr_v1_clients_object_next(uint32_t operation, uint32_t stage, uint8_t fact);
struct swr_v1_clients_ip_plan { uint8_t bytes[16]; uint32_t length; };
struct swr_v1_clients_ip_plan swr_v1_clients_ip(uint8_t version, const uint8_t *data, size_t length, uint8_t allow_decimal_zeroes);
uint8_t swr_v1_clients_loopback(uint8_t version, const uint8_t *address);
struct swr_v1_clients_ip_text_plan { uint8_t bytes[40]; uint32_t length; };
struct swr_v1_clients_ip_text_plan swr_v1_clients_ip_text(uint8_t version, const uint8_t *address);
struct swr_v1_clients_url_plan {
    uint32_t kind, datagram;
    size_t host_offset, host_length, port_offset, port_length;
};
/* Kinds0 invalid,1 IPv4/hostname,2 IPv6,3 Unix. Digit classification stays native. */
struct swr_v1_clients_url_plan swr_v1_clients_url(const uint8_t *, size_t);
uint8_t swr_v1_clients_port(int32_t port, uint8_t for_connect);
/* Request0 read/1 write/2 both/other invalid; flags read1/write2/both4.
 * Actions0 reject/1 call read/2 call write/3 call both/4 set EINVAL. */
uint32_t swr_v1_clients_shutdown(uint8_t live, uint32_t flags, uint32_t request);
struct swr_v1_clients_host_match { uint32_t found; size_t offset, length; };
/* Line already has its first '#' replaced by NUL, as in the pinned caller.
 * spaces points to256 native locale classification bytes; no pointer retained. */
struct swr_v1_clients_host_match swr_v1_clients_hosts_match(const uint8_t *, size_t, const uint8_t *, size_t, const uint8_t *spaces);
struct swr_v1_clients_cookie_plan { size_t key_length, value_offset, value_length; };
struct swr_v1_clients_cookie_plan swr_v1_clients_cookie(const uint8_t *, size_t);
struct swr_v1_clients_exec_plan { uint32_t action, stage, iteration; };
/* Stages0 send/1 defer-receive/2 retry-close; actions0 fail/1 send/2 receive/3 close/4 success. */
struct swr_v1_clients_exec_plan swr_v1_clients_http_exec(uint32_t stage, uint32_t iteration, uint8_t retries, uint8_t deferred, uint16_t status);
/* Caller-owned bounded DNS codec buffers; no native execution or retained state. */
int32_t swr_v1_clients_domain_encode(const uint8_t *, size_t, uint8_t *, size_t);
uint8_t swr_v1_clients_domain_decode(uint8_t *, size_t, uint8_t signed_char);
enum swr_v1_clients_close_action {
    SWR_CLIENTS_CLOSE_REJECT=0, SWR_CLIENTS_CLOSE_PUBLISH=1,
    SWR_CLIENTS_CLOSE_SSL=2, SWR_CLIENTS_CLOSE_UNLINK=3,
    SWR_CLIENTS_CLOSE_EVENT=4, SWR_CLIENTS_CLOSE_TIMER=5,
    SWR_CLIENTS_CLOSE_CALLBACK=6, SWR_CLIENTS_CLOSE_DEACTIVATE=7,
    SWR_CLIENTS_CLOSE_ADVANCE=8, SWR_CLIENTS_CLOSE_FD=9,
    SWR_CLIENTS_CLOSE_SUCCESS=10
};
struct swr_v1_clients_close_plan { uint32_t action, stage; };
struct swr_v1_clients_close_plan swr_v1_clients_close_next(uint32_t stage, uint32_t facts);
enum swr_v1_clients_write_action {
    SWR_CLIENTS_WRITE_ADVANCE=0, SWR_CLIENTS_WRITE_HANDSHAKE=1,
    SWR_CLIENTS_WRITE_WRITABLE=2, SWR_CLIENTS_WRITE_GET_OPTION=3,
    SWR_CLIENTS_WRITE_READ_INTEREST=4, SWR_CLIENTS_WRITE_DRAIN_CALLBACK=5,
    SWR_CLIENTS_WRITE_MARK_CONNECTED=6, SWR_CLIENTS_WRITE_SOCKS_SEND=7,
    SWR_CLIENTS_WRITE_HTTP_SEND=8, SWR_CLIENTS_WRITE_CONNECT_CALLBACK=9,
    SWR_CLIENTS_WRITE_FAIL=10, SWR_CLIENTS_WRITE_FAIL_SSL=11,
    SWR_CLIENTS_WRITE_WARN_OPTION=12, SWR_CLIENTS_WRITE_SET_SSL_WAIT=13,
    SWR_CLIENTS_WRITE_SUCCESS=14, SWR_CLIENTS_WRITE_ERROR=15
};
struct swr_v1_clients_write_plan { uint32_t action, stage; };
struct swr_v1_clients_write_plan swr_v1_clients_write_next(uint32_t stage, uint32_t facts);
enum swr_v1_clients_read_action {
    SWR_CLIENTS_READ_ADVANCE=0, SWR_CLIENTS_READ_HTTP_RECEIVE=1,
    SWR_CLIENTS_READ_HTTP_HANDSHAKE=2, SWR_CLIENTS_READ_HTTP_READY=3,
    SWR_CLIENTS_READ_SOCKS_RECEIVE=4, SWR_CLIENTS_READ_SOCKS_HANDSHAKE=5,
    SWR_CLIENTS_READ_CLEAR_BUFFER=6, SWR_CLIENTS_READ_SSL_HANDSHAKE=7,
    SWR_CLIENTS_READ_PROTOCOL_RECEIVE=8, SWR_CLIENTS_READ_PROTOCOL_CLOSE=9,
    SWR_CLIENTS_READ_SLEEP=10, SWR_CLIENTS_READ_RECEIVE=11,
    SWR_CLIENTS_READ_CATCH_ERROR=12, SWR_CLIENTS_READ_WARN=13,
    SWR_CLIENTS_READ_CLOSE=14, SWR_CLIENTS_READ_RECEIVE_CALLBACK=15,
    SWR_CLIENTS_READ_CONNECT_CALLBACK=16, SWR_CLIENTS_READ_FAIL_HTTP=17,
    SWR_CLIENTS_READ_FAIL_SOCKS=18, SWR_CLIENTS_READ_FAIL_SSL=19,
    SWR_CLIENTS_READ_SUCCESS=20
};
struct swr_v1_clients_read_plan { uint32_t action, stage; };
struct swr_v1_clients_read_plan swr_v1_clients_read_next(uint32_t stage, uint32_t facts);
enum swr_v1_clients_connect_action {
    SWR_CLIENTS_CONNECT_ADVANCE=0, SWR_CLIENTS_CONNECT_SET_TIMEOUT=1,
    SWR_CLIENTS_CONNECT_KERNEL_TIMEOUT=2, SWR_CLIENTS_CONNECT_ADDRESS=3,
    SWR_CLIENTS_CONNECT_NONBLOCKING=4, SWR_CLIENTS_CONNECT_BLOCKING=5,
    SWR_CLIENTS_CONNECT_ASYNC_PENDING=6, SWR_CLIENTS_CONNECT_ACTIVATE=7,
    SWR_CLIENTS_CONNECT_SOCKS_SEND=8, SWR_CLIENTS_CONNECT_SOCKS_PUBLISH=9,
    SWR_CLIENTS_CONNECT_SOCKS_RECEIVE=10, SWR_CLIENTS_CONNECT_SOCKS_HANDSHAKE=11,
    SWR_CLIENTS_CONNECT_HTTP_SEND=12, SWR_CLIENTS_CONNECT_HTTP_RECEIVE=13,
    SWR_CLIENTS_CONNECT_HTTP_HANDSHAKE=14, SWR_CLIENTS_CONNECT_SSL_HANDSHAKE=15,
    SWR_CLIENTS_CONNECT_RETURN_RESULT=16, SWR_CLIENTS_CONNECT_SUCCESS=17,
    SWR_CLIENTS_CONNECT_ERROR=18, SWR_CLIENTS_CONNECT_WARN_CALLBACKS=19,
    SWR_CLIENTS_CONNECT_ALLOCATE_BUFFER=20, SWR_CLIENTS_CONNECT_WATERMARK=21,
    SWR_CLIENTS_CONNECT_DNS_LOOKUP=22, SWR_CLIENTS_CONNECT_ASYNC_CONNECT=23,
    SWR_CLIENTS_CONNECT_ADD_TIMER=24, SWR_CLIENTS_CONNECT_ADD_EVENT=25,
    SWR_CLIENTS_CONNECT_FAIL_CALLBACK=26
};
struct swr_v1_clients_connect_plan { uint32_t action, stage; };
struct swr_v1_clients_connect_plan swr_v1_clients_connect_next(uint32_t stage, uint32_t facts);
enum swr_v1_clients_persistent_action {
    SWR_CLIENTS_PERSISTENT_ADVANCE=0, SWR_CLIENTS_PERSISTENT_FIND=1,
    SWR_CLIENTS_PERSISTENT_TAKE=2, SWR_CLIENTS_PERSISTENT_REUSE=3,
    SWR_CLIENTS_PERSISTENT_DROP_STALE=4, SWR_CLIENTS_PERSISTENT_CREATE=5,
    SWR_CLIENTS_PERSISTENT_CREATE_FAILED=6, SWR_CLIENTS_PERSISTENT_SET_IDENTITY=7,
    SWR_CLIENTS_PERSISTENT_PUBLISH_SOCKET=8, SWR_CLIENTS_PERSISTENT_KEEP=9,
    SWR_CLIENTS_PERSISTENT_ENABLE_SSL=10, SWR_CLIENTS_PERSISTENT_RETURN=11,
    SWR_CLIENTS_PERSISTENT_DELETE_TIMER=12, SWR_CLIENTS_PERSISTENT_FREE_CALLABLE=13,
    SWR_CLIENTS_PERSISTENT_ERASE_POOL=14, SWR_CLIENTS_PERSISTENT_DELETE_CLIENT=15,
    SWR_CLIENTS_PERSISTENT_FREE_SOCKET_OBJECT=16, SWR_CLIENTS_PERSISTENT_DETACH=17
};
struct swr_v1_clients_persistent_plan { uint32_t action, stage; };
struct swr_v1_clients_persistent_plan swr_v1_clients_persistent_next(uint32_t stage, uint32_t facts);
struct swr_v1_clients_resolv_line { uint32_t kind; size_t offset, length; };
struct swr_v1_clients_resolv_line swr_v1_clients_resolv_line(const uint8_t *, size_t);
struct swr_v1_clients_dns_endpoint { uint32_t has_port; size_t host_length, port_offset; };
struct swr_v1_clients_dns_endpoint swr_v1_clients_dns_endpoint(const uint8_t *, size_t);
enum swr_v1_clients_transport_action {
    SWR_CLIENTS_TRANSPORT_ADVANCE=0, SWR_CLIENTS_TRANSPORT_SET_TIMEOUT=1,
    SWR_CLIENTS_TRANSPORT_KERNEL_TIMEOUT=2, SWR_CLIENTS_TRANSPORT_PUBLISH_FLAGS=3,
    SWR_CLIENTS_TRANSPORT_ADDRESS=4, SWR_CLIENTS_TRANSPORT_WARN_RECEIVE=5,
    SWR_CLIENTS_TRANSPORT_WARN_ERROR=6, SWR_CLIENTS_TRANSPORT_DNS_LOOKUP=7,
    SWR_CLIENTS_TRANSPORT_ACTIVATE=8, SWR_CLIENTS_TRANSPORT_SOCKET_TIMEOUT=9,
    SWR_CLIENTS_TRANSPORT_BIND_UNIX=10, SWR_CLIENTS_TRANSPORT_WARN_BIND=11,
    SWR_CLIENTS_TRANSPORT_ENABLE_DTLS=12, SWR_CLIENTS_TRANSPORT_CONNECT=13,
    SWR_CLIENTS_TRANSPORT_CLEAN=14, SWR_CLIENTS_TRANSPORT_ADD_EVENT=15,
    SWR_CLIENTS_TRANSPORT_CONNECT_CALLBACK=16, SWR_CLIENTS_TRANSPORT_SSL_HANDSHAKE=17,
    SWR_CLIENTS_TRANSPORT_FAIL_CLOSE=18, SWR_CLIENTS_TRANSPORT_ERROR_CALLBACK=19,
    SWR_CLIENTS_TRANSPORT_SUCCESS=20, SWR_CLIENTS_TRANSPORT_ERROR=21,
    SWR_CLIENTS_TRANSPORT_EVENT_WRITE=22, SWR_CLIENTS_TRANSPORT_OVERFLOW=23,
    SWR_CLIENTS_TRANSPORT_BUFFER_FULL=24, SWR_CLIENTS_TRANSPORT_RETURN_WRITE=25
};
struct swr_v1_clients_transport_plan { uint32_t action, stage; };
struct swr_v1_clients_transport_plan swr_v1_clients_transport_next(uint32_t stage, uint32_t facts);
intptr_t swr_v1_clients_datagram_send(intptr_t result, intptr_t narrowed_length);
/* Sole private pool; binary keys, FIFO opaque native tokens. Allocation returns
 * 0 success/1 OOM/2 invalid; caller throws only after return. Never destroys Client.
 * All calls require live owner/no concurrent mutation; key storage is native. */
void *swr_v1_clients_pool_create(void);
void swr_v1_clients_pool_destroy(void *);
uint32_t swr_v1_clients_pool_push(void *, const uint8_t *, size_t, void *);
struct swr_v1_clients_pool_state { uint32_t kind; size_t length; };
struct swr_v1_clients_pool_state swr_v1_clients_pool_state(const void *, const uint8_t *, size_t);
void *swr_v1_clients_pool_take(void *, const uint8_t *, size_t);
uint8_t swr_v1_clients_pool_remove_empty(void *, const uint8_t *, size_t);
enum swr_v1_clients_resolver_action {
    SWR_CLIENTS_RESOLVER_LOOKUP=1, SWR_CLIENTS_RESOLVER_COUNT=2,
    SWR_CLIENTS_RESOLVER_STORE_CLUSTER=3, SWR_CLIENTS_RESOLVER_STRING=4,
    SWR_CLIENTS_RESOLVER_RESET=5, SWR_CLIENTS_RESOLVER_RELEASE=6,
    SWR_CLIENTS_RESOLVER_POP=7, SWR_CLIENTS_RESOLVER_FIND_HOST=8,
    SWR_CLIENTS_RESOLVER_COPY_HOST=9, SWR_CLIENTS_RESOLVER_COLON_PORT=10,
    SWR_CLIENTS_RESOLVER_APPEND_PORT=11, SWR_CLIENTS_RESOLVER_DTOR=12,
    SWR_CLIENTS_RESOLVER_RESULT=13, SWR_CLIENTS_RESOLVER_EMPTY=14
};
struct swr_v1_clients_resolver_plan { uint32_t action, stage; };
struct swr_v1_clients_resolver_plan swr_v1_clients_resolver_next(uint32_t stage, uint32_t facts);
enum swr_v1_clients_http_connection_action {
    SWR_CLIENTS_HC_ADVANCE=0, SWR_CLIENTS_HC_TRUE=1, SWR_CLIENTS_HC_FALSE=2,
    SWR_CLIENTS_HC_ALLOC_BODY=3, SWR_CLIENTS_HC_CREATE_SOCKET=4,
    SWR_CLIENTS_HC_NOMEM=5, SWR_CLIENTS_HC_ERRNO=6, SWR_CLIENTS_HC_PUBLISH_SOCKET=7,
    SWR_CLIENTS_HC_SSL=8, SWR_CLIENTS_HC_SOCKET_ERROR_CLOSE=9,
    SWR_CLIENTS_HC_APPLY=10, SWR_CLIENTS_HC_RESET_CONNECTION=11,
    SWR_CLIENTS_HC_CONFIGURE=12, SWR_CLIENTS_HC_CONNECT=13,
    SWR_CLIENTS_HC_PUBLISH_PROPERTIES=14, SWR_CLIENTS_HC_LIVENESS=15,
    SWR_CLIENTS_HC_CLOSE_DEAD=16, SWR_CLIENTS_HC_RETRY_CONNECT=17,
    SWR_CLIENTS_HC_DEFER_CLOSE=18, SWR_CLIENTS_HC_DISCONNECTED=19,
    SWR_CLIENTS_HC_CLOSE=20, SWR_CLIENTS_HC_SAVED_ERROR=21, SWR_CLIENTS_HC_RESET=22
};
struct swr_v1_clients_http_connection_plan { uint32_t action, stage, iteration; };
struct swr_v1_clients_http_connection_plan swr_v1_clients_http_connection_next(uint32_t kind, uint32_t stage, uint32_t facts, uint32_t iteration, uint8_t retries);
enum swr_v1_clients_http_response_action {
    SWR_CLIENTS_HR_ADVANCE=0, SWR_CLIENTS_HR_FALSE=1, SWR_CLIENTS_HR_FAIL=2,
    SWR_CLIENTS_HR_RECV=3, SWR_CLIENTS_HR_EOF_ERROR=4, SWR_CLIENTS_HR_FINISH=5,
    SWR_CLIENTS_HR_HEADER_APPEND=6, SWR_CLIENTS_HR_HEADER_COMPLETE=7,
    SWR_CLIENTS_HR_PARSE=8, SWR_CLIENTS_HR_HEADER_ERROR=9,
    SWR_CLIENTS_HR_HEADER_CONTINUE=10, SWR_CLIENTS_HR_PROTOCOL_ERROR=11,
    SWR_CLIENTS_HR_UPGRADE_BUFFER=12, SWR_CLIENTS_HR_WEBSOCKET=13,
    SWR_CLIENTS_HR_CLOSE_SUCCESS=14, SWR_CLIENTS_HR_RESET_SUCCESS=15
};
struct swr_v1_clients_http_response_plan { uint32_t action, stage; size_t offset; };
struct swr_v1_clients_http_response_plan swr_v1_clients_http_response_next(uint32_t stage, uint32_t facts, size_t size, size_t parsed, size_t websocket_header);
struct swr_v1_clients_format_span { const uint8_t *data; size_t length; };
struct swr_v1_clients_format_result { size_t written; uint32_t error; };
/* Output is disjoint native-owned writable bytes, possibly uninitialized.
 * Required inputs initialized.0 success,1 invalid,2 printf-count overflow. */
struct swr_v1_clients_format_result swr_v1_clients_http_format(uint32_t kind, struct swr_v1_clients_format_span, struct swr_v1_clients_format_span, struct swr_v1_clients_format_span, struct swr_v1_clients_format_span, size_t number, uint8_t *output, size_t capacity);
enum swr_v1_clients_coro_action {
    SWR_CLIENTS_CC_ADVANCE=0, SWR_CLIENTS_CC_TRUE=1, SWR_CLIENTS_CC_FALSE=2,
    SWR_CLIENTS_CC_ERROR_FALSE=3, SWR_CLIENTS_CC_ERROR_LONG=4,
    SWR_CLIENTS_CC_LONG=5, SWR_CLIENTS_CC_EMPTY=6, SWR_CLIENTS_CC_STRING=7,
    SWR_CLIENTS_CC_PACKET=8, SWR_CLIENTS_CC_RAW=9, SWR_CLIENTS_CC_POP=10,
    SWR_CLIENTS_CC_NOMEM=11, SWR_CLIENTS_CC_FETCH=12, SWR_CLIENTS_CC_FREE=13,
    SWR_CLIENTS_CC_EISCONN=14, SWR_CLIENTS_CC_READ_TYPE=15,
    SWR_CLIENTS_CC_VERIFY_PORT=16, SWR_CLIENTS_CC_CREATE=17,
    SWR_CLIENTS_CC_PUBLISH=18, SWR_CLIENTS_CC_APPLY=19, SWR_CLIENTS_CC_SOCKET=20,
    SWR_CLIENTS_CC_PORT_WARNING=21, SWR_CLIENTS_CC_HOST_WARNING=22,
    SWR_CLIENTS_CC_DATA_WARNING=23, SWR_CLIENTS_CC_FILE_WARNING=24,
    SWR_CLIENTS_CC_GET_SOCKET=25, SWR_CLIENTS_CC_CONNECT_TIMEOUT=26,
    SWR_CLIENTS_CC_CONNECT=27, SWR_CLIENTS_CC_RDWR_TIMEOUT=28,
    SWR_CLIENTS_CC_CONNECT_ERROR=29, SWR_CLIENTS_CC_CONNECTED=30,
    SWR_CLIENTS_CC_DGRAM_FILE=31
};
struct swr_v1_clients_coro_plan { uint32_t action, stage; };
struct swr_v1_clients_coro_plan swr_v1_clients_coro_next(uint32_t operation, uint32_t stage, uint32_t facts, intptr_t result, size_t length);
struct swr_v1_clients_async_meta { uint32_t slot; const uint8_t *name; size_t length; };
struct swr_v1_clients_async_meta swr_v1_clients_async_meta(uint32_t slot);
uint32_t swr_v1_clients_async_event(const uint8_t *folded, size_t length, size_t original_length);
struct swr_v1_clients_async_plan { uint32_t action, stage; };
struct swr_v1_clients_async_plan swr_v1_clients_async_next(uint32_t operation, uint32_t stage, uint32_t facts);
#ifdef __cplusplus
}
#endif
#endif
