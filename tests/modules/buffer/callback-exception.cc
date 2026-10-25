#include "swoole.h"
#include "swoole_buffer.h"
#include <cstdlib>
#include <cstring>
#include <exception>
#include <memory>

swoole::Global SwooleG{};
static void throwing_callback(swoole::BufferChunk *) { throw 1; }
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    std::set_terminate([] { std::_Exit(77); });
    auto buffer = std::make_unique<swoole::Buffer>(4);
    if (std::strcmp(argv[1], "native") == 0) {
        buffer->alloc(swoole::BufferChunk::TYPE_CLOSE, 0)->destroy = throwing_callback;
    } else {
        buffer->append("abc", 3);
        buffer->front()->destroy = throwing_callback;
    }
    try {
        if (std::strcmp(argv[1], "teardown") == 0) buffer.reset();
        else buffer->pop();
    } catch (...) { std::_Exit(42); }
    std::_Exit(0);
}
