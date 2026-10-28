#ifndef SWOOLE_RS_PHPCLIENTS_H
#define SWOOLE_RS_PHPCLIENTS_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <sys/types.h>
#include <sys/uio.h>

#ifdef __cplusplus
extern "C" {
#endif

/* PHP Coroutine\Socket (crates/phpclients). MINIT passes upstream's method
 * table, built from the stub's arginfo; Rust registers the class, its exception,
 * properties and constants, and the methods are its zim_swoole_socket_coro_*
 * exports (getOption, setOption and import stay C++). */
struct _zend_function_entry;
struct _zend_class_entry;
struct _zend_object;
struct _zval_struct;
void swr_v1_phpclients_socket_minit(const struct _zend_function_entry *methods,
                                    struct _zend_class_entry *exception,
                                    bool shortname,
                                    bool sockets,
                                    int module,
                                    uint32_t ai,
                                    struct _zend_class_entry **socket_class);

/* Defined by ext-src/swoole_socket_coro.cc for those methods: the coroutine
 * socket (a SocketImpl *) is still C++, so each operation is one call. */
void swoole_rs_php_error(int level, bool fatal, const char *message);
void swoole_socket_coro_unconstructed(void);
void *swoole_socket_coro_create(int64_t domain, int64_t type, int64_t protocol, int *error);
void swoole_socket_coro_init(struct _zend_object *object);
void swoole_socket_coro_release(struct _zend_object *object);
void swoole_socket_coro_close(struct _zend_object *object);
bool swoole_socket_coro_is_closed(void *socket);
int swoole_socket_coro_error(void *socket, const char **message);
void swoole_socket_coro_set_error(void *socket, int code, const char *message);
bool swoole_socket_coro_bind(void *socket, const char *address, size_t length, int64_t port);
bool swoole_socket_coro_listen(void *socket, int64_t backlog);
void *swoole_socket_coro_accept(void *socket, double timeout);
bool swoole_socket_coro_port_required(void *socket);
bool swoole_socket_coro_connect(void *socket, const char *host, size_t length, int64_t port, double timeout);
bool swoole_socket_coro_check_liveness(void *socket);
int64_t swoole_socket_coro_bound_cid(void *socket, int64_t event);
/* op: 0 peek, 1 recv, 2 recv_all, 3 recv_line, 4 recv_with_buffer, 5 send, 6 send_all. */
ssize_t swoole_socket_coro_transfer(void *socket, int op, char *buffer, size_t length, double timeout);
ssize_t swoole_socket_coro_recv_packet(void *socket, double timeout);
char *swoole_socket_coro_pop_packet(void *socket);
/* op: 0 readv, 1 readv_all, 2 writev, 3 writev_all. */
ssize_t swoole_socket_coro_vector(
    void *socket, int op, struct iovec *vectors, int count, double timeout, int *index, size_t *offset);
bool swoole_socket_coro_sendfile(void *socket, const char *file, int64_t offset, int64_t length);
ssize_t swoole_socket_coro_recvfrom(void *socket, char *buffer, size_t length, double timeout);
const char *swoole_socket_coro_address(void *socket, int *port);
ssize_t swoole_socket_coro_sendto(
    void *socket, const char *address, size_t length, int64_t port, const char *data, size_t data_length);
bool swoole_socket_coro_shutdown(void *socket, int64_t how);
bool swoole_socket_coro_getsockname(void *socket);
bool swoole_socket_coro_getpeername(void *socket, char *address, size_t size, int *port);
bool swoole_socket_coro_cancel(void *socket, int event);
bool swoole_socket_coro_ssl_handshake(void *socket);
bool swoole_socket_coro_set_protocol(void *socket, const struct _zval_struct *settings);

#ifdef __cplusplus
}
#endif
#endif
