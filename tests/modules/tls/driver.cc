// SPDX-License-Identifier: Apache-2.0
#include "swoole_server.h"
#include <cerrno>
#include <cstring>
#include <iostream>
#include <string>

int main(int argc, char **argv) {
    if (argc == 2 && std::string(argv[1]) == "--identify") return 0;
    swoole_init();
    std::cout << "openssl " << OpenSSL_version(OPENSSL_VERSION) << '\n';
    // Explicit initialization is intentional: the unchanged ssl.password original
    // separately has uninitialized scalar members. This fixture uses defined input.
    for (uint32_t protocols = 0; protocols < 256; ++protocols) {
        for (int compress = 0; compress < 2; ++compress) {
            swoole::SSLContext ctx{};
            ctx.protocols = protocols;
            ctx.disable_compress = compress;
            errno = 71;
            ERR_clear_error();
            bool result = ctx.create();
            int saved = errno;
            if (!ctx.context) return 4;
            std::cout << "context " << protocols << ' ' << compress << ' ' << result << ' '
                      << ctx.protocols << ' ' << SSL_CTX_get_options(ctx.context) << ' '
                      << SSL_CTX_get_mode(ctx.context) << ' ' << SSL_CTX_get_verify_mode(ctx.context)
                      << ' ' << saved << ' ' << ERR_GET_REASON(ERR_peek_error()) << '\n';
        }
    }
    const char *reference = std::getenv("SWR_TLS_REFERENCE");
    if (!reference) return 2;
    const std::string certs = std::string(reference) + "/tests/include/ssl_certs/";
    for (int scenario = 0; scenario < 49; ++scenario) {
        swoole::SSLContext ctx{};
        ctx.http = (scenario & 1) != 0;ctx.http_v2 = (scenario & 2) != 0;
        ctx.verify_peer = (scenario & 4) != 0;ctx.verify_depth = scenario & 8 ? 3 : 0;
        ctx.prefer_server_ciphers = (scenario & 16) != 0;
        if (scenario < 32) {
            ctx.cert_file = certs + "passwd.crt";ctx.key_file = certs + "passwd_key.pem";
            ctx.passphrase = "swoole";
        } else if (scenario == 32) {
            ctx.cert_file = certs + "does-not-exist-m21-cert.pem";
        } else if (scenario == 33) {
            ctx.key_file = certs + "does-not-exist-m21-key.pem";
        } else if (scenario == 34) {
            ctx.cafile = certs + "does-not-exist-m21-ca.pem";ctx.verify_peer = true;
        } else if (scenario == 35) {
            ctx.cafile = certs + "does-not-exist-m21-ca.pem";ctx.verify_peer = false;
        } else if (scenario == 36) {
            ctx.ciphers = "M21-nonexistent-cipher";
        } else if (scenario == 37) {
            ctx.cert_file = certs + "passwd.crt";ctx.key_file = certs + "passwd_key.pem";
            ctx.passphrase = "incorrect-m21-passphrase";
        } else if (scenario == 38) {
            ctx.client_cert_file = certs + "does-not-exist-m21-client-ca.pem";
        } else if (scenario == 39) {
            ctx.ecdh_curve = "M21-nonexistent-curve";
        } else if (scenario == 40 || scenario == 41) {
            ctx.ciphers = "ECDHE-RSA-AES128-GCM-SHA256";
            ctx.prefer_server_ciphers = scenario == 41;
        } else if (scenario == 42) {
            ctx.dhparam = certs + "dhparams.pem";
        } else if (scenario == 43) {
            ctx.dhparam = certs + "does-not-exist-m21-dh.pem";
        } else if (scenario == 44) {
            ctx.ecdh_curve = "auto";
        } else if (scenario == 45) {
            ctx.ecdh_curve = "prime256v1";
        } else if (scenario == 46) {
            ctx.cafile = certs + "ca.crt";ctx.verify_peer = 1;ctx.verify_depth = 255;
        } else if (scenario == 47) {
            ctx.client_cert_file = certs + "ca.crt";ctx.verify_depth = 3;
        } else {
            ctx.capath = certs;ctx.verify_depth = 1;
        }
        ERR_clear_error();errno = 71;
        bool result = ctx.create();int saved = errno;
        // A failed create() may leave no context (v6.2.4); print that, so both engines are compared.
        if (!ctx.context) {
            std::cout << "setup " << scenario << ' ' << result << " null " << saved << '\n';
            continue;
        }
        std::cout << "setup " << scenario << ' ' << result << ' ' << ctx.protocols << ' '
                  << SSL_CTX_get_options(ctx.context) << ' ' << SSL_CTX_get_mode(ctx.context) << ' '
                  << SSL_CTX_get_verify_mode(ctx.context) << ' ' << SSL_CTX_get_verify_depth(ctx.context)
                  << ' ' << saved << ' ' << ERR_GET_REASON(ERR_peek_error()) << '\n';
    }

    {
        swoole::SSLContext prefix;
        prefix.protocols = 0;prefix.disable_compress = 0;
        prefix.cert_file = certs + "does-not-exist-m21-cert.pem";
        ERR_clear_error();errno = 71;
        bool result = prefix.create();
        // v6.2.4's create() fails on a missing certificate, as on a missing key or CA below.
        if (result) return 6;
        std::cout << "partial-prefix " << result << ' ' << prefix.protocols << '\n';
    }

    {
        swoole::SSLContext prefix;
        prefix.protocols = 0;prefix.disable_compress = 0;
        prefix.key_file = certs + "does-not-exist-m21-key.pem";
        ERR_clear_error();errno = 71;
        bool result = prefix.create();
        if (result) return 7;
        std::cout << "partial-key-prefix " << result << ' ' << prefix.protocols << '\n';
    }
    {
        swoole::SSLContext prefix;
        prefix.protocols = 0;prefix.disable_compress = 0;prefix.verify_peer = 1;
        prefix.cafile = certs + "does-not-exist-m21-ca.pem";
        ERR_clear_error();errno = 71;
        bool result = prefix.create();
        if (result) return 8;
        std::cout << "partial-ca-prefix " << result << ' ' << prefix.protocols << '\n';
    }


    // Defined direct-method prefixes: trailing scalar fields remain unobserved
    // after the original immediate CA/cipher failure.
    {
        swoole::SSLContext prefix;
        prefix.context = SSL_CTX_new(TLS_method());if (!prefix.context) return 9;
        prefix.cafile = certs + "does-not-exist-m21-ca.pem";
        ERR_clear_error();errno = 71;
        bool result = prefix.set_capath();if (result) return 10;
        std::cout << "partial-direct-ca " << result << '\n';
    }
    {
        swoole::SSLContext prefix;
        prefix.context = SSL_CTX_new(TLS_method());if (!prefix.context) return 11;
        prefix.ciphers = "M21-nonexistent-cipher";
        ERR_clear_error();errno = 71;
        bool result = prefix.set_ciphers();if (result) return 12;
        std::cout << "partial-direct-ciphers " << result << '\n';
    }

    {
        swoole::SSLContext prefix;
        prefix.context = SSL_CTX_new(TLS_method());if (!prefix.context) return 13;
        prefix.client_cert_file = certs + "does-not-exist-m21-client-ca.pem";
        prefix.verify_depth = 3;
        ERR_clear_error();errno = 71;
        bool result = prefix.set_client_certificate();if (result) return 14;
        auto callback = SSL_CTX_get_verify_callback(prefix.context);
        if (!callback || callback(0, nullptr) != 1 || callback(1, nullptr) != 1) return 15;
        std::cout << "partial-direct-client-ca " << result << ' ' << SSL_CTX_get_verify_depth(prefix.context)
                  << ' ' << SSL_CTX_get_verify_mode(prefix.context) << ' ' << errno << '\n';
    }


    // Direct original method entry: only context/dhparam are initialized. No
    // unrelated public scalar may be observed during DH failure or success.
    for (int scenario = 0; scenario < 5; ++scenario) {
        swoole::SSLContext prefix;
        prefix.context = SSL_CTX_new(TLS_method());if (!prefix.context) return 16;
        prefix.dhparam = scenario < 2 ? certs + "dhparams.pem" :
            scenario == 2 ? certs + "ca.crt" : scenario == 3 ? certs + "does-not-exist-m21-dh.pem" : "";
        SSL_CTX_set_security_level(prefix.context, scenario == 1 ? 5 : 0);
        ERR_clear_error();errno = 71;
        bool result = prefix.set_dhparam();
        std::cout << "direct-dh " << scenario << ' ' << result << ' ' << errno
                  << ' ' << ERR_GET_REASON(ERR_peek_error()) << '\n';
        if (scenario == 0 && !result) return 17;
        if (scenario >= 2 && result) return 18;
#if OPENSSL_VERSION_MAJOR >= 3
        if (scenario == 1 && result) return 19;
#endif
    }


    for (int scenario = 0; scenario < 4; ++scenario) {
        swoole::SSLContext prefix;
        prefix.context = SSL_CTX_new(TLS_method());if (!prefix.context) return 20;
        prefix.ecdh_curve = scenario == 0 ? "auto" : scenario == 1 ? "prime256v1" :
            scenario == 2 ? "M21-nonexistent-curve" : "";
        bool expected = true;
#ifndef OPENSSL_NO_ECDH
        expected = scenario == 1;
#if defined(SSL_CTX_set1_curves_list) || defined(SSL_CTRL_SET_CURVES_LIST)
        expected = scenario < 2;
        if (scenario == 3) {
            // Actual libraries differ on empty-list acceptance. Probe the same
            // native primitive/options, rather than assuming a version policy.
            SSL_CTX *probe = SSL_CTX_new(TLS_method());if (!probe) return 25;
            SSL_CTX_set_options(probe,SSL_OP_SINGLE_ECDH_USE);
#if SSL_CTRL_SET_ECDH_AUTO
            SSL_CTX_set_ecdh_auto(probe,1);
#endif
            expected = SSL_CTX_set1_curves_list(probe,"") != 0;
            SSL_CTX_free(probe);
        }
#endif
#endif
        ERR_clear_error();errno = 71;
        bool result = prefix.set_ecdh_curve();
        std::cout << "direct-curve " << scenario << ' ' << result << ' ' << errno
                  << ' ' << ERR_GET_REASON(ERR_peek_error()) << ' ' << expected << '\n';
        if (result != expected) return 23;
    }

#ifdef SW_SUPPORT_DTLS
    swoole::network::Socket socket{};
    socket.info.addr.inet_v4.sin_family = AF_INET;
    socket.info.addr.inet_v4.sin_port = htons(12345);
    socket.info.addr.inet_v4.sin_addr.s_addr = htonl(0x7f000001);
    for (int length : {0, 1, 8, 64}) {
        for (int requested : {0, 1, 7, 64, 128}) {
            for (int peek : {0, 1}) {
                swoole::dtls::Session session(&socket, {});
                std::string input(length, 'x');
                session.append(input.data(), input.size());
                session.peek_mode = peek;
                BIO *bio = BIO_new(swoole::dtls::BIO_get_methods());
                BIO_set_data(bio, &session);BIO_set_init(bio, 1);
                char bytes[128];std::memset(bytes, 0x55, sizeof(bytes));
                int n = swoole::dtls::BIO_read(bio, bytes, requested);
                std::cout << "read " << length << ' ' << requested << ' ' << peek << ' ' << n
                          << ' ' << session.rxqueue.size() << ' ' << session.get_buffer_length()
                          << ' ' << BIO_should_retry(bio) << ' ';
                for (int i = 0; i < 128; ++i) std::cout << (int)(unsigned char)bytes[i] << ',';
                std::cout << '\n';BIO_free(bio);
            }
        }
    }
    swoole::dtls::Session session(&socket, {});
    session.append("abc", 3);session.append("defgh", 5);
    BIO *bio = BIO_new(swoole::dtls::BIO_get_methods());BIO_set_data(bio, &session);BIO_set_init(bio, 1);
    int commands[] = {BIO_CTRL_EOF, BIO_CTRL_GET_CLOSE, BIO_CTRL_SET_CLOSE, BIO_CTRL_WPENDING,
        BIO_CTRL_PENDING, BIO_CTRL_FLUSH, BIO_CTRL_DGRAM_SET_CONNECTED, BIO_CTRL_DGRAM_SET_PEER,
        BIO_CTRL_DGRAM_GET_PEER, BIO_CTRL_DGRAM_QUERY_MTU, BIO_CTRL_DGRAM_GET_FALLBACK_MTU,
#ifdef BIO_CTRL_DGRAM_GET_MTU_OVERHEAD
        BIO_CTRL_DGRAM_GET_MTU_OVERHEAD,
#endif
#ifdef BIO_CTRL_DGRAM_SET_PEEK_MODE
        BIO_CTRL_DGRAM_SET_PEEK_MODE,
#endif
        BIO_CTRL_PUSH, BIO_CTRL_POP, BIO_CTRL_DGRAM_SET_NEXT_TIMEOUT,
#if OPENSSL_VERSION_NUMBER >= 0x30000000L
        BIO_CTRL_GET_KTLS_SEND, BIO_CTRL_GET_KTLS_RECV,
#endif
        -12345};
    for (int cmd : commands) {
        for (long value : {-1L, 0L, 1L, 2147483648L}) {
            swoole::network::Address address{};
            long result = swoole::dtls::BIO_ctrl(bio, cmd, value, &address);
            std::cout << "ctrl " << cmd << ' ' << value << ' ' << result << ' '
                      << BIO_get_shutdown(bio) << ' ' << session.peek_mode << ' '
                      << address.addr.inet_v4.sin_family << ' ' << address.addr.inet_v4.sin_port << '\n';
        }
    }
    while (!session.rxqueue.empty()) {sw_free(session.rxqueue.front());session.rxqueue.pop_front();}
    char byte = 0;
    int n = swoole::dtls::BIO_read(bio, &byte, 1);
    std::cout << "empty " << n << ' ' << BIO_should_read(bio) << ' ' << BIO_should_retry(bio) << '\n';
    BIO_free(bio);
    swoole::dtls::BIO_meth_free();
#endif
    swoole_clean();
}
