// SPDX-License-Identifier: Apache-2.0
// Narrow support adapter; upstream protocol/ssl.cpp and its assertions are unchanged.
#include "test_core.h"
#include <cstdlib>
namespace swoole { namespace test {
NullStream null_stream;
std::reference_wrapper<std::ostream> debug_output = std::ref(std::cout);
std::string get_ssl_dir() { return std::string(std::getenv("SWR_TLS_REFERENCE")) + "/tests/include/ssl_certs"; }
} }
int main(int argc, char **argv) {
    ::testing::InitGoogleTest(&argc, argv);
    swoole_init();
    int result = RUN_ALL_TESTS();
    swoole_clean();
    return result;
}
