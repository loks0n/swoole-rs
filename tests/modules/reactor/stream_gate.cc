#include <cassert>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <functional>
#include <iostream>
#include <string>
#include <vector>
#include <algorithm>
#include <arpa/inet.h>
#include <sys/socket.h>
#include "swoole_rs_reactor.h"
constexpr int SW_ERR=-1;
struct Socket {
    uint32_t close_wait=0;
    unsigned calls=0;
    int first_result=4,body_result=1;
    uint8_t prefix[4]{};
    std::vector<std::string> trace;
    ssize_t recv_sync(void *out,size_t length,int flags) {
        assert(flags==MSG_WAITALL);
        trace.push_back("recv:"+std::to_string(length));
        if(calls++==0) {
            assert(length==4);
            if(first_result>0)memcpy(out,prefix,first_result);
            if(first_result<0)errno=EBADF;
            return first_result;
        }
        if(body_result<0){errno=EIO;return -1;}
        size_t n=std::min(length,static_cast<size_t>(body_result));memset(out,'x',n);return n;
    }
};
struct String {
    alignas(uint32_t) char storage[128];
    char *str=storage;
    size_t length;
    bool *destroyed;
    String(size_t length,bool *destroyed):length(length),destroyed(destroyed){memset(storage,0xa5,sizeof(storage));}
    ~String(){*destroyed=true;}
};
struct Stream {
    bool cancel=false;
    String *buffer=nullptr;
    std::function<void(Stream*,const char*,uint32_t)> response;
};
struct Client {
    Stream *object;
    Socket *socket;
    std::vector<std::string> trace;
    uint8_t encoded[4]{};
    int send_result=1;
    void close(){trace.push_back("close");errno=EBADF;}
    int send(const char *data,size_t length,int flags) {
        assert(flags==0);memcpy(encoded,data,4);
        trace.push_back("send:"+std::to_string(length));
        if(send_result<0)errno=EPIPE;
        return send_result;
    }
};
#include "stream.inc"
struct ConnectResult {
    std::vector<std::string> trace;
    std::vector<uint8_t> encoded;
    bool destroyed,retained;
    int error;
    bool operator==(const ConnectResult &o)const{return trace==o.trace&&encoded==o.encoded&&destroyed==o.destroyed&&retained==o.retained&&error==o.error;}
};
static ConnectResult connect(int variant,size_t length,bool cancel,int sent) {
    bool destroyed=false;Socket socket;Stream stream;stream.cancel=cancel;stream.buffer=new String(length,&destroyed);
    Client client{&stream,&socket};client.send_result=sent;errno=EDOM;
    if(variant)Variant1::Stream_onConnect(&client);else Variant0::Stream_onConnect(&client);
    uint32_t expected=static_cast<uint32_t>(length-4);
    uint8_t bytes[]={static_cast<uint8_t>(expected>>24),static_cast<uint8_t>(expected>>16),static_cast<uint8_t>(expected>>8),static_cast<uint8_t>(expected)};
    assert(memcmp(bytes,client.encoded,4)==0);
    ConnectResult out{client.trace,std::vector<uint8_t>(client.encoded,client.encoded+4),destroyed,stream.buffer!=nullptr,errno};
    assert(out.destroyed==(sent>=0) && out.retained==(sent<0));
    assert(!cancel || out.trace.front()=="close");
    delete stream.buffer;return out;
}
static std::vector<uint64_t> receive(int variant,uint32_t length,int closed) {
    Socket socket;socket.close_wait=closed;Stream stream;Client client{&stream,&socket};char data[128]{};
    std::vector<uint64_t> out;
    stream.response=[&](Stream *s,const char *body,uint32_t n){assert(s==&stream);out={static_cast<uint64_t>(body-data),n};};
    if(variant)Variant1::Stream_onReceive(&client,data,length);else Variant0::Stream_onReceive(&client,data,length);
    if(length==4)assert(out.empty() && socket.close_wait);
    else assert(out==std::vector<uint64_t>({4,static_cast<uint32_t>(length-4)}));
    out.push_back(socket.close_wait);return out;
}
struct SyncResult {
    std::vector<std::string> trace;
    std::vector<char> bytes;
    ssize_t result;
    int error;
    bool operator==(const SyncResult&o)const{return trace==o.trace&&bytes==o.bytes&&result==o.result&&error==o.error;}
};
static SyncResult sync(int variant,uint32_t length,size_t capacity,int first,int second) {
    Socket socket;uint32_t network=htonl(length);memcpy(socket.prefix,&network,4);socket.first_result=first;socket.body_result=second;
    char data[128]{};errno=EDOM;
    ssize_t result=variant?Variant1::recv_sync(&socket,data,capacity):Variant0::recv_sync(&socket,data,capacity);
    return {socket.trace,std::vector<char>(data,data+sizeof(data)),result,errno};
}
int main() {
    unsigned connects=0,receives=0,syncs=0;
    const size_t totals[]={0,1,3,4,5,128,static_cast<size_t>(UINT32_MAX)+5,SIZE_MAX};
    for(size_t length:totals)for(bool cancel:{false,true})for(int sent:{-1,0,1,127}){assert(connect(0,length,cancel,sent)==connect(1,length,cancel,sent));++connects;}
    for(uint32_t length:{0u,1u,3u,4u,5u,64u,UINT32_MAX})for(int closed=0;closed<2;closed++){assert(receive(0,length,closed)==receive(1,length,closed));++receives;}
    const size_t capacities[]={0,1,8,128,INT32_MAX,static_cast<size_t>(INT32_MAX)+1,UINT32_MAX,static_cast<size_t>(UINT32_MAX)+9,SIZE_MAX};
    for(uint32_t length:{0u,1u,8u,static_cast<uint32_t>(INT32_MAX),static_cast<uint32_t>(INT32_MAX)+1,UINT32_MAX})for(size_t capacity:capacities)for(int first:{-1,0,1,2,3,4})for(int second:{-1,0,1,7}) {
        assert(sync(0,length,capacity,first,second)==sync(1,length,capacity,first,second));++syncs;
    }
    std::cout<<"stream_connect="<<connects<<" receive="<<receives<<" sync="<<syncs<<" errors=0\n";
}
