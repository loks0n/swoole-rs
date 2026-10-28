#include <poll.h>
#include <unistd.h>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <algorithm>
#include <iostream>
#include <tuple>
#include <new>
#include <unordered_map>
#include <utility>
#include <vector>
#include "swoole_rs_reactor.h"
constexpr int SW_EVENT_READ = 1 << 9, SW_EVENT_WRITE = 1 << 10, SW_EVENT_ERROR = 1 << 11;
struct Socket { int fd, events; };
// The original body reads the std map, the selected one the Rust registry; add() fills both.
struct Reactor {
    std::unordered_map<int, Socket *> sockets;
    swr_v1_reactor_registry *registry = swr_v1_reactor_registry_new();
    int max_event_num = 0;
    ~Reactor() { swr_v1_reactor_registry_free(registry); }
    const std::unordered_map<int, Socket *> &get_sockets() const { return sockets; }
    void add(Socket *socket) {
        sockets.emplace(socket->fd, socket);
        assert(swr_v1_reactor_registry_put(registry, socket->fd, socket, socket->events) == 0);
    }
};
// Poll order is each map's iteration order, so compare the entries as sets.
template <class Snapshot>
std::vector<std::tuple<int, short, short, Socket *>> entries(const Snapshot &snapshot, int n) {
    std::vector<std::tuple<int, short, short, Socket *>> result;
    for (int i = 0; i < n; ++i) {
        result.emplace_back(snapshot.events_[i].fd, snapshot.events_[i].events, snapshot.events_[i].revents, snapshot.event_sockets_[i]);
    }
    std::sort(result.begin(), result.end());
    return result;
}
struct ReactorImpl { Reactor *reactor_; explicit ReactorImpl(Reactor *r): reactor_(r) {} };
int16_t translate_events_to_poll_original(int);
int16_t translate_events_to_poll_selected(int);
#include "poll-snapshot.inc"
int main() {
    const auto layout = swr_v1_reactor_poll_layout();
    assert(layout.size == sizeof(pollfd) && layout.alignment == alignof(pollfd));
    assert(layout.fd == offsetof(pollfd, fd) && layout.events == offsetof(pollfd, events));
    assert(layout.revents == offsetof(pollfd, revents));
    size_t translations = 0, snapshots = 0;
    for (unsigned i = 0; i < 65536; ++i) {
        const auto input = static_cast<int16_t>(i);
        assert(translate_events_to_poll_original(input) == translate_events_to_poll_selected(input));
        assert(translate_events_from_poll_original(input) == translate_events_from_poll_selected(input));
        ++translations;
    }
    for (int n : {0, 1, 3, 17, 65}) {
        Reactor reactor;
        SnapshotOriginal original(&reactor, n);
        SnapshotSelected selected(&reactor, n);
        assert(reactor.max_event_num == n);
        std::vector<Socket> sockets;
        sockets.reserve(n);
        for (int i = 0; i < n; ++i) {
            sockets.push_back({100 + i, (i % 4) << 9});
            reactor.add(&sockets.back());
        }
        auto *address = selected.events_;
        for (unsigned round = 0; round < 3; ++round) {
            assert(original.set_events() == n);
            assert(selected.set_events() == n);
            assert(selected.events_ == address);
            assert(entries(original, n) == entries(selected, n));
            for (int i = 0; i < n; ++i) {
                assert(selected.events_[i].revents == 0);
                original.events_[i].revents = selected.events_[i].revents = POLLIN;
                ++snapshots;
            }
        }
    }
    int fds[2]; assert(pipe(fds) == 0);
    { Reactor reactor; Socket socket{fds[0], SW_EVENT_READ}; reactor.add(&socket);
      SnapshotOriginal original(&reactor, 1); SnapshotSelected selected(&reactor, 1);
      assert(original.set_events() == 1 && selected.set_events() == 1);
      char byte = 'x'; assert(write(fds[1], &byte, 1) == 1);
      assert(poll(original.events_, 1, 0) == 1 && poll(selected.events_, 1, 0) == 1);
      assert(original.events_[0].revents == selected.events_[0].revents);
      assert(selected.events_[0].revents & POLLIN);
    }
    close(fds[0]); close(fds[1]);
    std::cout << "{\"translations\":" << translations << ",\"snapshot_entries\":" << snapshots
              << ",\"real_pipe_poll\":true,\"layout\":{\"size\":" << sizeof(pollfd)
              << ",\"alignment\":" << alignof(pollfd) << ",\"fd\":" << offsetof(pollfd, fd)
              << ",\"events\":" << offsetof(pollfd, events) << ",\"revents\":" << offsetof(pollfd, revents) << "}}\n";
}
