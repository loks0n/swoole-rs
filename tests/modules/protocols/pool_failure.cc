// Separate TU: allocation injection must never affect the matched benchmark.
#include <cstddef>
#include <cstdlib>
#include <new>
static thread_local std::ptrdiff_t fail_after = -1;
static thread_local bool fault_fired = false;
// Keep replacement new/delete opaque to GCC's mismatched-allocation inliner;
// both sides deliberately use malloc/free, with sanitizers still enabled.
[[gnu::noinline]] void *operator new(std::size_t size) {
    if (fail_after >= 0 && fail_after-- == 0) {
        fault_fired = true;
        throw std::bad_alloc();
    }
    if (auto pointer = std::malloc(size ? size : 1)) return pointer;
    throw std::bad_alloc();
}
[[gnu::noinline]] void *operator new[](std::size_t size) { return ::operator new(size); }
[[gnu::noinline]] void operator delete(void *pointer) noexcept { std::free(pointer); }
[[gnu::noinline]] void operator delete[](void *pointer) noexcept { std::free(pointer); }
[[gnu::noinline]] void operator delete(void *pointer, std::size_t) noexcept { std::free(pointer); }
[[gnu::noinline]] void operator delete[](void *pointer, std::size_t) noexcept { std::free(pointer); }
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wreturn-type"
#define main protocols_correctness_main
#include "native.cc"
#undef main
#pragma GCC diagnostic pop
struct FailureScope {
    explicit FailureScope(size_t position) { fault_fired = false; fail_after = position; }
    ~FailureScope() { fail_after = -1; }
};
struct Outcomes { size_t copy_attempts=0, copy_failures=0, assignment_attempts=0, assignment_failures=0; };
template<class Bus, class Buffer, class String>
static Outcomes owner_failure_trace(const char *engine) {
    Outcomes outcomes;
    assert(String::live == 0);
    for (size_t count : {0u,1u,31u,32u,33u,97u}) {
        {
            Buffer buffer{};
            Bus original;
            original.buffer_=&buffer;
            buffer.info.flags=SW_EVENT_DATA_BEGIN;
            buffer.info.len=32;
            for(uint64_t id=0;id<count;++id) {
                buffer.info.msg_id=id;
                original.get_packet_buffer()->append("owner",5);
            }
            buffer.info.flags=0; // Missing lookups must fail, never allocate during validation.
            auto validate_original = [&]() {
                assert(original.packet_pool_.size()==count);
                for(uint64_t id=0;id<count;++id) {
                    buffer.info.msg_id=id;
                    auto value=original.get_packet_buffer();
                    assert(value && value->length==5 && !std::memcmp(value->str,"owner",5));
                }
            };
            size_t copy_successes=0, assignment_successes=0;
            for(size_t position=0;position<2*count+6;++position) {
                ++outcomes.copy_attempts;
                try {
                    FailureScope injection(position);
                    Bus copy(original);
                    assert(copy.packet_pool_.size()==count && copy.get_memory_size()==original.get_memory_size());
                    for(uint64_t id=0;id<count;++id) {
                        buffer.info.msg_id=id;
                        assert(copy.get_packet_buffer()==original.get_packet_buffer());
                    }
                    ++copy_successes;
                    assert(!fault_fired);
                } catch(const std::bad_alloc &) {
                    assert(fault_fired);
                    ++outcomes.copy_failures;
                }
                validate_original();
                assert(String::live==count);
                Buffer target_buffer{};
                Bus target;
                target.buffer_=&target_buffer;
                target_buffer.info.flags=SW_EVENT_DATA_BEGIN;
                target_buffer.info.msg_id=UINT64_MAX;
                target_buffer.info.len=32;
                target.get_packet_buffer()->append("old",3);
                ++outcomes.assignment_attempts;
                try {
                    FailureScope injection(position);
                    target=original;
                    assert(target.packet_pool_.size()==count);
                    ++assignment_successes;
                    assert(!fault_fired);
                } catch(const std::bad_alloc &) {
                    assert(fault_fired);
                    ++outcomes.assignment_failures;
                }
                // stdcontainer post-throw target contents are unspecified. Require
                // validity/cleanup, not identical failure positions or contents.
                target.packet_pool_.clear();
                validate_original();
                assert(String::live==count);
            }
            assert(copy_successes && assignment_successes);
            // A single-node stdmap assignment can reuse its existing node and
            // allocate nothing; failure counts are intentionally not prescribed.
        }
        assert(String::live==0); // Leaked partial holders retain shared String refs.
    }
    if(!outcomes.copy_failures || !outcomes.assignment_failures) {
        std::fprintf(stderr,"No injected allocation failures engine=%s\n",engine);
        assert(outcomes.copy_failures && outcomes.assignment_failures);
    }
    return outcomes;
}
int main() {
    const auto before=owner_failure_trace<reference::MessageBus,reference::PipeBuffer,reference::String>("upstream");
    const auto after=owner_failure_trace<candidate::MessageBus,candidate::PipeBuffer,candidate::String>("rust");
    std::printf("{\"upstream\":{\"copy_attempts\":%zu,\"copy_failures\":%zu,\"assignment_attempts\":%zu,\"assignment_failures\":%zu},"
                "\"rust\":{\"copy_attempts\":%zu,\"copy_failures\":%zu,\"assignment_attempts\":%zu,\"assignment_failures\":%zu},\"errors\":0}\n",
                before.copy_attempts,before.copy_failures,before.assignment_attempts,before.assignment_failures,
                after.copy_attempts,after.copy_failures,after.assignment_attempts,after.assignment_failures);
}
