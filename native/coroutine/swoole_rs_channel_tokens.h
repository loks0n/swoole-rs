#pragma once
#include "swoole_rs_coroutine.h"
#include <cassert>
#include <new>
#include <type_traits>
#include <utility>

namespace swoole {
namespace coroutine {
// Thin native lifetime/exception adapter. Rust alone owns queue order/storage;
// pointed-to data and Coroutine objects remain native-owned.
template <typename T> class ChannelTokens {
    static_assert(std::is_pointer<T>::value, "Channel tokens must be pointers");
    swr_v1_channel_tokens *owner_;

    static swr_v1_channel_tokens *require(swr_v1_channel_tokens *owner) {
        if (!owner) throw std::bad_alloc();
        return owner;
    }

  public:
    ChannelTokens() : owner_(require(swr_v1_channel_tokens_new())) {}
    ChannelTokens(const ChannelTokens &other)
        : owner_(require(swr_v1_channel_tokens_clone(other.owner_))) {}
    ChannelTokens &operator=(const ChannelTokens &other) {
        if (this != &other) {
            ChannelTokens copy(other);
            std::swap(owner_, copy.owner_);
        }
        return *this;
    }
    ~ChannelTokens() { swr_v1_channel_tokens_free(owner_); }

    // Borrow this sole Rust owner only for a complete module-local operation.
    swr_v1_channel_tokens *native_handle() const { return owner_; }
    size_t size() const { return swr_v1_channel_tokens_len(owner_); }
    bool empty() const { return size() == 0; }
    void push(T token) {
        if (swr_v1_channel_tokens_push(owner_, token) != 0) throw std::bad_alloc();
    }
    void push_back(T token) { push(token); }
    T front() const {
        void *token = nullptr;
        const int present = swr_v1_channel_tokens_front(owner_, &token);
        assert(present == 1);
        (void) present;
        return static_cast<T>(token);
    }
    void pop() { swr_v1_channel_tokens_pop(owner_); }
    void pop_front() { pop(); }
    void remove(T token) { swr_v1_channel_tokens_remove(owner_, token); }
};
}  // namespace coroutine
}  // namespace swoole
