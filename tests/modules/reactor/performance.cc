// Actual private CMake lib-swoole consumers; timing needs an exclusive lease.
#include "swoole.h"
#include "swoole_reactor.h"
#include <chrono>
#include <iostream>
using namespace swoole;

struct Progress {
    uint64_t count = 0, target;
};

static int readable(Reactor *reactor, Event *) {
    auto &progress = *static_cast<Progress *>(reactor->ptr);
    if (++progress.count == progress.target) reactor->running = false;
    return SW_OK;
}

int main(int argc, char **argv) {
    if (argc != 4) return 2;
    std::string workload = argv[1], backend = argv[2];
    uint64_t iterations = std::stoull(argv[3]);
    if (!iterations || iterations > 1000000000) return 2;
    Reactor::Type type;
    if (backend == "poll") type = Reactor::TYPE_POLL;
#ifdef HAVE_EPOLL
    else if (backend == "epoll") type = Reactor::TYPE_EPOLL;
#endif
#ifdef HAVE_KQUEUE
    else if (backend == "kqueue") type = Reactor::TYPE_KQUEUE;
#endif
    else return 2;
    if (workload != "ready" && workload != "interest" && workload != "write") return 2;
    swoole_init();
    int errors = 0;
    uint64_t checksum = 0;
    int64_t elapsed = 0;
    {
        Reactor reactor(8, type);
        if (!reactor.ready() || reactor.type_ != type ||
            (type != Reactor::TYPE_POLL && fcntl(reactor.native_handle, F_GETFD) < 0)) return 3;
        int pair[2];
        if (socketpair(AF_UNIX, SOCK_DGRAM, 0, pair) != 0) return 3;
        auto *socket = make_socket(pair[0], SW_FD_USER);
        if (!socket || reactor.add(socket, SW_EVENT_READ) != SW_OK) return 3;
        Progress progress{0, iterations};
        reactor.ptr = &progress;
        reactor.set_handler(SW_FD_USER, SW_EVENT_READ, readable);
        char payload[32], received[32];
        for (size_t i = 0; i < sizeof(payload); ++i) payload[i] = static_cast<char>(i);
        if (workload == "ready" && send(pair[1], payload, sizeof(payload), 0) != sizeof(payload)) return 3;
        // Warm native write setup before measuring its steady full-send path.
        if (workload == "write" &&
            (reactor.write(&reactor, socket, payload, sizeof(payload)) != sizeof(payload) ||
             recv(pair[1], received, sizeof(received), 0) != sizeof(received))) return 3;
        auto start = std::chrono::steady_clock::now();
        if (workload == "ready") {
            if (reactor.wait() != SW_OK) ++errors;
            checksum = progress.count;
        } else if (workload == "interest") {
            volatile int requested = SW_EVENT_READ;
            for (uint64_t i = 0; i < iterations; ++i) {
                if (reactor.add_event(socket, static_cast<EventType>(requested)) != SW_OK) ++errors;
                checksum += socket->events;
            }
        } else {
            for (uint64_t i = 0; i < iterations; ++i) {
                if (reactor.write(&reactor, socket, payload, sizeof(payload)) != sizeof(payload)) ++errors;
                if (recv(pair[1], received, sizeof(received), 0) != sizeof(received) ||
                    memcmp(payload, received, sizeof(payload)) != 0) ++errors;
                checksum += sizeof(payload);
            }
        }
        elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-start).count();
        if (workload == "ready" &&
            (recv(pair[0], received, sizeof(received), 0) != sizeof(received) ||
             memcmp(payload, received, sizeof(payload)) != 0)) ++errors;
        uint64_t expected = iterations * (workload == "interest" ? SW_EVENT_READ : workload == "write" ? sizeof(payload) : 1);
        if (checksum != expected || socket->events != SW_EVENT_READ || socket->out_buffer != nullptr) ++errors;
        if (reactor.del(socket) != SW_OK || reactor.get_event_num() != 0 || !socket->removed) ++errors;
        socket->free();
        close(pair[1]);
    }
    swoole_clean();
    std::cout << "{\"workload\":\"" << workload << "\",\"backend\":\"" << backend
              << "\",\"iterations\":" << iterations << ",\"checksum\":" << checksum
              << ",\"elapsed_ns\":" << elapsed << ",\"errors\":" << errors << "}\n";
    return errors ? 1 : 0;
}
