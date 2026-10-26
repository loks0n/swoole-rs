#ifndef SWOOLE_RS_REACTOR_SOCKETS_H
#define SWOOLE_RS_REACTOR_SOCKETS_H
#if defined(SWOOLE_RS_REACTOR_SOCKETS_OWNED) && SWOOLE_RS_REACTOR_SOCKETS_OWNED
#if !defined(SWOOLE_RS_REACTOR) || !SWOOLE_RS_REACTOR
#error "Socket registry requires --enable-swoole-rs-reactor"
#endif
#include "swoole_rs_reactor.h"
#include <cstdlib>
#include <iterator>
#include <new>
#include <utility>
#if !defined(__APPLE__) || !defined(_LIBCPP_VERSION) || _LIBCPP_VERSION != 210106 || _LIBCPP_ABI_VERSION != 1
#error "Owned socket registry order requires Apple libc++210106 ABI1; unknown policy is activation-blocked"
#endif
static_assert(sizeof(size_t) == 8 && sizeof(int) == 4, "Socket registry target integer ABI");
namespace swoole {
namespace network { struct Socket; }
// Value-only views. No std::unordered_map reference or fabricated Native pair.
// Source-bound Apple libc++210106 ABI1 order; unknown policies refuse this capability.
using ReactorSocketEntry = std::pair<int, network::Socket *>;
inline ReactorSocketEntry swr_socket_entry(swr_v1_reactor_socket_entry value) {
    return {value.fd, reinterpret_cast<network::Socket *>(value.token)};
}
class ReactorSocketView {
    swr_v1_reactor_sockets *const *slot_;
  public:
    class Iterator {
        swr_v1_reactor_socket_live_iterator state_{0, {}, {}, 1};
        void advance() {
            auto *slot = reinterpret_cast<swr_v1_reactor_sockets *const *>(state_.slot_identity);
            if (swr_v1_reactor_sockets_live_next(*slot, &state_) < 0) std::abort();
        }
      public:
        using iterator_category = std::input_iterator_tag;
        using value_type = ReactorSocketEntry;
        using difference_type = ptrdiff_t;
        using pointer = void;
        using reference = value_type;
        Iterator() = default;
        explicit Iterator(swr_v1_reactor_sockets *const *slot) : state_{reinterpret_cast<uintptr_t>(slot), {}, {}, 1} { advance(); }
        value_type operator*() const { return swr_socket_entry(state_.value); }
        Iterator &operator++() { advance(); return *this; }
        Iterator operator++(int) {
            Iterator old;
            auto *slot = reinterpret_cast<swr_v1_reactor_sockets *const *>(state_.slot_identity);
            if (swr_v1_reactor_sockets_live_post(*slot, &state_, &old.state_) < 0) std::abort();
            return old;
        }
        bool operator==(const Iterator &other) const { return swr_v1_reactor_sockets_live_compare(&state_, &other.state_, 0); }
        bool operator!=(const Iterator &other) const { return swr_v1_reactor_sockets_live_compare(&state_, &other.state_, 1); }
    };
    explicit ReactorSocketView(swr_v1_reactor_sockets *const *slot) : slot_(slot) {}
    Iterator begin() const { return Iterator(slot_); }
    Iterator end() const { return Iterator(); }
    size_t size() const { return swr_v1_reactor_sockets_len(*slot_); }
};
class ReactorSocketSnapshot {
    swr_v1_reactor_socket_snapshot *owner_ = nullptr;
  public:
    class Iterator {
        swr_v1_reactor_socket_snapshot_iterator state_{};
      public:
        using iterator_category = std::input_iterator_tag;
        using value_type = ReactorSocketEntry;
        using difference_type = ptrdiff_t;
        using pointer = void;
        using reference = value_type;
        Iterator() = default;
        Iterator(const swr_v1_reactor_socket_snapshot *owner, size_t index) : state_{owner, index} {}
        value_type operator*() const {
            swr_v1_reactor_socket_entry value{};
            if (swr_v1_reactor_sockets_snapshot_iterator_entry(&state_, &value) != 1) std::abort();
            return swr_socket_entry(value);
        }
        Iterator &operator++() { swr_v1_reactor_sockets_snapshot_iterator_next(&state_); return *this; }
        Iterator operator++(int) { Iterator old; if (swr_v1_reactor_sockets_snapshot_iterator_post(&state_, &old.state_) != 0) std::abort(); return old; }
        bool operator==(const Iterator &other) const { return swr_v1_reactor_sockets_snapshot_iterator_compare(&state_, &other.state_, 0); }
        bool operator!=(const Iterator &other) const { return swr_v1_reactor_sockets_snapshot_iterator_compare(&state_, &other.state_, 1); }
    };
    explicit ReactorSocketSnapshot(const swr_v1_reactor_sockets *source) {
        switch (swr_v1_reactor_sockets_snapshot(source, &owner_)) {
        case 0: return;
        case -2: throw std::bad_alloc();
        default: std::abort();
        }
    }
    ReactorSocketSnapshot(const ReactorSocketSnapshot &) = delete;
    ReactorSocketSnapshot &operator=(const ReactorSocketSnapshot &) = delete;
    ReactorSocketSnapshot(ReactorSocketSnapshot &&other) noexcept : owner_(other.owner_) { other.owner_ = nullptr; }
    ReactorSocketSnapshot &operator=(ReactorSocketSnapshot &&) = delete;
    ~ReactorSocketSnapshot() { swr_v1_reactor_sockets_snapshot_free(owner_); }
    size_t size() const { return swr_v1_reactor_sockets_snapshot_len(owner_); }
    Iterator begin() const { return Iterator(owner_, 0); }
    Iterator end() const { return Iterator(owner_, size()); }
};
class ReactorSocketRegistry {
    swr_v1_reactor_sockets *owner_ = nullptr;
    static void check(int32_t status) {
        if (status == -2) throw std::bad_alloc();
        if (status != 0) std::abort();
    }
  public:
    ReactorSocketRegistry() { if (swr_v1_reactor_sockets_policy() != 1) std::abort(); }
    ReactorSocketRegistry(const ReactorSocketRegistry &) = delete;
    ReactorSocketRegistry &operator=(const ReactorSocketRegistry &) = delete;
    ~ReactorSocketRegistry() { swr_v1_reactor_sockets_free(&owner_); }
    bool contains(int fd) const { return swr_v1_reactor_sockets_contains(owner_, fd) != 0; }
    network::Socket *get(int fd) const { return reinterpret_cast<network::Socket *>(swr_v1_reactor_sockets_get(owner_, fd)); }
    void put(int fd, network::Socket *socket) { check(swr_v1_reactor_sockets_put(&owner_, fd, reinterpret_cast<uintptr_t>(socket))); }
    void erase(int fd) { swr_v1_reactor_sockets_erase(owner_, fd); }
    size_t size() const { return swr_v1_reactor_sockets_len(owner_); }
    ReactorSocketView view() const { return ReactorSocketView(&owner_); }
    ReactorSocketSnapshot snapshot() const { return ReactorSocketSnapshot(owner_); }
};
}
#endif
#endif
