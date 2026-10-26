// Ordinary inert integer membership/order model, no real Socket effects or callbacks.
#include <cassert>
#include <cstdint>
#include <functional>
#include <iostream>
#include <map>
#include <unordered_map>
#include <vector>
#include "swoole_rs_reactor.h"
namespace swoole { namespace network { struct Socket { int fd=0; int events=0; int removed=1; }; } }
#include "swoole_rs_reactor_sockets.h"
#include "registry.inc"
using namespace swoole;
using Socket = network::Socket;
#if defined(SWOOLE_RS_REACTOR_SOCKETS_OWNED) && SWOOLE_RS_REACTOR_SOCKETS_OWNED
#define LIVE(r) (r).socket_registry_view()
#define SNAPSHOT(r) (r).socket_registry_snapshot()
#else
#define LIVE(r) (r).get_sockets()
#define SNAPSHOT(r) (r).get_sockets()
#endif
static size_t checks=0;
#define CHECK(x) do {++checks;assert(x);} while(0)
template<class Range> static std::map<int,Socket*> members(const Range &range) {
    std::map<int,Socket*> values;for(auto entry:range) values.emplace(entry.first,entry.second);return values;
}
template<class Range> static uint64_t order_hash(const Range &range) {
    uint64_t hash=1469598103934665603ULL;
    for(auto entry:range) {hash^=static_cast<uint64_t>(static_cast<int64_t>(entry.first));hash*=1099511628211ULL;}
    return hash;
}
static void emit(const std::vector<uint64_t> &values) {
    std::cout<<'[';bool first=true;for(auto value:values){if(!first)std::cout<<',';first=false;std::cout<<value;}std::cout<<']';
}
int main() {
    std::vector<uint64_t> live, copied;
    for(int pattern=0;pattern<6;++pattern) {
        for(int count:{1,3,17,65,257}) {
            RegistryFacade registry; Socket objects[600];
            std::map<int,Socket*> expected;
            auto observe=[&](){
                CHECK(registry.get_event_num()==expected.size());
                CHECK(members(LIVE(registry))==expected);
                const auto snapshot=SNAPSHOT(registry);
                CHECK(members(snapshot)==expected);
                live.push_back(order_hash(LIVE(registry)));
                copied.push_back(order_hash(snapshot));
            };
            uint32_t random=0x12345678;
            observe();
            for(int i=0;i<count;++i) {
                random=random*1664525u+1013904223u;
                int key=pattern==0?i:pattern==1?count-i:pattern==2?i*97:pattern==3?i*1024:pattern==4?(i%2?-i:i):static_cast<int>(random%97)-48;
                objects[i].fd=key;
                registry._add(&objects[i],i+1);expected[key]=&objects[i];
                CHECK(objects[i].events==i+1&&objects[i].removed==0);
                CHECK(registry.get_socket(key)==&objects[i]);
                observe();
            }
            for(int i=0;i<count;i+=3) {
                registry._del(&objects[i]);expected.erase(objects[i].fd);
                CHECK(objects[i].events==0&&objects[i].removed==1);observe();
            }
            // Reuse metadata slots, overwrite duplicate keys and retain existing buckets.
            for(int i=0;i<count;i+=2) {
                objects[count+i].fd=objects[i].fd;
                registry._add(&objects[count+i],2);expected[objects[i].fd]=&objects[count+i];observe();
            }
            // Since v6.2.4 (5c1018b49) a missed lookup returns null without inserting.
            const int absent=-1000000-pattern;CHECK(registry.get_socket(absent)==nullptr);
            CHECK(!registry.exists(absent));observe();
        }
    }
    std::cout<<"{\"common\":{\"checks\":"<<checks<<",\"traces\":"<<live.size()<<",\"scenarios\":30},\"live_order\":";emit(live);std::cout<<",\"snapshot_order\":";emit(copied);std::cout<<"}\n";
}
