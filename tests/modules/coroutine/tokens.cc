// Actual Channel header and normal token storage only. No Coroutine is created,
// resumed, canceled or destroyed; native logging is an explicit inert facade.
#include "swoole.h"
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <type_traits>

static unsigned warning_calls;
#undef swoole_error_log
#define swoole_error_log(...) (++warning_calls)
#include "swoole_coroutine_channel.h"

using swoole::Coroutine;
using swoole::coroutine::Channel;

struct Probe : Channel {
    using Channel::Channel;
    void append(void *token) { data_queue.push(token); }
    void producer(Coroutine *token) { producer_queue.push_back(token); }
    void consumer(Coroutine *token) { consumer_queue.push_back(token); }
    void remove_producer(Coroutine *token) { producer_queue.remove(token); }
    void remove_consumer(Coroutine *token) { consumer_queue.remove(token); }
    Coroutine *first_producer() { return producer_queue.front(); }
    Coroutine *first_consumer() { return consumer_queue.front(); }
    void shift_producer() { producer_queue.pop_front(); }
    void shift_consumer() { consumer_queue.pop_front(); }
    void clear_waiters() {
        while (!producer_queue.empty()) producer_queue.pop_front();
        while (!consumer_queue.empty()) consumer_queue.pop_front();
    }
};

struct alignas(std::max_align_t) Token { unsigned char bytes[32]; };
static Token tokens[19];
static uint64_t checksum = 1469598103934665603ULL;
static size_t observations;

static void observe(size_t value) {
    checksum = (checksum ^ value) * 1099511628211ULL;
    ++observations;
}

static size_t identity(void *pointer) {
    if (!pointer) return 0;
    for (size_t i = 0; i < 19; ++i) if (pointer == &tokens[i]) return i + 1;
    assert(false);
    return 0;
}

int main() {
    static_assert(std::is_copy_constructible<Channel>::value, "Public Channel copy remains available");
    static_assert(std::is_copy_assignable<Channel>::value, "Public Channel assignment remains available");
    static_assert(alignof(Coroutine) <= alignof(Token), "Opaque identities retain pointer alignment");
    {
        Probe channel(3);
        assert(channel.is_empty() && !channel.is_full() && !channel.is_closed());
        assert(channel.get_error() == 0 && channel.pop_data() == nullptr);
        for (size_t i = 0; i < 4096; ++i) {
            void *token = i % 7 ? &tokens[i % 19] : nullptr;
            channel.append(token);
            observe(channel.length());
            observe(channel.is_full());
            if (i % 3 == 0) observe(identity(channel.pop_data()));
        }
        const size_t original_length = channel.length();
        Probe copy(channel);
        assert(copy.length() == original_length);
        while (!copy.is_empty()) observe(identity(copy.pop_data()));
        assert(channel.length() == original_length);
        copy = channel;
        copy = copy;
        assert(copy.length() == original_length);
        while (!channel.is_empty()) assert(channel.pop_data() == copy.pop_data());
        assert(copy.is_empty());

        for (size_t i = 0; i < 1024; ++i) {
            auto *token = reinterpret_cast<Coroutine *>(&tokens[i % 19]);
            channel.producer(token);
            channel.consumer(token);
        }
        for (size_t i = 0; i < 19; i += 2) {
            auto *token = reinterpret_cast<Coroutine *>(&tokens[i]);
            channel.remove_producer(token);
            channel.remove_consumer(token);
        }
        copy = channel;
        assert(copy.producer_num() == channel.producer_num());
        assert(copy.consumer_num() == channel.consumer_num());
        while (channel.producer_num()) {
            observe(identity(channel.first_producer()));
            assert(channel.first_producer() == copy.first_producer());
            channel.shift_producer();
            copy.shift_producer();
        }
        while (channel.consumer_num()) {
            observe(identity(channel.first_consumer()));
            assert(channel.first_consumer() == copy.first_consumer());
            channel.shift_consumer();
            copy.shift_consumer();
        }
        channel.clear_waiters();
        copy.clear_waiters();
    }
    assert(warning_calls == 0);
    std::printf("{\"observations\":%zu,\"checksum\":%llu,\"warnings\":%u}\n",
                observations, static_cast<unsigned long long>(checksum), warning_calls);
}
