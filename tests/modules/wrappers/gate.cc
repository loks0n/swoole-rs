#include "swoole_rs_wrappers.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#include <thread>
#include <atomic>
#include <sys/wait.h>
#include <unistd.h>
static std::atomic<unsigned> checks{0};
#define CHECK(x) do { if(!(x)) { std::fprintf(stderr,"failed line %d: %s\n",__LINE__,#x); std::abort(); } ++checks; } while(0)
static const uint8_t *bytes(const std::string &s) { return (const uint8_t *)s.data(); }
static std::string text(SwrWrapperSpan s) { return std::string((const char *)s.data,s.len); }
static SwrWrapperView view(SwrWrapperRequest *p) { SwrWrapperView v{};CHECK(!swr_v1_wrappers_request_view(p,&v));return v; }
static int header(SwrWrapperRequest *p,const std::string &s){return swr_v1_wrappers_header(p,bytes(s),s.size());}
static int kind(SwrWrapperRequest *p,int method,const std::string &s,bool multipart=false){return swr_v1_wrappers_header_kind(p,method,bytes(s),s.size(),multipart);}
static int param(SwrWrapperRequest*p,const std::string&k,const std::string&v){return swr_v1_wrappers_parameter(p,bytes(k),k.size(),bytes(v),v.size());}
static void lifecycle(){
    auto p=swr_v1_wrappers_request_new();CHECK(p);CHECK(view(p).flags==0);
    CHECK(header(p,"Content-Type")==0);
    for(int method=0;method<50;method++){
        bool allowed=method==0||method==3||method==4||method==28;
        CHECK(kind(p,method,"Application/X-WWW-Form-Urlencoded; charset=utf8")==int(allowed));
        CHECK(kind(p,method,"MULTIPART/FORM-DATA; boundary=abc")==int(allowed)*2);
        CHECK(kind(p,method,"multipart/form-dat")==0);
    }
    CHECK(!header(p,"content-disposition"));CHECK(kind(p,0,"anything",true)==3);
    swr_v1_wrappers_disposition_begin(p);CHECK(!param(p,"name","first"));CHECK(!param(p,"Name","ignored"));CHECK(!param(p,"name","last"));CHECK(!swr_v1_wrappers_disposition_end(p));CHECK(text(view(p).form)=="last");
    std::string data("a\0b",3);CHECK(!swr_v1_wrappers_body_append(p,bytes(data),data.size()));CHECK(text(view(p).body)==data);
    swr_v1_wrappers_part_end(p);CHECK(view(p).form.len==0&&view(p).body.len==0&&view(p).header.len==0);
    swr_v1_wrappers_disposition_begin(p);CHECK(!param(p,"name","field"));CHECK(!param(p,"filename","image.jpg"));CHECK(!swr_v1_wrappers_disposition_end(p));CHECK(text(view(p).input)=="image.jpg");CHECK(view(p).form.len==0); // pinned file-name/form-key quirk
    swr_v1_wrappers_part_end(p);swr_v1_wrappers_disposition_begin(p);CHECK(swr_v1_wrappers_disposition_end(p)==-1); // explicit pinned UB correction
    CHECK(!header(p,"Swoole-Upload-File"));CHECK(kind(p,0,"/tmp/file",true)==4);
    std::string leading="\r\n\r--abc";CHECK(swr_v1_wrappers_body_skip(p,bytes(leading),leading.size())==3);CHECK(!swr_v1_wrappers_body_skip(p,bytes(leading),leading.size()));
    swr_v1_wrappers_complete(p);CHECK(view(p).flags==1);swr_v1_wrappers_request_free(p);
}
int main(){
    for(int event=-2048;event<=2048;event++)CHECK(swr_v1_wrappers_event_direction(event)==(event==512?1:event==1024?2:0));
    for(int wait=0;wait<2;wait++)for(int exit=0;exit<2;exit++)CHECK(swr_v1_wrappers_event_wait(wait,exit)==(!wait||!exit));
    uint64_t seed=0x81f83e95;auto next=[&](){seed^=seed<<13;seed^=seed>>7;seed^=seed<<17;return seed;};
    for(int trial=0;trial<20000;trial++){
        std::string k(next()%1600,'x'),v(next()%1600,'y');for(auto &c:k)c=(char)next();for(auto &c:v)c=(char)next();
        size_t cap=next()%1100;std::vector<char> expected(cap+1,42),actual(cap+1,42);
        int n=std::snprintf(expected.data(),cap,"%s: %s\r\n",k.c_str(),v.c_str());size_t wanted=cap?std::min((size_t)n,cap-1):(size_t)n;
        CHECK(swr_v1_wrappers_header_wire(bytes(k),k.size(),bytes(v),v.size(),(uint8_t*)actual.data(),cap)==wanted);CHECK(expected==actual);
        CHECK(swr_v1_wrappers_split(bytes(k),k.size(),'?')==k.find('?') || (k.find('?')==k.npos && swr_v1_wrappers_split(bytes(k),k.size(),'?')==k.size()));
    }
    std::vector<std::thread> workers;for(int i=0;i<4;i++)workers.emplace_back([]{for(int j=0;j<100;j++)lifecycle();});for(auto&t:workers)t.join();
    auto p=swr_v1_wrappers_request_new();CHECK(p);CHECK(!header(p,"parent"));pid_t child=fork();CHECK(child>=0);if(child==0){CHECK(!header(p,"child"));swr_v1_wrappers_request_free(p);_exit(0);}int status;CHECK(waitpid(child,&status,0)==child&&WIFEXITED(status)&&WEXITSTATUS(status)==0);CHECK(text(view(p).header)=="parent");swr_v1_wrappers_request_free(p);
    CHECK(swr_v1_wrappers_header(nullptr,nullptr,0)==-1);CHECK(swr_v1_wrappers_request_view(nullptr,nullptr)==-1);swr_v1_wrappers_request_free(nullptr);
    std::printf("{\"checks\":%u,\"passed\":true}\n",checks.load());
}
