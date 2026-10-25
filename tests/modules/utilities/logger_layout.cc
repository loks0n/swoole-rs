// Compile independently against each exact engine SDK; no Logger construction,
// linking to a production DSO, private fields or guessed platform dimensions.
#include <cstdio>
#include <mutex>
#include <string>
#include "swoole_log.h"
int main() {
    std::printf("{\"sizeof_logger\":%zu,\"alignof_logger\":%zu}\n",
                sizeof(swoole::Logger), alignof(swoole::Logger));
}
