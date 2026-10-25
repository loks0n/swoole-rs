// SPDX-License-Identifier: Apache-2.0
// Check-only by default. --measure requires a separately granted host lease.
#include "swoole_server.h"
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>

static void require(bool value) { if (!value) std::abort(); }
static bool measure = false;
using Clock = std::chrono::steady_clock;

// Fixture allocation, printing and destruction surround, rather than enter, windows.
template<class F> static void workload(const char *name, uint64_t count, uint64_t expected, F function) {
    Clock::time_point start;
    if (measure) start = Clock::now();
    uint64_t checksum = function();
    uint64_t nanos = 0;
    if (measure) nanos = std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - start).count();
    require(checksum == expected);
    std::cout << name << ' ' << count << ' ' << checksum;
    if (measure) std::cout << ' ' << nanos;
    std::cout << '\n';
}

#ifdef SW_SUPPORT_DTLS
static void datagram_reads(const char *name, int requested, bool peek) {
    constexpr uint64_t count = 20000;
    swoole::network::Socket socket{};
    swoole::dtls::Session session(&socket, {});
    char input[64];std::memset(input, 'x', sizeof(input));
    for (uint64_t i = 0; i <= count; ++i) session.append(input, sizeof(input));
    BIO *bio = BIO_new(swoole::dtls::BIO_get_methods());require(bio);
    BIO_set_data(bio, &session);BIO_set_init(bio, 1);
    char warm[64] = {};
    if (peek) { session.peek_mode = true;require(::BIO_read(bio, warm, requested) == requested);session.peek_mode = false; }
    require(::BIO_read(bio, warm, requested) == requested);
    const uint64_t unit = requested + (unsigned char)'x';
    workload(name, count, count * unit * (peek ? 2 : 1), [&] {
        uint64_t checksum = 0;
        char output[64] = {};
        for (uint64_t i = 0; i < count; ++i) {
            if (peek) {
                session.peek_mode = true;
                int length = ::BIO_read(bio, output, requested);
                checksum += length + (unsigned char)output[requested - 1];
                session.peek_mode = false;
            }
            int length = ::BIO_read(bio, output, requested);
            checksum += length + (unsigned char)output[requested - 1];
        }
        return checksum;
    });
    require(session.rxqueue.empty());BIO_free(bio);
}

static void datagram_controls() {
    constexpr uint64_t count = 100000;
    swoole::network::Socket socket{};
    swoole::dtls::Session session(&socket, {});
    char input[32] = {};
    for (int i = 0; i < 8; ++i) session.append(input, sizeof(input));
    BIO *bio = BIO_new(swoole::dtls::BIO_get_methods());require(bio);
    BIO_set_data(bio, &session);BIO_set_init(bio, 1);
    require(::BIO_ctrl(bio, BIO_CTRL_PENDING, 0, nullptr) == 256);
    require(::BIO_ctrl(bio, BIO_CTRL_EOF, 0, nullptr) == 0);
    workload("bio-pending-eof", count, count * 256, [&] {
        uint64_t checksum = 0;
        for (uint64_t i = 0; i < count; ++i) {
            checksum += ::BIO_ctrl(bio, BIO_CTRL_PENDING, 0, nullptr);
            checksum += ::BIO_ctrl(bio, BIO_CTRL_EOF, 0, nullptr);
        }
        return checksum;
    });
    require(session.rxqueue.size() == 8);BIO_free(bio);
}
#endif

static void contexts(bool configured) {
    constexpr uint64_t count = 200;
    // Context/OpenSSL allocation, trust-path loading and free ARE this workload.
    {
        swoole::SSLContext warm{};warm.protocols = SW_SSL_TLSv1_2;
        if (configured) {warm.ciphers = "ECDHE-RSA-AES128-GCM-SHA256";warm.prefer_server_ciphers = 1;warm.ecdh_curve = "prime256v1";}
        require(warm.create());
    }
    workload(configured ? "context-cipher-preference" : "context-default", count, count, [&] {
        uint64_t checksum = 0;
        for (uint64_t i = 0; i < count; ++i) {
            swoole::SSLContext ctx{};ctx.protocols = SW_SSL_TLSv1_2;
            if (configured) {
                ctx.ciphers = "ECDHE-RSA-AES128-GCM-SHA256";ctx.prefer_server_ciphers = 1;
                ctx.ecdh_curve = "prime256v1";
            }
            bool result = ctx.create();
            bool options = result && ctx.context && (!configured || (SSL_CTX_get_options(ctx.context) & SSL_OP_CIPHER_SERVER_PREFERENCE));
            checksum += result && options;
        }
        return checksum;
    });
}

int main(int argc, char **argv) {
    if (argc == 2 && std::string(argv[1]) == "--identify") return 0;
    if (argc > 2 || (argc == 2 && std::string(argv[1]) != "--measure" && std::string(argv[1]) != "--check")) return 2;
    measure = argc == 2 && std::string(argv[1]) == "--measure";
#ifndef SW_SUPPORT_DTLS
    std::cerr << "unsupported: actual DTLS configuration required\n";return 77;
#else
    swoole_init();
    {
        // Warm native globals before any window, without timing/check output.
        swoole::SSLContext warm{};require(warm.create());
        datagram_reads("bio-read-full", 64, false);
        datagram_reads("bio-read-truncated", 7, false);
        datagram_reads("bio-peek-consume", 64, true);
        datagram_controls();
        contexts(false);contexts(true);
    }
    swoole::dtls::BIO_meth_free();swoole_clean();
#endif
}
