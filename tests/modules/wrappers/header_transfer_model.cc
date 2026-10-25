// Proposal-only normal ownership/publication model; no HTTP parser/Context object.
#include "swoole_http.h"
#include <cassert>
#include <cstdint>
#include <functional>
#include <iostream>
#include <memory>
#include <string>
#include <type_traits>
#include <unordered_map>
#include <utility>
#include <vector>
using Context=swoole::http_server::Context;
using Map=decltype(std::declval<Context>().headers);
static_assert(std::is_same<Map,std::unordered_map<std::string,std::string>>::value,"real public map type");
static_assert(std::is_same<decltype(std::declval<Map&>()[std::declval<const std::string&>()]),std::string&>::value,"real string lvalue");
static_assert(std::is_same<decltype(std::declval<Map&>().begin()),Map::iterator>::value,"real native iterator");
using Listen=std::shared_ptr<swoole::Server>(*)(const std::string&,const std::function<void(Context&)>&,int);
static_assert(std::is_same<decltype(&swoole::http_server::listen),Listen>::value,"existing callback signature");
extern "C" {
struct HeaderStore;
struct Sizes {size_t key,value;};
HeaderStore *model_headers_new();
void model_headers_free(HeaderStore*);
int model_headers_set(HeaderStore*,const uint8_t*,size_t,const uint8_t*,size_t);
size_t model_headers_prepare(HeaderStore*);
int model_headers_sizes(const HeaderStore*,size_t,Sizes*);
int model_headers_copy(const HeaderStore*,size_t,uint8_t*,size_t,uint8_t*,size_t);
int model_headers_commit(HeaderStore*);
size_t model_headers_owned_entries(const HeaderStore*);
}
static void publish(HeaderStore *state,Map &destination) {
    assert(destination.empty());
    size_t count=model_headers_prepare(state);assert(count!=size_t(-1));
    Map staging;
    for(size_t i=0;i<count;i++) {
        Sizes size{};assert(!model_headers_sizes(state,i,&size));
        std::string key(size.key,'\0'),value(size.value,'\0');
        assert(!model_headers_copy(state,i,key.empty()?nullptr:reinterpret_cast<uint8_t*>(&key[0]),key.size(),value.empty()?nullptr:reinterpret_cast<uint8_t*>(&value[0]),value.size()));
        staging[std::move(key)]=std::move(value);
    }
    static_assert(noexcept(destination.swap(staging)),"atomic native publication cannot allocate/throw");
    destination.swap(staging);
    assert(!model_headers_commit(state));
    assert(model_headers_owned_entries(state)==0);
}
using Input=std::vector<std::pair<std::string,std::string>>;
static void run(const Input &input) {
    auto *state=model_headers_new();assert(state);Map original,published;
    for(const auto &item:input) {
        original[std::string(item.first.data(),item.first.size())]=std::string(item.second.data(),item.second.size());
        assert(!model_headers_set(state,reinterpret_cast<const uint8_t*>(item.first.data()),item.first.size(),reinterpret_cast<const uint8_t*>(item.second.data()),item.second.size()));
        assert(published.empty());
    }
    publish(state,published);
    assert(original==published&&original.bucket_count()==published.bucket_count());
    auto a=original.begin(),b=published.begin();
    for(;a!=original.end();++a,++b) {
        assert(a->first==b->first&&a->second==b->second);
        assert(a->first.capacity()==b->first.capacity()&&a->second.capacity()==b->second.capacity());
    }
    assert(b==published.end());
    // Ordinary public caller mutation: exact real map/lvalue APIs, no Rust mirror.
    published["callback-value"]="changed";
    auto *address=&published["callback-value"];published.reserve(1024);
    assert(address==&published["callback-value"]&&*address=="changed");
    assert(model_headers_owned_entries(state)==0);
    model_headers_free(state);
}
int main() {
    uint64_t cases=0,seed=0x686561646572;
    auto next=[&](){seed^=seed<<13;seed^=seed>>7;seed^=seed<<17;return seed;};
    run({});++cases;
    run({{"X","a"},{"x","b"},{"X","last"},{std::string("a\0b",3),std::string("c\0d",3)}});++cases;
    for(unsigned count:{1,8,32,128,512})for(unsigned duplicate=0;duplicate<4;duplicate++) {
        Input input;
        for(unsigned i=0;i<count;i++) {
            std::string key="field-"+std::to_string(i),value(i%127,'v');
            input.emplace_back(key,value);
            for(unsigned d=0;d<duplicate;d++)input.emplace_back(key,"replacement-"+std::to_string(d));
        }
        run(input);++cases;
    }
    for(unsigned round=0;round<512;round++) {
        Input input;
        for(unsigned i=0,n=next()%64;i<n;i++) {
            std::string key(next()%32,'k'),value(next()%256,'v');
            for(char &c:key)c=char(next()%128);
            for(char &c:value)c=char(next()%128);
            if(!input.empty()&&(next()&3)==0)key=input[next()%input.size()].first;
            input.emplace_back(key,value);
        }
        run(input);++cases;
    }
    std::cout<<cases<<" positive Rust-to-real-native-map handoff cases PASS; exact types/order/buckets/references, zero Rust payload after publication\n";
}
