// Exact response methods on initialized native models; no parser, socket or IO.
#include <cassert>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>
#include "swoole_rs_wrappers.h"
#define SW_STRL(s) s, sizeof(s)-1
#define sw_unlikely(x) (x)
static std::ostringstream trace;
#include "format.inc"
static void swoole_warning(const char *text) { trace << "warning:" << text << ';'; }
static const char *get_status_message(int code) { return code == 404 ? "404 Not Found" : "200 OK"; }
struct Buffer {
    std::string bytes;
    const char *str = nullptr;
    size_t length = 0;
    void clear() { trace << "clear;"; bytes.clear(); str=bytes.data(); length=0; }
    void append(const char *data, size_t size) {
        trace << "append:" << size << ':'; trace.write(data,size); trace << ';';
        bytes.append(data,size); str=bytes.data(); length=bytes.size();
    }
    void append(const char *data) { append(data,strlen(data)); }
};
static Buffer buffers[2];
static unsigned current_buffer;
static Buffer *sw_tg_buffer() { trace << "buffer:" << current_buffer << ';'; return &buffers[current_buffer]; }
struct ObservedBool {
    bool value=false, retired=false;
    operator bool() const { assert(!retired); trace << "keepalive:" << value << ';'; return value; }
};
struct Server {
    unsigned identity;
    unsigned *sends=nullptr;
    int header_keepalive=-1, body_keepalive=-1;
    bool reseat=false;
    ObservedBool *keepalive=nullptr;
    Server **server=nullptr;
    unsigned *session=nullptr;
    Server *other=nullptr;
    bool send(unsigned id, const char *data, size_t length) {
        trace << "send:" << identity << ':' << id << ':' << length << ':';
        trace.write(data,length); trace << ';';
        int next=(*sends)++ == 0 ? header_keepalive : body_keepalive;
        if (next>=0) keepalive->value=next;
        current_buffer ^= 1; // a native effect may replace the TLS buffer
        if(reseat) { *server=other; *session+=7; }
        return true;
    }
    void close(unsigned id, bool reset) {
        trace << "close:" << identity << ':' << id << ':' << reset << ';';
        keepalive->retired=true; // observation fence, not destruction/invalid storage
    }
};
namespace Original {
struct Context {
    struct { int code=200; std::unordered_map<std::string,std::string> headers; } response;
    ObservedBool keepalive;
    Server *server_;
    unsigned session_id_=17;
    bool end(const char *, size_t);
};
#include "original.inc"
}
namespace Selected {
struct Context {
    struct { int code=200; std::unordered_map<std::string,std::string> headers; } response;
    ObservedBool keepalive;
    Server *server_;
    unsigned session_id_=17;
    bool end(const char *, size_t);
};
#include "selected.inc"
}
static uint32_t seed=0x471ad51;
static uint32_t random_word() { seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed; }
template<class T> static std::string run(unsigned sample, bool keepalive, int header_next, int body_next,
                                       bool reseat, const std::string &body,
                                       const std::vector<std::pair<std::string,std::string>> &headers) {
    trace.str(""); trace.clear(); current_buffer=0;
    for(auto &b:buffers) {b.bytes.clear();b.str=b.bytes.data();b.length=0;}
    T ctx; ctx.keepalive.value=keepalive; ctx.response.code=sample%2 ? 200:404;
    for(const auto &h:headers) ctx.response.headers[h.first]=h.second;
    unsigned sends=0; Server a{},b{}; a.identity=1;b.identity=2;ctx.server_=&a;
    for(auto *s:{&a,&b}) {
        s->sends=&sends;s->header_keepalive=header_next;s->body_keepalive=body_next;s->reseat=reseat;
        s->keepalive=&ctx.keepalive;s->server=&ctx.server_;s->session=&ctx.session_id_;
        s->other=s==&a?&b:&a;
    }
    bool result=ctx.end(body.empty()?nullptr:body.data(),body.size());
    trace << "result:" << result << ";headers:";
    for(auto &h:ctx.response.headers) trace << h.first << ':' << h.second << ';';
    return trace.str();
}
int main() {
    size_t cases=0;
    for(unsigned sample=0;sample<160;sample++) {
        std::string body(sample%7==0?0:random_word()%4096,'\0');
        for(char &c:body)c=static_cast<char>(random_word());
        std::vector<std::pair<std::string,std::string>> headers={{"Content-Length","original"},{"X-Sample",std::to_string(sample)}};
        for(unsigned i=0;i<sample%5;i++) {
            std::string name="X-"+std::to_string(i),value(random_word()%1600,'\0');
            for(char &c:value)c=static_cast<char>(random_word());
            if(sample%11==0)name.append("\0ignored",8);
            headers.emplace_back(name,value);
        }
        for(bool initial:{false,true})for(int h:{-1,0,1})for(int b:{-1,0,1})for(bool reseat:{false,true}) {
            auto expected=run<Original::Context>(sample,initial,h,b,reseat,body,headers);
            auto actual=run<Selected::Context>(sample,initial,h,b,reseat,body,headers);
            if(expected!=actual) {fprintf(stderr,"response trace mismatch sample=%u keepalive=%d header=%d body=%d reseat=%d\n",sample,initial,h,b,reseat);return 1;}
            cases++;
        }
    }
    size_t decimal_cases=0;
    std::vector<size_t> lengths={0,1,9,10,99,100,SIZE_MAX,SIZE_MAX-1};
    for(unsigned i=0;i<16384;i++)lengths.push_back(size_t((uint64_t(random_word())<<32)|random_word()));
    for(size_t length:lengths) {
        unsigned char bytes[sizeof(size_t)*8+2];memset(bytes,0xa5,sizeof(bytes));
        size_t count=swr_v1_wrappers_content_length(length,bytes+1,sizeof(bytes)-2);
        assert(count<sizeof(bytes)-1);
        assert(std::string((const char*)bytes+1,count)==std::to_string(length));
        assert(bytes[0]==0xa5&&bytes[count+1]==0xa5&&bytes[sizeof(bytes)-1]==0xa5);
        decimal_cases++;
    }
    printf("%zu decimal formatting and %zu normal exact-method response comparisons passed\n",decimal_cases,cases);
}
