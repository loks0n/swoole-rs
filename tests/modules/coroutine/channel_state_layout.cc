#include "swoole_coroutine_channel.h"
#include <cstddef>
#include <cstdio>
#include <type_traits>
using swoole::coroutine::Channel;
#ifdef SWOOLE_RS_COROUTINE
using swoole::coroutine::ChannelTokens;
struct OldSelected {
    size_t capacity; bool closed; int error;
    ChannelTokens<swoole::Coroutine *> producers, consumers;
    ChannelTokens<void *> data;
};
struct Probe : Channel {
    static void verify() {
        static_assert(sizeof(Channel) == sizeof(OldSelected) && alignof(Channel) == alignof(OldSelected), "full selected layout frozen");
        static_assert(offsetof(Probe, state_) == offsetof(OldSelected, capacity), "prefix offset");
        static_assert(offsetof(Probe, producer_queue) == offsetof(OldSelected, producers), "producer offset");
        static_assert(offsetof(Probe, consumer_queue) == offsetof(OldSelected, consumers), "consumer offset");
        static_assert(offsetof(Probe, data_queue) == offsetof(OldSelected, data), "data offset");
        static_assert(std::is_trivially_copyable<swr_v1_channel_state>::value, "passive metadata projection");
        std::printf("{\"size\":%zu,\"align\":%zu,\"prefix\":%zu,\"producer\":%zu,\"consumer\":%zu,\"data\":%zu}\n",
            sizeof(Channel), alignof(Channel), offsetof(Probe,state_), offsetof(Probe,producer_queue), offsetof(Probe,consumer_queue), offsetof(Probe,data_queue));
    }
};
#else
struct Probe : Channel {
    static void verify() {
// The native Channel's std::list members make it non-standard-layout; GCC accepts offsetof there
// but warns, and the gate builds with -Werror.
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Winvalid-offsetof"
        std::printf("{\"size\":%zu,\"align\":%zu,\"capacity\":%zu,\"closed\":%zu,\"error\":%zu}\n",sizeof(Channel),alignof(Channel),offsetof(Probe,capacity),offsetof(Probe,closed),offsetof(Probe,error_));
#pragma GCC diagnostic pop
    }
};
#endif
int main() { Probe::verify(); }
