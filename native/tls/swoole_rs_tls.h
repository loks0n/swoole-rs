/* SPDX-License-Identifier: Apache-2.0 */
#ifndef SWOOLE_RS_TLS_H
#define SWOOLE_RS_TLS_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Copied scalar plans and bounded initialized password bytes only. No native
 * object/OpenSSL pointer, callback or retained borrow enters Rust. */
struct swr_v1_tls_context_plan { uint32_t protocols, disabled; uint8_t dtls; };
struct swr_v1_tls_read_plan { int32_t length; uint8_t consume, retry; };
struct swr_v1_tls_control_plan { long result; uint32_t effect; };
struct swr_v1_tls_context_plan swr_v1_tls_context(uint32_t protocols, uint8_t supports_dtls);
struct swr_v1_tls_read_plan swr_v1_tls_read(uint8_t empty, uint16_t front, int32_t requested, uint8_t peek);
/* Native OpenSSL command -> module-local tag; observed value only for tags0..2.
 * 0 EOF,1 GET_CLOSE,2 PENDING,3 SET_CLOSE,4 success,5 GET_PEER,6 MTU,
 * 7 overhead,8 PEEK,9 zero, other unknown. Effects0 none/1 shutdown/2 peer/3 peek/4 warning. */
struct swr_v1_tls_control_plan swr_v1_tls_control(uint32_t tag, long observed);
/* Native caller-stack setup cursor. No pointer/state retained by Rust.
 * Fact bits: password1/cert2/key4/cookie8/verify16/http32/boring64/clientCA128.
 * Actions: false0,true1,password2,cert3,chain4,key5,check6,cookie7,capath8,
 * noverify9,alpn10,alpninstall11,grease12,clientCA13,ciphers14,observe15. Observe performs no effect and asks native
 * to read only the field belonging to next stage, retaining result. */
enum swr_v1_tls_setup_action {
    SWR_TLS_FALSE = 0,
    SWR_TLS_TRUE = 1,
    SWR_TLS_PASSWORD = 2,
    SWR_TLS_CERT = 3,
    SWR_TLS_CHAIN = 4,
    SWR_TLS_KEY = 5,
    SWR_TLS_CHECK_KEY = 6,
    SWR_TLS_COOKIE = 7,
    SWR_TLS_CAPATH = 8,
    SWR_TLS_NO_VERIFY = 9,
    SWR_TLS_ALPN = 10,
    SWR_TLS_ALPN_INSTALL = 11,
    SWR_TLS_GREASE = 12,
    SWR_TLS_CLIENT_CA = 13,
    SWR_TLS_CIPHERS = 14,
    SWR_TLS_OBSERVE = 15,
    SWR_TLS_LOAD_CA = 16,
    SWR_TLS_DEFAULT_CA = 17,
    SWR_TLS_VERIFY_DEPTH = 18,
    SWR_TLS_CIPHER_LIST = 19,
    SWR_TLS_CIPHER_PREFERENCE = 20,
    SWR_TLS_DHPARAM = 21,
    SWR_TLS_ECDH_CURVE = 22,
    SWR_TLS_CLIENT_VERIFY_INSTALL = 23,
    SWR_TLS_CLIENT_TRUST = 24,
    SWR_TLS_CLIENT_NAMES = 25,
    SWR_TLS_CLIENT_NAMES_INSTALL = 26,
    SWR_TLS_DH_OPEN = 27,
    SWR_TLS_DH_PARSE = 28,
    SWR_TLS_DH_INSTALL = 29,
    SWR_TLS_DH_OPEN_FAILED = 30,
    SWR_TLS_DH_PARSE_FAILED = 31,
    SWR_TLS_DH_INSTALL_FAILED = 32,
    SWR_TLS_DH_RELEASE = 33,
    SWR_TLS_CURVE_OPTIONS = 34,
    SWR_TLS_CURVE_LIST = 35,
    SWR_TLS_CURVE_LIST_FAILED = 36,
    SWR_TLS_CURVE_NAME = 37,
    SWR_TLS_CURVE_UNKNOWN = 38,
    SWR_TLS_CURVE_KEY = 39,
    SWR_TLS_CURVE_KEY_FAILED = 40,
    SWR_TLS_CURVE_INSTALL = 41,
    SWR_TLS_INFO_START_SOCKET = 42,
    SWR_TLS_INFO_RENEGOTIATE = 43,
    SWR_TLS_INFO_LOOP_SOCKET = 44,
    SWR_TLS_INFO_BIOS = 45,
    SWR_TLS_INFO_BUFFER = 46,
    SWR_TLS_SESSION_CREATE = 47,
    SWR_TLS_SESSION_CREATE_FAILED = 48,
    SWR_TLS_SESSION_BIND_BIO = 49
};
enum swr_v1_tls_setup_stage {
    SWR_TLS_STAGE_PASSWORD = 0,
    SWR_TLS_STAGE_CERT = 1,
    SWR_TLS_STAGE_CERT_RESULT = 2,
    SWR_TLS_STAGE_CHAIN_RESULT = 3,
    SWR_TLS_STAGE_KEY = 4,
    SWR_TLS_STAGE_KEY_RESULT = 5,
    SWR_TLS_STAGE_CHECK_KEY_RESULT = 6,
    SWR_TLS_STAGE_COOKIE = 7,
    SWR_TLS_STAGE_CAPATH = 8,
    SWR_TLS_STAGE_VERIFY = 9,
    SWR_TLS_STAGE_HTTP = 10,
    SWR_TLS_STAGE_ALPN_RESULT = 11,
    SWR_TLS_STAGE_GREASE = 12,
    SWR_TLS_STAGE_CLIENT_CA = 13,
    SWR_TLS_STAGE_CLIENT_CA_RESULT = 14,
    SWR_TLS_STAGE_CIPHERS = 15,
    SWR_TLS_STAGE_CIPHERS_RESULT = 16,
    SWR_TLS_STAGE_FINISHED = 17,
    /* Same copied planner, independent subordinate method entry cursors.
     * Each fact below is bit0, observed only when that exact stage is reached. */
    SWR_TLS_STAGE_CA_CONFIG = 100,
    SWR_TLS_STAGE_CA_RESULT = 101,
    SWR_TLS_STAGE_CA_DEPTH = 102,
    SWR_TLS_STAGE_CA_FINISHED = 103,
    SWR_TLS_STAGE_CIPHER_CONFIG = 200,
    SWR_TLS_STAGE_CIPHER_RESULT = 201,
    SWR_TLS_STAGE_CIPHER_PREFERENCE = 202,
    SWR_TLS_STAGE_CIPHER_PREFERENCE_RESULT = 203,
    SWR_TLS_STAGE_DH_CONFIG = 204,
    SWR_TLS_STAGE_DH_RESULT = 205,
    SWR_TLS_STAGE_CURVE_CONFIG = 206,
    SWR_TLS_STAGE_CURVE_RESULT = 207,
    SWR_TLS_STAGE_CLIENT_VERIFY_CONFIG = 300,
    SWR_TLS_STAGE_CLIENT_VERIFY_INSTALLED = 301,
    SWR_TLS_STAGE_CLIENT_TRUST_RESULT = 302,
    SWR_TLS_STAGE_CLIENT_NAMES_RESULT = 303,
    SWR_TLS_STAGE_CLIENT_NAMES_INSTALLED = 304,
    SWR_TLS_STAGE_DH_OPEN = 400,
    SWR_TLS_STAGE_DH_OPEN_RESULT = 401,
    SWR_TLS_STAGE_DH_PARSE_RESULT = 402,
    SWR_TLS_STAGE_DH_INSTALL_RESULT = 403,
    SWR_TLS_STAGE_DH_FAILED = 450,
    SWR_TLS_STAGE_DH_FINISHED = 451,
    SWR_TLS_STAGE_CURVE_CAPABILITY = 500,
    SWR_TLS_STAGE_CURVE_AUTO = 501,
    SWR_TLS_STAGE_CURVE_LIST_RESULT = 502,
    SWR_TLS_STAGE_CURVE_NAME_RESULT = 503,
    SWR_TLS_STAGE_CURVE_KEY_RESULT = 504,
    SWR_TLS_STAGE_CURVE_INSTALLED = 505,
    SWR_TLS_STAGE_CURVE_FAILED = 599,
    SWR_TLS_STAGE_INFO_START = 600,
    SWR_TLS_STAGE_INFO_READY = 601,
    SWR_TLS_STAGE_INFO_ACCEPT = 602,
    SWR_TLS_STAGE_INFO_BUFFER_UNSET = 603,
    SWR_TLS_STAGE_INFO_BIOS_DIFFER = 604,
    SWR_TLS_STAGE_INFO_FINISHED = 605,
    SWR_TLS_STAGE_SESSION_PRESENT = 700,
    SWR_TLS_STAGE_SESSION_CREATE_RESULT = 701,
    SWR_TLS_STAGE_SESSION_BOUND = 702,
    SWR_TLS_STAGE_SESSION_FAILED = 799
};
enum swr_v1_tls_setup_facts {
    SWR_TLS_HAS_PASSWORD = 1,
    SWR_TLS_HAS_CERT = 2,
    SWR_TLS_HAS_KEY = 4,
    SWR_TLS_HAS_COOKIE = 8,
    SWR_TLS_HAS_VERIFY = 16,
    SWR_TLS_HAS_HTTP = 32,
    SWR_TLS_HAS_BORING = 64,
    SWR_TLS_HAS_CLIENT_CA = 128
};
struct swr_v1_tls_setup_plan { uint32_t action, next; };
struct swr_v1_tls_setup_plan swr_v1_tls_setup(uint32_t stage, uint32_t facts, int32_t result);
/* Actual native password callback: preserve its already-narrowed int length.
 * Accepted copies require initialized nonoverlapping source[length] and writable
 * destination[length+1]. Rejected copies touch neither pointer. No native calls
 * or retained storage in Rust; original negative-copy/INT_MIN overflow domain
 * remains excluded, rather than being emulated with an invalid Rust borrow. */
int32_t swr_v1_tls_password(const uint8_t *source, uint8_t nonempty, int32_t length,
                            uint8_t *destination, int32_t capacity);
/* Negative failure0; zero pending1; positive publish2. BoringSSL keeps native SSL_is_dtls. */
uint32_t swr_v1_tls_listen(int32_t result);
#ifdef __cplusplus
}
#endif
#endif
