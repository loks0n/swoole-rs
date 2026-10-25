#ifndef SWOOLE_RS_ERROR_H
#define SWOOLE_RS_ERROR_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Known Swoole error -> immortal NUL-terminated string; unmapped -> null. */
const char *swr_v1_error_message(int32_t code);
#ifdef __cplusplus
}
#endif
#endif
