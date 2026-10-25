#include <cassert>
#include <cstdint>
#include <cstddef>
#include <functional>
#include <iostream>
#include <map>
#include <type_traits>
#include <unordered_map>
#include <vector>
#include "swoole_rs_reactor.h"
namespace swoole { namespace network { struct Socket { int fd; int events=0; int removed=1; }; } }
#include "swoole_rs_reactor_sockets.h"
#include "registry.inc"
using namespace swoole;
using Socket = network::Socket;
static size_t checks=0;
#define CHECK(x) do { ++checks; assert(x); } while(0)
#if defined(SWOOLE_RS_REACTOR_SOCKETS_OWNED) && SWOOLE_RS_REACTOR_SOCKETS_OWNED
#define LIVE(r) (r).socket_registry_view()
#define SNAPSHOT(r) (r).socket_registry_snapshot()
#else
#define LIVE(r) (r).get_sockets()
#define SNAPSHOT(r) (r).get_sockets()
static_assert(std::is_same<decltype(std::declval<RegistryFacade&>().get_sockets()), const std::unordered_map<int,Socket*>&>::value,"Exact original default API");
#endif
template<class Range> static std::map<int,Socket*> members(const Range &range) {
    std::map<int,Socket*> result;
    for (auto pair : range) result.emplace(pair.first,pair.second);
    return result;
}
template<class Range> static void order(const Range &range) {
    bool first=true; std::cout << '[';
    for (auto pair : range) { if (!first) std::cout << ','; first=false;std::cout << pair.first; }
    std::cout << ']';
}
int main() {
    RegistryFacade registry;
    CHECK(registry.get_event_num()==0);
    const auto &early_view=LIVE(registry);
    CHECK(registry.get_socket(-7)==nullptr);
    CHECK(registry.exists(-7));CHECK(registry.get_event_num()==1);CHECK(early_view.size()==1);
    Socket missing{-7};registry._del(&missing);CHECK(!registry.exists(-7));CHECK(missing.events==0&&missing.removed==1);
    Socket values[67];
    for (int i=0;i<65;++i) {values[i].fd=3*i+1;registry._add(&values[i],i+1);CHECK(registry.get_socket(values[i].fd)==&values[i]);CHECK(values[i].events==i+1&&values[i].removed==0);}
    CHECK(registry.get_event_num()==65);CHECK(early_view.size()==65);
    auto expected=members(LIVE(registry));
    const auto snapshot=SNAPSHOT(registry);
    CHECK(members(snapshot)==expected);
    // Replace an existing key without count change. No resources/callback effects.
    values[65].fd=values[1].fd;registry._add(&values[65],777);
    CHECK(registry.get_event_num()==65);CHECK(registry.get_socket(values[1].fd)==&values[65]);
    CHECK(members(snapshot)==expected);
    registry._del(&values[2]);CHECK(!registry._exists(&values[2]));CHECK(registry.get_event_num()==64);
    values[66].fd=999;registry._set(&values[66],12);CHECK(!registry._exists(&values[66]));CHECK(values[66].events==12);
    registry._add(&values[66],14);CHECK(registry._exists(&values[66]));CHECK(registry.get_event_num()==65);
    CHECK(members(snapshot)==expected);
    std::map<int,Socket*> visited;
    registry.foreach_socket([&visited](int key,Socket *value){visited.emplace(key,value);});
    CHECK(visited==members(LIVE(registry)));
    CHECK(visited.count(values[2].fd)==0);CHECK(visited.at(values[1].fd)==&values[65]);
    // Layout ABI facts use actual compiled C declarations and target Rust facts.
    CHECK(swr_v1_reactor_sockets_layout(0,0)==sizeof(swr_v1_reactor_socket_entry));
    CHECK(swr_v1_reactor_sockets_layout(0,1)==alignof(swr_v1_reactor_socket_entry));
    CHECK(swr_v1_reactor_sockets_layout(0,2)==offsetof(swr_v1_reactor_socket_entry,fd));
    CHECK(swr_v1_reactor_sockets_layout(0,3)==offsetof(swr_v1_reactor_socket_entry,token));
    CHECK(swr_v1_reactor_sockets_layout(1,0)==sizeof(swr_v1_reactor_socket_cursor));
    CHECK(swr_v1_reactor_sockets_layout(1,1)==alignof(swr_v1_reactor_socket_cursor));
    CHECK(swr_v1_reactor_sockets_layout(1,2)==offsetof(swr_v1_reactor_socket_cursor,current));
    CHECK(swr_v1_reactor_sockets_layout(1,3)==offsetof(swr_v1_reactor_socket_cursor,generation));
    CHECK(swr_v1_reactor_sockets_layout(1,4)==offsetof(swr_v1_reactor_socket_cursor,started));
    CHECK(swr_v1_reactor_sockets_layout(1,5)==offsetof(swr_v1_reactor_socket_cursor,done));
    std::cout << "{\"common\":{\"checks\":" << checks << ",\"members\":"<<visited.size()<<",\"snapshot_members\":"<<expected.size()<<"},\"live_order\":";
    order(LIVE(registry));std::cout << ",\"snapshot_order\":";order(snapshot);std::cout << "}\n";
}
