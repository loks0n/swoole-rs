// Exact original/selected wrapper callbacks; inert parser/context shells only.
#include "swoole_rs_wrappers.h"
#include <cassert>
#include <cctype>
#include <cstring>
#include <strings.h>
#include <functional>
#include <iostream>
#include <string>
#include <unordered_map>
#include <vector>
#define SW_HTTP_UPLOAD_FILE "swoole-upload-file"
#define SW_STRCASEEQ(p,n,s) ((n)==sizeof(s)-1 && strncasecmp(p,s,n)==0)
using ParseCookieCallback=std::function<bool(char*,size_t,char*,size_t)>;
struct Scratch { char str[8192]; };
static Scratch scratch;
static Scratch *sw_tg_buffer() { return &scratch; }
#include "cookie.inc"
struct multipart_parser { void *data; };
namespace original {
struct ContextImpl { std::string current_header_name,current_form_data_name,current_input_name; bool completed=false; };
struct Context { ContextImpl *impl; std::unordered_map<std::string,std::string> files; };
#include "original.inc"
}
namespace selected {
static std::string owned(SwrWrapperSpan s) { return std::string(reinterpret_cast<const char*>(s.data),s.len); }
struct ContextImpl {
    SwrWrapperRequest *state=swr_v1_wrappers_request_new();
    ContextImpl() { assert(state); }
    ~ContextImpl() { swr_v1_wrappers_request_free(state); }
    SwrWrapperView view() const { SwrWrapperView v{};assert(!swr_v1_wrappers_request_view(state,&v));return v; }
};
struct Context { ContextImpl *impl;std::unordered_map<std::string,std::string> files; };
#include "selected.inc"
}
static void seed(SwrWrapperRequest *state,const char *key,const char *value) {
    swr_v1_wrappers_disposition_begin(state);
    assert(!swr_v1_wrappers_parameter(state,reinterpret_cast<const uint8_t*>(key),strlen(key),reinterpret_cast<const uint8_t*>(value),strlen(value)));
    assert(!swr_v1_wrappers_disposition_end(state));
}
static void compare(const std::string &header,const std::string &data) {
    original::ContextImpl before;
    before.current_header_name=header;before.current_form_data_name="old-form";before.current_input_name="old-input";
    original::Context a{&before,{{"retained","path"}}};multipart_parser pa{&a};
    selected::ContextImpl after;seed(after.state,"name","old-form");seed(after.state,"filename","old-input");
    assert(!swr_v1_wrappers_header(after.state,reinterpret_cast<const uint8_t*>(header.data()),header.size()));
    selected::Context b{&after,{{"retained","path"}}};multipart_parser pb{&b};
    assert(original::multipart_body_on_header_value(&pa,data.data(),data.size())==selected::multipart_body_on_header_value(&pb,data.data(),data.size()));
    auto view=after.view();assert(before.current_form_data_name==selected::owned(view.form));assert(before.current_input_name==selected::owned(view.input));
    assert(before.completed==bool(view.flags&1));assert(a.files==b.files);
}
int main() {
    uint64_t cases=0;
    std::vector<std::string> inputs={"form-data; name=x","name","filename","name=","filename=","name=first; name=last","filename=first; filename=last; name=ignored","name=foo; filename=", "name=foo; filename=\"bar\"", " ;\tname=a=b; name =ignored", std::string("name=a\0;name=ignored",20),"\r\n\tname=one;name=two;\tfilename=x","name=x; Filename=y; NAME=z"};
    uint64_t state=0x646973706f736974;
    auto next=[&](){state^=state<<13;state^=state>>7;state^=state<<17;return state;};
    for(unsigned i=0;i<8192;i++) {
        std::string value(next()%96,'x');for(char &c:value)c=char(32+next()%95);
        // Guaranteed defined original name; arbitrary subsequent ASCII tokens,
        // quotes, semicolons, duplicates and whitespace are ordinary metadata.
        std::string data="name=initial;"+value;
        if(i&1)data+=";name="+std::to_string(i);
        if(i&2)data+=";filename="+std::to_string(i^0x1234);
        if(i&4)data+=";filename=";
        if(i&8)data.append("\0;filename=ignored",18);
        inputs.push_back(data);
    }
    for(const auto &data:inputs)for(const char *header:{"content-disposition","Content-Disposition","CONTENT-DISPOSITION","swoole-upload-file","other"}) {compare(header,data);++cases;}
    // Prior staged ABI remains usable after the direct decoder; no new callback
    // or multipart parser executes. Missing-name UB in original is not invoked.
    selected::ContextImpl endpoint;
    const auto before=endpoint.view();(void)before;
    assert(swr_v1_wrappers_disposition(endpoint.state,reinterpret_cast<const uint8_t*>("ignored=x"),9)==-1);
    seed(endpoint.state,"name","staged");assert(selected::owned(endpoint.view().form)=="staged");
    std::cout<<cases<<" exact disposition/file-map metadata cases PASS\n";
}
