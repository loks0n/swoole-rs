// SPDX-License-Identifier: Apache-2.0
// Additional fresh in-memory certificate fixture; original certs/tests unchanged.
#include "swoole_server.h"
#include <openssl/rsa.h>
#include <openssl/pem.h>
#include <cstdlib>
#include <fcntl.h>
#include <cstring>
#include <iostream>
#include <string>
#include <array>
#include <sstream>
#include <thread>
#include <climits>
#include <dlfcn.h>

static void require(bool condition) { if (!condition) std::abort(); }
struct Certificate {
    EVP_PKEY *key = nullptr;
    X509 *certificate = nullptr;
    Certificate() {
        EVP_PKEY_CTX *generate = EVP_PKEY_CTX_new_id(EVP_PKEY_RSA, nullptr);
        require(generate && EVP_PKEY_keygen_init(generate) > 0);
        require(EVP_PKEY_CTX_set_rsa_keygen_bits(generate, 2048) > 0);
        require(EVP_PKEY_keygen(generate, &key) > 0);EVP_PKEY_CTX_free(generate);
        certificate = X509_new();require(certificate);
        require(X509_set_version(certificate, 2) == 1);
        require(ASN1_INTEGER_set(X509_get_serialNumber(certificate), 1) == 1);
        require(X509_gmtime_adj(X509_get_notBefore(certificate), -60));
        require(X509_gmtime_adj(X509_get_notAfter(certificate), 3600));
        require(X509_set_pubkey(certificate, key) == 1);
        X509_NAME *subject = X509_get_subject_name(certificate);
        require(X509_NAME_add_entry_by_txt(subject, "CN", MBSTRING_ASC,
                    (const unsigned char *) "localhost", -1, -1, 0) == 1);
        require(X509_set_issuer_name(certificate, subject) == 1);
        require(X509_sign(certificate, key, EVP_sha256()) > 0);
    }
    ~Certificate() { X509_free(certificate);EVP_PKEY_free(key); }
};

struct CertificateFile {
    std::string path;
    explicit CertificateFile(X509 *certificate) {
        if (!certificate) return;
        char name[] = "/tmp/m21-client-ca-XXXXXX";
        int fd = mkstemp(name);require(fd >= 0);
        path = name;
        FILE *file = fdopen(fd, "w");require(file);
        require(PEM_write_X509(file, certificate) == 1);require(fclose(file) == 0);
    }
    ~CertificateFile() { if (!path.empty()) require(unlink(path.c_str()) == 0); }
};

static int handshake_step(SSL *ssl) {
    ERR_clear_error();
    int result = SSL_do_handshake(ssl);
    if (result == 1) return 1;
    int error = SSL_get_error(ssl, result);
    return error == SSL_ERROR_WANT_READ || error == SSL_ERROR_WANT_WRITE ? 0 : -1;
}

static void password_callback() {
    swoole::SSLContext ctx{};ctx.passphrase = "initial";require(ctx.create());
    auto callback = SSL_CTX_get_default_passwd_cb(ctx.context);
    void *userdata = SSL_CTX_get_default_passwd_cb_userdata(ctx.context);
    require(callback && userdata == &ctx);
    // Native callback retains the live context, not an eager passphrase snapshot.
    for (const std::string &value : {std::string("swoole"), std::string("a\0b", 3), std::string(),
                                    std::string("x"), std::string("xy"), std::string(7, 'q'),
                                    std::string(14, 'r'), std::string(15, 's'), std::string(512, 't'),
                                    std::string("\xff\0\x7f", 3)}) {
        ctx.passphrase = value;
        for (int capacity : {-8, -1, 0, 1, 2, 3, 4, 7, 8, 15, 16}) {
            unsigned char expected[16];std::memset(expected, 0x55, sizeof(expected));
            int length = !value.empty() && (int)value.size() < capacity - 1 ? (int)value.size() : 0;
            if (length) {std::memcpy(expected, value.data(), length);expected[length] = 0;}
            for (int verify : {0, 1}) {
                char output[16];std::memset(output, 0x55, sizeof(output));
                require(callback(output, capacity, verify, userdata) == length);
                require(std::memcmp(output, expected, sizeof(output)) == 0);
            }
            std::cout << "password-callback " << value.size() << ' ' << capacity << ' ' << length << ' ';
            for (unsigned char byte : expected) std::cout << (int)byte << ',';
            std::cout << '\n';
        }
    }
}

static void info_callback() {
    swoole::SSLContext ctx{};require(ctx.create());
    auto callback = SSL_CTX_get_info_callback(ctx.context);require(callback);
    // Unrelated events must not observe SSL or ex_data at all.
    callback(nullptr, 0, INT_MIN);callback(nullptr, SSL_CB_LOOP, INT_MAX);
    for (int where : {0, SSL_CB_LOOP, SSL_CB_HANDSHAKE_START, SSL_CB_ACCEPT_LOOP,
                      SSL_CB_HANDSHAKE_START | SSL_CB_ACCEPT_LOOP}) {
        for (int ready : {0, 1}) for (int buffered : {0, 1}) for (int split : {0, 1}) {
            swoole::network::Socket socket{};
            SSL *ssl = SSL_new(ctx.context);require(ssl);
            require(SSL_set_ex_data(ssl, swoole_ssl_get_ex_connection_index(), &socket) == 1);
            BIO *rbio = BIO_new(BIO_s_mem()), *wbio = split ? BIO_new(BIO_s_mem()) : rbio;
            require(rbio && wbio);SSL_set_bio(ssl,rbio,wbio);
            for (int ret : {INT_MIN, 0, INT_MAX}) {
                socket.ssl_state = ready ? SW_SSL_STATE_READY : 0;
                socket.ssl_renegotiation = 0;socket.ssl_handshake_buffer_set = buffered;
                callback(ssl,where,ret);
                require(socket.ssl_renegotiation == ((where & SSL_CB_HANDSHAKE_START) != 0 && ready));
                require(socket.ssl_handshake_buffer_set == (buffered ||
                    ((where & SSL_CB_ACCEPT_LOOP) == SSL_CB_ACCEPT_LOOP && split)));
            }
            std::cout << "info-callback " << where << ' ' << ready << ' ' << buffered << ' ' << split
                      << ' ' << (int)socket.ssl_renegotiation << ' ' << (int)socket.ssl_handshake_buffer_set << '\n';
            // Native ex_data owner remains live through SSL/BIO destruction.
            SSL_free(ssl);
        }
    }
}

static void tls_peer(Certificate &cert, uint32_t protocols, int offer, int verify_mode, std::ostream &sink = std::cout,
                     const Certificate *installed_authority = nullptr, bool dh = false, const char *curve = nullptr) {
    bool h2 = offer == 1;
    CertificateFile trust_file(installed_authority ? installed_authority->certificate : nullptr);
    swoole::SSLContext server_ctx{}, client_ctx{};
    server_ctx.protocols = client_ctx.protocols = protocols;
    server_ctx.http_v2 = 1;client_ctx.http = 1;client_ctx.http_v2 = h2;
    if (curve) {
        server_ctx.ecdh_curve = curve;
        server_ctx.ciphers = client_ctx.ciphers = "ECDHE-RSA-AES128-GCM-SHA256";
    }
    require(server_ctx.create() && client_ctx.create());
    if (dh) {
        const char *reference = std::getenv("SWR_TLS_REFERENCE");require(reference);
        // Explicit test configuration accepts the pinned DH fixture, including
        // its original group size; this is not the production default policy.
        SSL_CTX_set_security_level(server_ctx.context,0);SSL_CTX_set_security_level(client_ctx.context,0);
        server_ctx.dhparam = std::string(reference) + "/tests/include/ssl_certs/dhparams.pem";
        server_ctx.ciphers = client_ctx.ciphers = "DHE-RSA-AES128-GCM-SHA256";
        require(server_ctx.set_ciphers() && client_ctx.set_ciphers());
    }
    require(SSL_CTX_use_certificate(server_ctx.context, cert.certificate) == 1);
    require(SSL_CTX_use_PrivateKey(server_ctx.context, cert.key) == 1);
    if (installed_authority) {
        client_ctx.client_cert_file = trust_file.path;client_ctx.verify_depth = 4;
        require(client_ctx.set_client_certificate());
        auto callback = SSL_CTX_get_verify_callback(client_ctx.context);
        require(callback && callback(0, nullptr) == 1 && callback(1, nullptr) == 1);
        require(SSL_CTX_get_verify_mode(client_ctx.context) == SSL_VERIFY_PEER);
        require(SSL_CTX_get_verify_depth(client_ctx.context) == 4);
        require(sk_X509_NAME_num(SSL_CTX_get_client_CA_list(client_ctx.context)) == 1);
    } else {
        SSL_CTX_set_verify(client_ctx.context, SSL_VERIFY_PEER, nullptr);
        if (verify_mode != 1) require(X509_STORE_add_cert(SSL_CTX_get_cert_store(client_ctx.context), cert.certificate) == 1);
    }
    swoole::network::Socket server_socket{}, client_socket{};
    server_socket.ssl_state = client_socket.ssl_state = SW_SSL_STATE_READY;
    SSL *server = SSL_new(server_ctx.context), *client = SSL_new(client_ctx.context);
    require(server && client);
    require(SSL_set_ex_data(server, swoole_ssl_get_ex_connection_index(), &server_socket) == 1);
    require(SSL_set_ex_data(client, swoole_ssl_get_ex_connection_index(), &client_socket) == 1);
    BIO *server_io = nullptr, *client_io = nullptr;
    require(BIO_new_bio_pair(&server_io, 8192, &client_io, 8192) == 1);
    SSL_set_bio(server, server_io, server_io);SSL_set_bio(client, client_io, client_io);
    SSL_set_accept_state(server);SSL_set_connect_state(client);
    if (offer == 2) {
        const unsigned char unknown[] = {3, 'm', '2', '1'};
        require(SSL_set_alpn_protos(client, unknown, sizeof(unknown)) == 0);
    }
    require(SSL_set1_host(client, verify_mode == 2 ? "wrong-host.invalid" : "localhost") == 1);
    bool completed = false, rejected = false;
    for (int i = 0; i < 100; ++i) {
        int c = handshake_step(client);
        if (c < 0) {rejected = true;break;}
        int s = handshake_step(server);
        if (s < 0) {rejected = true;break;}
        if (c == 1 && s == 1) {completed = true;break;}
    }
    long verified = SSL_get_verify_result(client);
    if (installed_authority) {
        // Original registered callback permits the handshake, retaining a later
        // verification error for protected consumers. Do not "correct" it to ok.
        require(completed && !rejected);
        require(verify_mode == 0 ? verified == X509_V_OK : verified != X509_V_OK);
    } else require(verify_mode == 0 ? completed && !rejected && verified == X509_V_OK : rejected && verified != X509_V_OK);
    sink << (curve ? "tls-curve " : dh ? "tls-dh " : installed_authority ? "tls-native-verify-callback " : "tls ") << protocols << ' ' << offer << ' ' << verify_mode << ' ' << completed << ' ' << verified
              << ' ' << (int)server_socket.ssl_renegotiation << ' ' << (int)client_socket.ssl_renegotiation;
    if (completed) {
        const unsigned char *selected;unsigned int length;
        SSL_get0_alpn_selected(client, &selected, &length);
        std::string alpn;
        if (length) alpn.assign((const char *) selected, length);
        require(alpn == (offer == 2 ? "" : h2 ? "h2" : "http/1.1"));
        const char message[] = "M21 native callback lifetime";
        char output[sizeof(message)] = {};
        require(SSL_write(client, message, sizeof(message)) == (int) sizeof(message));
        require(SSL_read(server, output, sizeof(output)) == (int) sizeof(message));
        require(std::memcmp(message, output, sizeof(message)) == 0);
        for (int i = 0; i < 10; ++i) {
            int c = SSL_shutdown(client);int s = SSL_shutdown(server);
            if (c == 1 && s == 1) break;
        }
        require(SSL_get_shutdown(client) == (SSL_SENT_SHUTDOWN | SSL_RECEIVED_SHUTDOWN));
        require(SSL_get_shutdown(server) == (SSL_SENT_SHUTDOWN | SSL_RECEIVED_SHUTDOWN));
        sink << ' ' << SSL_get_version(client) << ' ' << alpn << ' ' << SSL_get_shutdown(client) << ' ' << SSL_get_shutdown(server);
        if (curve) {
            const char *cipher = SSL_get_cipher_name(client);
            require(std::strcmp(cipher,"ECDHE-RSA-AES128-GCM-SHA256") == 0);
            sink << ' ' << curve << ' ' << cipher;
#ifdef SSL_get_negotiated_group
            int group = SSL_get_negotiated_group(client);
            if (std::strcmp(curve,"prime256v1") == 0) require(group == NID_X9_62_prime256v1);
            sink << ' ' << group;
#endif
        }
        if (dh) {
            const char *cipher = SSL_get_cipher_name(client);
            require(std::strcmp(cipher,"DHE-RSA-AES128-GCM-SHA256") == 0);
            sink << ' ' << cipher;
        }
    }
    sink << '\n';
    // Socket callback/ex_data custody outlives both SSL/BIO destruction operations.
    SSL_free(client);SSL_free(server);
}

#ifdef SW_SUPPORT_DTLS
static void listen_empty_and_malformed() {
    auto ctx = std::make_shared<swoole::SSLContext>();ctx->protocols = SW_SSL_DTLS;require(ctx->create());
    swoole::network::Socket socket{};socket.fd = -1;
    socket.info.addr.inet_v4.sin_family = AF_INET;
    socket.info.addr.inet_v4.sin_port = htons(12345);
    socket.info.addr.inet_v4.sin_addr.s_addr = htonl(0x7f000001);
    socket.ssl = SSL_new(ctx->context);require(socket.ssl);
    require(SSL_set_ex_data(socket.ssl, swoole_ssl_get_ex_connection_index(), &socket) == 1);
    SSL_set_accept_state(socket.ssl);
    {
        swoole::dtls::Session session(&socket, ctx);
        BIO *bio = BIO_new(swoole::dtls::BIO_get_methods());require(bio);
        BIO_set_data(bio, &session);BIO_set_init(bio, 1);SSL_set_bio(socket.ssl, bio, bio);
        bool empty = session.listen();
        std::cout << "dtls-empty " << empty << ' ' << session.listened << ' ' << session.rxqueue.size() << '\n';
        require(empty && !session.listened);
        session.append("malformed-M21-record", 20);
        bool malformed = session.listen();
        std::cout << "dtls-malformed " << malformed << ' ' << session.listened << ' ' << session.rxqueue.size() << '\n';
        session.listened = true;
        require(!session.listen());
        std::cout << "dtls-already-listened 0\n";
        SSL_free(socket.ssl);socket.ssl = nullptr;
    }
    swoole::dtls::BIO_meth_free();
}

static void dtls_session_init() {
    auto check = [](bool ok, const char *label) { if (!ok) { std::cerr << "dtls-init assertion: " << label << '\n'; std::abort(); } };
    int fds[2];check(socketpair(AF_UNIX, SOCK_DGRAM, 0, fds) == 0,"socketpair");
    auto ctx = std::make_shared<swoole::SSLContext>();ctx->protocols = SW_SSL_DTLS;check(ctx->create(),"context create");
    swoole::network::Socket socket{};socket.fd = fds[0];
    {
        swoole::dtls::Session session(&socket,ctx);
        check(session.init(),"session init result");check(socket.ssl && socket.dtls && socket.ssl_state == 0,"SSL/dtls/state after init");
        BIO *bio = SSL_get_rbio(socket.ssl);SSL *ssl = socket.ssl;
        check(bio && bio == SSL_get_wbio(socket.ssl) && BIO_get_data(bio) == &session && BIO_get_init(bio),"BIO identity and init");
        if (SSL_get_ex_data(socket.ssl,swoole_ssl_get_ex_connection_index()) != &socket) {
            const char *library = std::getenv("SWR_TLS_NATIVE_LIBRARY");
            void *handle = library ? dlopen(library,RTLD_LAZY | RTLD_LOCAL) : nullptr;
            auto getter = handle ? reinterpret_cast<int (*)()>(dlsym(handle,"_Z34swoole_ssl_get_ex_connection_indexv")) : nullptr;
            std::cerr << "dtls-init native authority: fixture-index=" << swoole_ssl_get_ex_connection_index()
                      << " library-index=" << (getter ? getter() : -1)
                      << " library-index-owns-socket=" << (getter && SSL_get_ex_data(socket.ssl,getter()) == &socket) << '\n';
            if (handle) dlclose(handle);
        }
        check(SSL_get_ex_data(socket.ssl,swoole_ssl_get_ex_connection_index()) == &socket,"ex_data owner");
        // The already-created branch must not observe the context or mutate errors.
        session.ctx.reset();swoole_set_last_error(1234567);
        check(!session.init(),"already present rejects");check(swoole_get_last_error() == 1234567,"already present preserves last error");
        check(socket.ssl == ssl && SSL_get_rbio(ssl) == bio && socket.dtls,"already present preserves objects");
        std::cout << "dtls-session-init 1 1 1 1 0 1234567\n";
        SSL_free(socket.ssl);socket.ssl = nullptr;
    }
    close(fds[0]);close(fds[1]);swoole::dtls::BIO_meth_free();
}

static void drain_datagrams(int fd, swoole::dtls::Session &session) {
    char packet[65535];
    for (int i = 0; i < 64; ++i) {
        ssize_t length = recv(fd, packet, sizeof(packet), MSG_DONTWAIT);
        if (length < 0) { require(errno == EAGAIN || errno == EWOULDBLOCK);return; }
        session.append(packet, length);
    }
    std::abort();
}

static void dtls_peer(Certificate &cert) {
    int fds[2];require(socketpair(AF_UNIX, SOCK_DGRAM, 0, fds) == 0);
    require(fcntl(fds[0], F_SETFL, O_NONBLOCK) == 0);require(fcntl(fds[1], F_SETFL, O_NONBLOCK) == 0);
    auto server_ctx = std::make_shared<swoole::SSLContext>();
    auto client_ctx = std::make_shared<swoole::SSLContext>();
    server_ctx->protocols = client_ctx->protocols = SW_SSL_DTLS;
    require(server_ctx->create() && client_ctx->create());
    require(SSL_CTX_use_certificate(server_ctx->context, cert.certificate) == 1);
    require(SSL_CTX_use_PrivateKey(server_ctx->context, cert.key) == 1);
    require(X509_STORE_add_cert(SSL_CTX_get_cert_store(client_ctx->context), cert.certificate) == 1);
    SSL_CTX_set_verify(client_ctx->context, SSL_VERIFY_PEER, nullptr);
    swoole::network::Socket server_socket{}, client_socket{};
    server_socket.fd = fds[0];client_socket.fd = fds[1];
    for (auto *sock : {&server_socket, &client_socket}) {
        // Custom BIO peer identity is native Address storage; no IP listener exists.
        sock->info.addr.inet_v4.sin_family = AF_INET;
        sock->info.addr.inet_v4.sin_port = htons(sock == &server_socket ? 12345 : 12346);
        sock->info.addr.inet_v4.sin_addr.s_addr = htonl(0x7f000001);
        sock->ssl = SSL_new(sock == &server_socket ? server_ctx->context : client_ctx->context);
        require(sock->ssl);
        require(SSL_set_ex_data(sock->ssl, swoole_ssl_get_ex_connection_index(), sock) == 1);
    }
    SSL_set_accept_state(server_socket.ssl);SSL_set_connect_state(client_socket.ssl);
    require(SSL_set1_host(client_socket.ssl, "localhost") == 1);
    {
        swoole::dtls::Session server(&server_socket, server_ctx), client(&client_socket, client_ctx);
        for (auto *session : {&server, &client}) {
            BIO *bio = BIO_new(swoole::dtls::BIO_get_methods());require(bio);
            BIO_set_data(bio, session);BIO_set_init(bio, 1);
            SSL_set_bio(session->socket->ssl, bio, bio);
        }
        bool client_done = false, server_done = false;
        for (int i = 0; i < 1000; ++i) {
            int c = handshake_step(client_socket.ssl);require(c >= 0);client_done = c == 1;
            drain_datagrams(fds[0], server);
            if (!server.listened) require(server.listen());
            if (server.listened) {
                int result = handshake_step(server_socket.ssl);require(result >= 0);server_done = result == 1;
            }
            drain_datagrams(fds[1], client);
            if (client_done && server_done) break;
        }
        require(client_done && server_done && server.listened);
        require(SSL_get_verify_result(client_socket.ssl) == X509_V_OK);
        const char message[] = "M21 datagram cookie/listen callback";char output[sizeof(message)] = {};
        require(SSL_write(client_socket.ssl, message, sizeof(message)) == (int) sizeof(message));
        drain_datagrams(fds[0], server);
        require(SSL_read(server_socket.ssl, output, sizeof(output)) == (int) sizeof(message));
        require(std::memcmp(output, message, sizeof(message)) == 0);
        for (int i = 0; i < 16; ++i) {
            int c = SSL_shutdown(client_socket.ssl);drain_datagrams(fds[0], server);
            int result = SSL_shutdown(server_socket.ssl);drain_datagrams(fds[1], client);
            if (c == 1 && result == 1) break;
        }
        require(SSL_get_shutdown(client_socket.ssl) == (SSL_SENT_SHUTDOWN | SSL_RECEIVED_SHUTDOWN));
        require(SSL_get_shutdown(server_socket.ssl) == (SSL_SENT_SHUTDOWN | SSL_RECEIVED_SHUTDOWN));
        std::cout << "dtls-peer " << server.listened << ' ' << SSL_get_version(client_socket.ssl)
                  << ' ' << SSL_get_verify_result(client_socket.ssl) << ' ' << sizeof(message) << ' '
                  << SSL_get_shutdown(client_socket.ssl) << ' ' << SSL_get_shutdown(server_socket.ssl) << '\n';
        SSL_free(client_socket.ssl);SSL_free(server_socket.ssl);
        client_socket.ssl = server_socket.ssl = nullptr;
    }
    close(fds[0]);close(fds[1]);swoole::dtls::BIO_meth_free();
}

#endif

int main(int argc, char **argv) {
    if (argc == 2 && std::string(argv[1]) == "--identify") return 0;
    swoole_init();
    if (argc == 2 && std::string(argv[1]) == "--callback-binding") {
#if defined(SW_SUPPORT_DTLS) && !defined(OPENSSL_IS_BORINGSSL)
        const BIO_METHOD *methods = swoole::dtls::BIO_get_methods();require(methods);
        auto callback = BIO_meth_get_callback_ctrl(methods);
        std::cout << "{\"supported\":true,\"has_callback_ctrl\":" << (callback ? "true" : "false")
                  << ",\"callback_is_public_dispatcher\":" << (callback == ::BIO_callback_ctrl ? "true" : "false") << "}\n";
        swoole::dtls::BIO_meth_free();
#else
        std::cout << "{\"supported\":false}\n";
#endif
        // Inspect the registered pointer only; never invoke callback-control.
        swoole_clean();return 0;
    }
    std::cout << "openssl " << OpenSSL_version(OPENSSL_VERSION) << '\n';
    {
        password_callback();
        info_callback();
        Certificate cert, unrelated_authority;
        for (int verify : {0, 1, 2}) tls_peer(cert,SW_SSL_TLSv1_2,0,verify,std::cout,nullptr,true);
#if !defined(OPENSSL_NO_ECDH) && (defined(SSL_CTX_set1_curves_list) || defined(SSL_CTRL_SET_CURVES_LIST))
        for (const char *curve : {"auto","prime256v1"})
            for (int verify : {0,1,2}) tls_peer(cert,SW_SSL_TLSv1_2,0,verify,std::cout,nullptr,false,curve);
#endif
        for (uint32_t protocol : {SW_SSL_TLSv1_2, SW_SSL_TLSv1_3}) {
            for (int offer : {0, 1}) for (int verify : {0, 1, 2}) tls_peer(cert, protocol, offer, verify);
            tls_peer(cert, protocol, 2, 0);
            for (int verify : {0, 1, 2})
                tls_peer(cert, protocol, 0, verify, std::cout, verify == 1 ? &unrelated_authority : &cert);
        }
#ifdef SW_SUPPORT_DTLS
        dtls_session_init();
        listen_empty_and_malformed();
        dtls_peer(cert);
#endif
        // Every SSL/BIO/Session from the preceding peers has been destroyed.
        // Native destroy permits lazy re-init; it is not one-shot Rust global state.
        for (int round = 0; round < 3; ++round) {
            int old_connection = swoole_ssl_get_ex_connection_index();
            int old_port = swoole_ssl_get_ex_port_index();
            swoole_ssl_destroy();swoole_ssl_destroy();
            {
                swoole::SSLContext reinitialized{};require(reinitialized.create());
                require(swoole_ssl_get_ex_connection_index() >= 0);
                require(swoole_ssl_get_ex_port_index() >= 0);
                require(swoole_ssl_get_ex_connection_index() != old_connection);
                require(swoole_ssl_get_ex_port_index() != old_port);
            }
            tls_peer(cert, SW_SSL_TLSv1_2, round % 2, 0);
#ifdef SW_SUPPORT_DTLS
            const BIO_METHOD *methods = swoole::dtls::BIO_get_methods();require(methods);
            require(methods == swoole::dtls::BIO_get_methods());
            BIO *bio = BIO_new(methods);require(bio);BIO_free(bio);
            swoole::dtls::BIO_meth_free();swoole::dtls::BIO_meth_free();
#endif
            std::cout << "native-lifecycle " << round << " 1 1\n";
        }
        // Global SSL indexes are already initialized and remain unchanged until
        // every thread joins. Each SSLContext/Socket/SSL/BIO/output is thread-local;
        // the immutable certificate fixture outlives all of them.
        std::array<std::string, 4> traces;
        std::array<std::thread, 4> threads;
        for (size_t i = 0; i < threads.size(); ++i) {
            threads[i] = std::thread([&cert, &traces, i] {
                std::ostringstream trace;
                tls_peer(cert, i % 2 ? SW_SSL_TLSv1_3 : SW_SSL_TLSv1_2, i % 2, 0, trace);
                traces[i] = trace.str();
            });
        }
        for (auto &thread : threads) thread.join();
        for (size_t i = 0; i < traces.size(); ++i) std::cout << "native-thread " << i << ' ' << traces[i];
    }
    swoole_clean();
}
