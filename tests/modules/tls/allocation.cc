// SPDX-License-Identifier: Apache-2.0
// Controlled replaceable C++ operator-new failures, not process/PHP/malloc OOM.
#include "swoole_server.h"
#include <cstdlib>
#include <iostream>
#include <new>
#include <string>

struct AllocationTrace { bool active = false;size_t fail_at = 0, calls = 0, sizes[64] = {}; };
static thread_local AllocationTrace allocation;
void *operator new(std::size_t size) {
    if (allocation.active) {
        size_t index = allocation.calls++;
        if (index < 64) allocation.sizes[index] = size;
        if (allocation.fail_at && allocation.calls == allocation.fail_at) throw std::bad_alloc();
    }
    void *pointer = std::malloc(size ? size : 1);
    if (!pointer) throw std::bad_alloc();
    return pointer;
}
void *operator new[](std::size_t size) { return ::operator new(size); }
void operator delete(void *pointer) noexcept { std::free(pointer); }
void operator delete[](void *pointer) noexcept { std::free(pointer); }
void operator delete(void *pointer, std::size_t) noexcept { std::free(pointer); }
void operator delete[](void *pointer, std::size_t) noexcept { std::free(pointer); }
static void require(bool value) { if (!value) std::abort(); }

int main(int argc, char **argv) {
    if (argc == 2 && std::string(argv[1]) == "--identify") return 0;
#ifndef SW_SUPPORT_DTLS
    std::cerr << "unsupported: DTLS callback allocation profile required\n";return 77;
#else
    swoole_init();
    { swoole::SSLContext warm{};require(warm.create()); }
    const char *reference = std::getenv("SWR_TLS_REFERENCE");require(reference);
    const std::string missing = std::string(reference) + "/tests/include/ssl_certs/does-not-exist-m21-cert.pem";
    // SSLContext's warnings are formatted in Rust (crates/tls), so only the DTLS
    // BIO's native unknown-command warning still allocates through operator new.
    const int scenarios[] = {4};
    for (int scenario : scenarios) {
        for (size_t fail_at = 0; fail_at <= 6; ++fail_at) {
            swoole::SSLContext ctx{};
            if (scenario == 1 || scenario == 3 || scenario >= 5) {ctx.context = SSL_CTX_new(TLS_method());require(ctx.context);}
            if (scenario == 1) ctx.ciphers = "M21-nonexistent-cipher";
            else if (scenario == 3) ctx.cafile = missing;
            else if (scenario == 5) {ctx.client_cert_file = missing;ctx.verify_depth = 3;}
            else if (scenario == 9) ctx.ecdh_curve = "M21-nonexistent-curve";
            else if (scenario >= 6) {
                ctx.dhparam = scenario == 6 ? missing : std::string(reference) +
                    (scenario == 7 ? "/tests/include/ssl_certs/ca.crt" : "/tests/include/ssl_certs/dhparams.pem");
                if (scenario == 8) SSL_CTX_set_security_level(ctx.context,5);
            }
            else ctx.cert_file = missing;
            swoole::network::Socket socket{};
            swoole::dtls::Session session(&socket, {});
            BIO *bio = nullptr;
            if (scenario == 4) {
                bio = BIO_new(swoole::dtls::BIO_get_methods());require(bio);
                BIO_set_data(bio, &session);BIO_set_init(bio, 1);
            }
            sw_logger()->set_level(scenario == 2 ? SW_LOG_ERROR : SW_LOG_WARNING);
            allocation = AllocationTrace{};allocation.fail_at = fail_at;
            bool result = false, threw = false;
            ERR_clear_error();errno = 71;
            allocation.active = true;
            try {
                if (scenario == 4) result = swoole::dtls::BIO_ctrl(bio, -12345, 0, nullptr) != 0;
                else result = scenario == 1 ? ctx.set_ciphers() : scenario == 3 ? ctx.set_capath() : scenario == 5 ? ctx.set_client_certificate() : scenario == 9 ? ctx.set_ecdh_curve() : scenario >= 6 ? ctx.set_dhparam() : ctx.create();
            } catch (const std::bad_alloc &) { threw = true; }
            allocation.active = false;
            int saved_errno = errno;
            if (bio) BIO_free(bio);  // Native callback storage outlives its BIO.
            require(allocation.calls <= 64);
            if (scenario < 2 || scenario >= 4) {
                // Proves this actual binary/library observes the formatter's C++
                // allocation; unavailable interposition cannot silently pass.
                if (!fail_at) require(allocation.calls > 0 && !threw);
                if (fail_at == 1) require(threw && allocation.calls == 1);
            } else require(!threw && allocation.calls == 0);
            std::cout << "native-new " << scenario << ' ' << fail_at << ' ' << result << ' ' << threw
                      << ' ' << saved_errno << ' ' << allocation.calls << ' ';
            for (size_t i = 0; i < allocation.calls; ++i) std::cout << allocation.sizes[i] << ',';
            std::cout << '\n';
        }
    }
    swoole::dtls::BIO_meth_free();
    sw_logger()->set_level(SW_LOG_WARNING);swoole_clean();
#endif
}
