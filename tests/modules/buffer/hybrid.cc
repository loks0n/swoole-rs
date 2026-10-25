// Count every real facade boundary, including additive front/advance plans.
#undef swr_v1_buffer_append
#undef swr_v1_buffer_stats
#undef swr_v1_buffer_front
#undef swr_v1_buffer_pop
#undef swr_v1_buffer_front_plan
#undef swr_v1_buffer_advance
#define SWR_BUFFER_HYBRID_GATE
#define main facade_checks
#include "baseline.cc"
#undef main
#include "swoole_rs_buffer.h"
#include "swoole_rs_buffer_facade.h"
#include <sys/wait.h>
#include <array>

struct AbiCalls { unsigned append = 0, stats = 0, front = 0, pop = 0; };
static AbiCalls abi_calls;
extern "C" int32_t swr_test_buffer_append(swr_v1_buffer *b, const uint8_t *p, size_t n) {
    ++abi_calls.append;
    return swr_v1_buffer_append(b, p, n);
}
extern "C" int32_t swr_test_buffer_stats(const swr_v1_buffer *b, uint32_t *n, size_t *c) {
    ++abi_calls.stats;
    return swr_v1_buffer_stats(b, n, c);
}
extern "C" int32_t swr_test_buffer_front(const swr_v1_buffer *b, swr_v1_buffer_view *v) {
    ++abi_calls.front;
    return swr_v1_buffer_front(b, v);
}
extern "C" int32_t swr_test_buffer_pop(swr_v1_buffer *b, void **token) {
    ++abi_calls.pop;
    return swr_v1_buffer_pop(b, token);
}
extern "C" int32_t swr_test_buffer_front_plan(swr_v1_buffer *b, void *identity, swr_v1_buffer_view *view) {
    ++abi_calls.front;
    return swr_v1_buffer_front_plan(b, identity, view);
}
extern "C" int32_t swr_test_buffer_advance(swr_v1_buffer *b, uint32_t drain, uint32_t destroy,
                                          swr_v1_buffer_advance_result *effect) {
    ++abi_calls.pop;
    return swr_v1_buffer_advance(b, drain, destroy, effect);
}
static unsigned discarded_native = 0;
static void discard_native(swoole::BufferChunk *chunk) {
    require((chunk->type == swoole::BufferChunk::TYPE_CLOSE && chunk->value.u32 == 1234) ||
            (chunk->type == swoole::BufferChunk::TYPE_DATA && chunk->size == 3),
            "Unobserved native token changed before disposal");
    ++discarded_native;
}
static std::array<unsigned, 2> call_count_checks() {
    std::array<unsigned, 2> totals{};
    for (unsigned peek = 0; peek < 2; ++peek) {
        swoole::Buffer buffer(16384);
        std::vector<char> bytes(65536, 'k');
        abi_calls = {};
        buffer.append(bytes.data(), bytes.size());
        while (!buffer.empty()) {
            if (peek) require(buffer.front()->value.str[0] == 'k', "Consumer data changed");
            buffer.pop();
        }
        const auto observed = abi_calls;
        require(observed.append == 1 && observed.stats == 5 && observed.pop == 4 &&
                observed.front == (peek ? 4u : 0u), "Four-chunk ABI call counts changed");
        totals[peek] = observed.append + observed.stats + observed.front + observed.pop;
        buffer.pop();
        buffer.pop();
        require(buffer.empty() && buffer.length() == 0, "Empty pop is not a no-op");
    }
    for (auto type : {swoole::BufferChunk::TYPE_CLOSE, swoole::BufferChunk::TYPE_DATA}) {
        swoole::Buffer buffer(3);
        auto *native = buffer.alloc(type, type == swoole::BufferChunk::TYPE_DATA ? 3 : 0);
        if (type == swoole::BufferChunk::TYPE_CLOSE) native->value.u32 = 1234;
        else std::memcpy(native->value.str, "xyz", 3);
        native->destroy = discard_native;
        buffer.append("abcdef", 6);
        abi_calls = {};
        buffer.pop();
        require(abi_calls.front == 0 && abi_calls.pop == 1, "Native discard materialized a front");
        buffer.pop();
        buffer.pop();
        require(abi_calls.front == 0 && abi_calls.pop == 3, "DATA discard materialized a front");
        require(buffer.empty() && buffer.length() == 0, "Unobserved discard corrupted accounting");
    }
    require(discarded_native == 2, "Unobserved native disposal count changed");
    return totals;
}

static void expect_stats(swr_v1_buffer *buffer, uint32_t bytes, size_t entries) {
    uint32_t length = UINT32_MAX;
    size_t count = SIZE_MAX;
    require(swr_v1_buffer_stats(buffer, &length, &count) == SWR_BUFFER_OK, "C ABI stats failed");
    require(length == bytes && count == entries, "C ABI stats mismatch");
}

static void abi_checks() {
    swr_v1_buffer *buffer = nullptr;
    require(swr_v1_buffer_create(4, &buffer) == SWR_BUFFER_OK && buffer, "C ABI create failed");
    require(swr_v1_buffer_create(4, nullptr) == SWR_BUFFER_INVALID, "Null create output accepted");
    require(swr_v1_buffer_release(nullptr) == SWR_BUFFER_OK, "Null release failed");
    expect_stats(buffer, 0, 0);
    swr_v1_buffer_view view{};
    view.length = 99;
    require(swr_v1_buffer_front(buffer, &view) == SWR_BUFFER_EMPTY && view.length == 0 && !view.data && !view.token, "Empty front not zeroed");
    view.length = 99;
    require(swr_v1_buffer_front(nullptr, &view) == SWR_BUFFER_INVALID && view.length == 0 && !view.data && !view.token, "Invalid front not zeroed");
    void *token = buffer;
    require(swr_v1_buffer_pop(buffer, &token) == SWR_BUFFER_EMPTY && !token, "Empty pop not zeroed");
    token = buffer;
    require(swr_v1_buffer_pop(nullptr, &token) == SWR_BUFFER_INVALID && !token, "Invalid pop not zeroed");
    require(swr_v1_buffer_append(buffer, nullptr, 0) == SWR_BUFFER_OK, "Empty append rejected");
    require(swr_v1_buffer_appendv(buffer, nullptr, 0, 0) == SWR_BUFFER_OK, "Empty vector rejected");
    uint8_t bytes[] = {0, 255, 2, 3, 0, 5};
    swr_v1_buffer_iovec vectors[] = {{nullptr, 0}, {bytes, 3}, {nullptr, 0}, {bytes + 3, 3}};
    require(swr_v1_buffer_appendv(buffer, vectors, 4, 6) == SWR_BUFFER_OK, "Offset equal to total rejected");
    expect_stats(buffer, 0, 0);
    require(swr_v1_buffer_appendv(buffer, vectors, 4, 7) == SWR_BUFFER_INVALID, "Offset beyond total accepted");
    require(swr_v1_buffer_appendv(buffer, nullptr, 1, 0) == SWR_BUFFER_INVALID, "Null nonempty vector accepted");
    require(swr_v1_buffer_append(buffer, nullptr, 1) == SWR_BUFFER_INVALID, "Null nonempty append accepted");
    require(swr_v1_buffer_append(buffer, bytes, SIZE_MAX) == SWR_BUFFER_OVERFLOW, "Oversized append accepted");
    require(swr_v1_buffer_appendv(buffer, vectors, SIZE_MAX, 0) == SWR_BUFFER_OVERFLOW, "Oversized descriptor count accepted");
    swr_v1_buffer_iovec invalid[] = {{nullptr, 1}, {bytes, 6}};
    require(swr_v1_buffer_appendv(buffer, invalid, 2, 1) == SWR_BUFFER_INVALID, "Skipped null nonempty descriptor accepted");
    expect_stats(buffer, 0, 0);
    require(swr_v1_buffer_appendv(buffer, vectors, 4, 3) == SWR_BUFFER_OK, "Exact vector offset failed");
    expect_stats(buffer, 3, 1);
    require(swr_v1_buffer_front(buffer, &view) == SWR_BUFFER_OK && view.kind == 0 && view.length == 3 && view.capacity == 3, "Data view differs");
    require(std::memcmp(view.data, bytes + 3, 3) == 0, "Vector suffix wrong");
    auto *stable = view.data;
    require(swr_v1_buffer_append(buffer, bytes, 6) == SWR_BUFFER_OK, "Append after front failed");
    require(swr_v1_buffer_front(buffer, &view) == SWR_BUFFER_OK && view.data == stable, "Append invalidated borrowed pointer");
    expect_stats(buffer, 9, 3);
    require(swr_v1_buffer_front(buffer, nullptr) == SWR_BUFFER_INVALID, "Null front output accepted");
    require(swr_v1_buffer_pop(buffer, nullptr) == SWR_BUFFER_INVALID, "Null pop output accepted");
    uint32_t untouched = 99;
    require(swr_v1_buffer_stats(buffer, &untouched, nullptr) == SWR_BUFFER_INVALID && untouched == 99, "Failed stats mutated output");
    int native = 7;
    require(swr_v1_buffer_push_native(buffer, nullptr) == SWR_BUFFER_INVALID, "Null native token accepted");
    require(swr_v1_buffer_push_native(buffer, &native) == SWR_BUFFER_OK, "Native push failed");
    require(swr_v1_buffer_release(buffer) == SWR_BUFFER_PENDING_NATIVE, "Pending native token lost on release");
    expect_stats(buffer, 9, 4);
    for (unsigned i = 0; i < 3; ++i) {
        token = &native;
        require(swr_v1_buffer_pop(buffer, &token) == SWR_BUFFER_OK && !token, "Data pop returned native token");
    }
    expect_stats(buffer, 0, 1);
    require(swr_v1_buffer_front(buffer, &view) == SWR_BUFFER_OK && view.kind == 1 && view.token == &native && !view.data, "Native front differs");
    require(swr_v1_buffer_pop(buffer, &token) == SWR_BUFFER_OK && token == &native, "Native ownership not returned");
    require(swr_v1_buffer_release(buffer) == SWR_BUFFER_OK, "Release after drain failed");
}

static unsigned live_callbacks = 0;
static void data_alive_callback(swoole::BufferChunk *chunk) {
    require(chunk->value.str && chunk->length == 3 && chunk->value.str[0] == 'a', "Data not alive during native callback");
    ++live_callbacks;
}

static void facade_lifetimes() {
    {
        swoole::Buffer buffer(4);
        buffer.append("abc", 3);
        auto *front = buffer.front();
        front->offset = 2;
        front->destroy = data_alive_callback;
        buffer.append("defg", 4);
        require(buffer.front() == front && front->offset == 2, "Native view identity/offset reset by append");
        buffer.pop();
        require(live_callbacks == 1 && buffer.length() == 4, "Live data callback/pop mismatch");
        auto *native = buffer.alloc(swoole::BufferChunk::TYPE_DATA, 3);
        std::memcpy(native->value.str, "xyz", 3);
        native->length = 3;
        buffer.pop();
        require(buffer.front() == native && buffer.length() == 0, "Native DATA allocation unexpectedly charged");
        buffer.pop();
        require(buffer.empty() && buffer.length() == 0, "Native DATA pop underflow");
    }
    {
        swoole::Buffer teardown(4);
        teardown.append("abc", 3);
        teardown.front()->destroy = data_alive_callback;
    }
    require(live_callbacks == 2, "Teardown did not invoke live data callback once");
    // Quiescent fork inherits independent queues under copy-on-write.
    auto forked = std::make_unique<swoole::Buffer>(4);
    auto &buffer = *forked;
    buffer.append("abc", 3);
    const pid_t child = fork();
    require(child >= 0, "Fork failed");
    if (child == 0) {
        try {
            require(buffer.length() == 3, "Child lost inherited buffer");
            buffer.pop();
            buffer.append("child", 5);
            require(buffer.length() == 5, "Child mutation failed");
            while (!buffer.empty()) buffer.pop();
            forked.reset();
            _exit(0);
        } catch (...) { _exit(1); }
    }
    int status = 0;
    require(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0, "Child buffer checks failed");
    require(buffer.length() == 3 && std::memcmp(buffer.front()->value.str, "abc", 3) == 0, "Child mutation affected parent");
    buffer.pop();
}

static unsigned small_vector_cases() {
    unsigned cases = 0;
    for (size_t count : {size_t(8), size_t(9)}) {
        for (bool all_empty : {false, true}) {
            std::vector<std::vector<char>> storage(count);
            std::vector<iovec> vectors(count);
            std::vector<char> concatenated;
            size_t boundary = 0;
            for (size_t index = 0; index < count; ++index) {
                const size_t length = all_empty || index % 3 == 1 ? 0 : index % 4 + 1;
                for (size_t byte = 0; byte < length; ++byte) {
                    storage[index].push_back(char((index * 97 + byte * 255) & 255));
                }
                vectors[index] = {storage[index].empty() ? nullptr : storage[index].data(), length};
                concatenated.insert(concatenated.end(), storage[index].begin(), storage[index].end());
                if (index == 3) boundary = concatenated.size();
            }
            const std::vector<size_t> offsets = all_empty ? std::vector<size_t>{0} :
                std::vector<size_t>{0, 1, boundary, concatenated.size() / 2,
                                    concatenated.size() - 1, concatenated.size()};
            for (uint32_t chunk_size : {1u, 4u, 17u}) {
                for (size_t offset : offsets) {
                    swoole::Buffer buffer(chunk_size);
                    std::vector<char> expected;
                    swoole::BufferChunk *front = nullptr;
                    char *front_data = nullptr;
                    uint32_t saved_offset = 0;
                    if (!all_empty) {
                        expected = {char(255), 0, char(128)};
                        buffer.append(expected.data(), uint32_t(expected.size()));
                        front = buffer.front();
                        front_data = front->value.str;
                        front->offset = saved_offset = std::min(1u, front->length);
                    }
                    const size_t old_count = buffer.count();
                    buffer.append(vectors.data(), vectors.size(), off_t(offset));
                    const size_t suffix_length = concatenated.size() - offset;
                    expected.insert(expected.end(), concatenated.begin() + offset, concatenated.end());
                    require(buffer.length() == expected.size(), "Small-vector copied-length accounting differs");
                    require(buffer.count() == old_count + (suffix_length + chunk_size - 1) / chunk_size, "Small-vector chunk count differs");
                    if (front) {
                        require(buffer.front() == front && front->value.str == front_data && front->offset == saved_offset,
                                "Small-vector append reset cached front identity/data/offset");
                    }
                    std::vector<char> copied;
                    size_t remaining = expected.size();
                    while (!buffer.empty()) {
                        auto *chunk = buffer.front();
                        require(chunk->length == chunk->size && chunk->offset <= chunk->length, "Small-vector chunk view differs");
                        copied.insert(copied.end(), chunk->value.str, chunk->value.str + chunk->length);
                        remaining -= chunk->length;
                        const size_t prior_count = buffer.count();
                        buffer.pop();
                        require(buffer.length() == remaining && buffer.count() == prior_count - 1, "Small-vector pop accounting differs");
                    }
                    require(copied == expected && buffer.length() == 0, "Small-vector binary suffix differs");
                    ++cases;
                }
            }
        }
    }
    require(cases == 42, "Small-vector case matrix incomplete");
    return cases;
}

static std::vector<unsigned> cache_callbacks;
static unsigned native_data_callbacks = 0;
static void cache_data_callback(swoole::BufferChunk *chunk) {
    require(chunk->length == 3 && chunk->value.str &&
            chunk->value.str[0] == chunk->value.str[1] && chunk->value.str[1] == chunk->value.str[2],
            "Cached data callback did not see live original bytes");
    cache_callbacks.push_back(static_cast<unsigned char>(chunk->value.str[0]));
}
static void cache_native_callback(swoole::BufferChunk *chunk) {
    cache_callbacks.push_back(chunk->value.u32);
}
static void cache_native_data_callback(swoole::BufferChunk *) { ++native_data_callbacks; }

static void cache_transitions() {
    {
        swoole::Buffer buffer(3);
        buffer.append("aaa", 3);
        buffer.append("bbb", 3);
        auto *native = buffer.alloc(swoole::BufferChunk::TYPE_CLOSE, 0);
        native->value.u32 = 1000;
        native->destroy = cache_native_callback;
        buffer.append("ccc", 3);
        auto *first = buffer.front();
        char *first_data = first->value.str;
        first->offset = 1;
        first->destroy = cache_data_callback;
        buffer.append("ddd", 3);
        const auto length = buffer.length();
        const auto count = buffer.count();
        auto unchanged = [&] {
            require(buffer.front() == first && first->value.str == first_data && first->offset == 1 &&
                    first->destroy == cache_data_callback && buffer.length() == length && buffer.count() == count,
                    "Successful/failed append changed cached front or callback");
        };
        unchanged();
        unchanged();
        bool invalid = false;
        try { buffer.append(nullptr, 1); }
        catch (const std::invalid_argument &) { invalid = true; }
        require(invalid, "Invalid append was not rejected");
        unchanged();
        iovec oversized{const_cast<char *>("x"), SIZE_MAX};
        bool overflow = false;
        try { buffer.append(&oversized, 1, 0); }
        catch (const std::length_error &) { overflow = true; }
        require(overflow, "Overflowing appendv was not rejected");
        unchanged();
        buffer.pop();
        auto *second = buffer.front();
        require(second->type == swoole::BufferChunk::TYPE_DATA && second->value.str != first_data &&
                std::memcmp(second->value.str, "bbb", 3) == 0 && second->offset == 0 && !second->destroy,
                "DATA-to-DATA transition reused stale cached fields");
        second->offset = 2;
        second->destroy = cache_data_callback;
        require(buffer.front() == second && second->offset == 2 && second->destroy == cache_data_callback,
                "Repeated front reset second DATA fields");
        buffer.pop();
        require(buffer.front() == native && native->value.u32 == 1000 && native->destroy == cache_native_callback,
                "DATA-to-native transition returned cached DATA");
        buffer.append("eee", 3);
        require(buffer.front() == native, "Append changed native front identity");
        buffer.pop();
        for (const char *expected : {"ccc", "ddd", "eee"}) {
            auto *chunk = buffer.front();
            require(chunk && chunk->type == swoole::BufferChunk::TYPE_DATA && chunk->offset == 0 && !chunk->destroy &&
                    std::memcmp(chunk->value.str, expected, 3) == 0, "Native/DATA transition retained stale fields");
            chunk->destroy = cache_data_callback;
            buffer.pop();
        }
        require(buffer.front() == nullptr && buffer.front() == nullptr && buffer.empty() && buffer.length() == 0,
                "Empty queue returned stale cached front");
    }
    require(cache_callbacks == std::vector<unsigned>({'a', 'b', 1000, 'c', 'd', 'e'}),
            "Cache transition callback order/count differs");
    for (size_t count : {size_t(8), size_t(9)}) {
        swoole::Buffer buffer(3);
        buffer.append("aaa", 3);
        auto *front = buffer.front();
        front->offset = 2;
        front->destroy = cache_data_callback;
        std::vector<iovec> vectors(count);
        size_t suffix_length = 0;
        for (size_t index = 0; index < count; ++index) {
            const size_t length = index % 3 == 0 ? 0 : 1;
            vectors[index] = {length ? const_cast<char *>("z") : nullptr, length};
            suffix_length += length;
        }
        buffer.append(vectors.data(), count, 0);
        require(buffer.front() == front && front->offset == 2 && front->destroy == cache_data_callback &&
                std::memcmp(front->value.str, "aaa", 3) == 0, "8/9 descriptor append reset DATA callback/cache");
        const auto before = cache_callbacks.size();
        buffer.pop();
        require(cache_callbacks.size() == before + 1 && buffer.length() == suffix_length,
                "8/9 descriptor DATA callback not invoked exactly once");
    }
    require(cache_callbacks.size() == 8, "Cached DATA destructor invoked callback twice");
    {
        swoole::Buffer buffer(3);
        auto *native = buffer.alloc(swoole::BufferChunk::TYPE_DATA, 3);
        std::memcpy(native->value.str, "xyz", 3);
        native->length = 3;
        native->offset = 1;
        native->destroy = cache_native_data_callback;
        require(buffer.front() == native, "Native-owned DATA was replaced by cached view");
        buffer.append("aaa", 3);
        require(buffer.front() == native && native->offset == 1 && native->destroy == cache_native_data_callback,
                "Native-owned DATA identity/offset/callback changed");
        buffer.pop();
        require(native_data_callbacks == 1 && buffer.front()->offset == 0 && !buffer.front()->destroy &&
                std::memcmp(buffer.front()->value.str, "aaa", 3) == 0,
                "Native-owned DATA transition left stale cached fields");
    }
    require(native_data_callbacks == 1 && cache_callbacks.size() == 8, "Cache teardown duplicated callbacks");
}

int main() {
    std::cout << "{\"facade\":";
    if (facade_checks() != 0) return 1;
    try {
        abi_checks();
        facade_lifetimes();
        const unsigned vector_cases = small_vector_cases();
        cache_transitions();
        const auto calls = call_count_checks();
        std::cout << ",\"c_abi_checks\":true,\"facade_lifetime_checks\":true,\"quiescent_fork\":true,\"small_vector_cases\":" << vector_cases
                  << ",\"cache_transition_checks\":true,\"cache_callbacks\":" << cache_callbacks.size()
                  << ",\"cache_native_data_callbacks\":" << native_data_callbacks << ",\"pop_only_rust_calls\":" << calls[0]
                  << ",\"consumer_rust_calls\":" << calls[1] << ",\"uncached_native_disposals\":" << discarded_native << "}\n";
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
