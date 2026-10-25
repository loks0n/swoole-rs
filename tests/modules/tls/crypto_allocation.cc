// SPDX-License-Identifier: Apache-2.0
// Supported OpenSSL allocator hooks; one failed library allocation per case.
#include "swoole_server.h"
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>

static void require(bool value) { if (!value) std::abort(); }
struct CryptoTrace { bool active = false, injected = false;size_t fail_at = 0, calls = 0, frees = 0; };
static thread_local CryptoTrace trace;
static bool fail_allocation() {
    if (!trace.active) return false;
    ++trace.calls;
    if (trace.fail_at && trace.calls == trace.fail_at) {
        trace.injected = true;errno = ENOMEM;return true;
    }
    return false;
}
static void *crypto_malloc(size_t size, const char *, int) {
    return fail_allocation() ? nullptr : std::malloc(size);
}
static void *crypto_realloc(void *pointer, size_t size, const char *, int) {
    return fail_allocation() ? nullptr : std::realloc(pointer, size);
}
static void crypto_free(void *pointer, const char *, int) {
    if (trace.active && pointer) ++trace.frees;
    std::free(pointer);
}

static int dtls_init_allocation() {
#ifndef SW_SUPPORT_DTLS
    std::cerr << "unsupported: DTLS disabled in this native configuration\n";return 77;
#else
    for (size_t fail_at : {size_t(0),size_t(1)}) {
        int fds[2];require(socketpair(AF_UNIX,SOCK_DGRAM,0,fds) == 0);
        auto ctx = std::make_shared<swoole::SSLContext>();ctx->protocols = SW_SSL_DTLS;require(ctx->create());
        swoole::network::Socket socket{};socket.fd = fds[0];
        {
            swoole::dtls::Session session(&socket,ctx);
            ERR_clear_error();swoole_set_last_error(1234567);errno = 71;
            trace = CryptoTrace{};trace.fail_at = fail_at;trace.active = true;
            bool result = session.init();
            trace.active = false;
            int saved_errno = errno, last_error = swoole_get_last_error();
            unsigned long error = ERR_peek_error();
            if (!fail_at) {
                require(result && socket.ssl && socket.dtls && trace.calls > 0);
                BIO *bio = SSL_get_rbio(socket.ssl);
                require(bio && bio == SSL_get_wbio(socket.ssl) && BIO_get_data(bio) == &session);
                require(SSL_get_ex_data(socket.ssl,swoole_ssl_get_ex_connection_index()) == &socket);
                require(last_error == 1234567);
            } else {
                require(!result && trace.injected && !socket.ssl && !socket.dtls);
                require(last_error == SW_ERROR_SSL_CREATE_SESSION_FAILED);
            }
            std::cout << "crypto-dtls-init " << fail_at << ' ' << result << ' ' << trace.injected << ' '
                      << trace.calls << ' ' << trace.frees << ' ' << saved_errno << ' ' << last_error
                      << ' ' << ERR_GET_REASON(error) << ' ' << (socket.ssl != nullptr) << ' ' << (int)socket.dtls << '\n';
            if (socket.ssl) {SSL_free(socket.ssl);socket.ssl = nullptr;}
        }
        close(fds[0]);close(fds[1]);
    }
    // Deeper BIO_new failures have an original unchecked-null domain. This bounded
    // gate proves SSL_new's defined first-allocation failure, not every OOM cutoff.
    swoole::dtls::BIO_meth_free();return 0;
#endif
}

int main(int argc, char **argv) {
    if (argc == 2 && std::string(argv[1]) == "--identify") return 0;
#if defined(OPENSSL_IS_BORINGSSL) || defined(LIBRESSL_VERSION_NUMBER)
    std::cerr << "unsupported: this fixture requires OpenSSL allocator-hook contract\n";return 77;
#else
    // Must precede every OpenSSL allocation, including swoole_init/context setup.
    if (!CRYPTO_set_mem_functions(crypto_malloc, crypto_realloc, crypto_free)) {
        std::cerr << "unsupported: OpenSSL allocator hooks unavailable before initialization\n";return 77;
    }
    const char *reference = std::getenv("SWR_TLS_REFERENCE");require(reference);
    const char *operation = std::getenv("SWR_TLS_CRYPTO_OPERATION");
    const bool dh = operation && std::strcmp(operation,"dhparam") == 0;
    const bool curve = operation && std::strcmp(operation,"curve") == 0;
#ifdef OPENSSL_NO_ECDH
    if (curve) {std::cerr << "unsupported: ECDH disabled in this native configuration\n";return 77;}
#endif
    std::string file = std::string(reference) + (dh ? "/tests/include/ssl_certs/dhparams.pem" : "/tests/include/ssl_certs/ca.crt");
    swoole_init();
    if (operation && std::strcmp(operation,"dtls-init") == 0) {
        int status = dtls_init_allocation();swoole_clean();return status;
    }
    {
        swoole::SSLContext warm{};require(warm.create());
        if (curve) {warm.ecdh_curve = "prime256v1";require(warm.set_ecdh_curve());}
        else if (dh) {warm.dhparam = file;require(warm.set_dhparam());}
        else {warm.client_cert_file = file;warm.verify_depth = 3;require(warm.set_client_certificate());}
    }
    size_t limit = 0;
    for (size_t fail_at = 0; fail_at <= limit; ++fail_at) {
        swoole::SSLContext ctx{};require(ctx.create());
        if (curve) ctx.ecdh_curve = "prime256v1";
        else if (dh) ctx.dhparam = file;
        else {ctx.client_cert_file = file;ctx.verify_depth = 3;}
        ERR_clear_error();errno = 71;
        trace = CryptoTrace{};trace.fail_at = fail_at;trace.active = true;
        bool result = curve ? ctx.set_ecdh_curve() : dh ? ctx.set_dhparam() : ctx.set_client_certificate();
        trace.active = false;
        int saved_errno = errno;
        unsigned long error = ERR_peek_error();
        if (!fail_at) {
            require(result && trace.calls > 0 && trace.calls <= 4096);
            limit = trace.calls;
        }
        if (!dh && !curve) {
            auto callback = SSL_CTX_get_verify_callback(ctx.context);
            require(callback && callback(0, nullptr) == 1);
            require(SSL_CTX_get_verify_mode(ctx.context) == SSL_VERIFY_PEER);
            require(SSL_CTX_get_verify_depth(ctx.context) == 3);
        }
        const STACK_OF(X509_NAME) *names = SSL_CTX_get_client_CA_list(ctx.context);
        std::cout << (curve ? "crypto-curve " : dh ? "crypto-dh " : "crypto-new ") << fail_at << ' ' << result << ' ' << trace.injected
                  << ' ' << trace.calls << ' ' << trace.frees << ' ' << saved_errno
                  << ' ' << ERR_GET_REASON(error) << ' ' << (names ? sk_X509_NAME_num(names) : -1) << '\n';
        // Context/X509 list destruction is native and occurs with injection off.
    }
    swoole_clean();
#endif
}
