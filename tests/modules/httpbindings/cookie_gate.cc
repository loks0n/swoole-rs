#include "cookie_oracle.h"
#include <iostream>
#include <memory>
thread_local Oracle *oracle;
struct Input {
    std::vector<std::string> fields={"name","value","/","example.test","Lax","High"};
    uint32_t absent=0, flags=15;
    int64_t expires=1700000010;
};
struct Result {
    std::vector<std::string> trace;
    std::string output, partial;
    bool success=false, bailed=false, deleted=false;
    bool operator==(const Result &r) const {
        return trace==r.trace && output==r.output && partial==r.partial && success==r.success && bailed==r.bailed && deleted==r.deleted;
    }
};
template<class Cookie> Result run(const Input &in, size_t fail=SIZE_MAX, unsigned reentry=0) {
    Oracle local; oracle=&local; local.fail=fail;
    auto *cookie=new Cookie;
    std::vector<zend_string> strings; strings.reserve(6);
    for(const auto &s:in.fields)strings.push_back({s});
    zend_string **slots[]={&cookie->name,&cookie->value,&cookie->path,&cookie->domain,&cookie->sameSite,&cookie->priority};
    for(unsigned i=0;i<6;i++)*slots[i]=(in.absent&(1u<<i))?nullptr:&strings[i];
    cookie->expires=in.expires; cookie->encode_=in.flags&1;cookie->secure=in.flags&2;cookie->httpOnly=in.flags&4;cookie->partitioned=in.flags&8;
    Result result;
    if(reentry) local.warning=[&](){
        auto kind=reentry; reentry=0;
        if(kind==1){result.partial=cookie->buffer_.value;delete cookie;cookie=nullptr;result.deleted=true;}
        else if(kind==2){cookie->buffer_.value.clear();cookie->name=&strings[0];strings[0].value="reset";}
        else {cookie->name=&strings[0];cookie->value=&strings[1];cookie->path=nullptr;cookie->domain=nullptr;strings[0].value="nested";strings[1].value="ok";cookie->expires=0;auto *s=cookie->toString();if(s)zend_string_free(s);}
    };
    try {auto *s=cookie->toString();if(s){result.success=true;result.output=s->value;zend_string_free(s);}}
    catch(const Bailout &){result.bailed=true;}
    if(cookie){result.partial=cookie->buffer_.value;delete cookie;}
    result.trace=local.trace;return result;
}
static size_t comparisons=0,faults=0,reentries=0;
static void check(const Input &in, bool fault=false) {
    auto old=run<upstream_cookie::HttpCookie>(in);auto candidate=run<candidate_cookie::HttpCookie>(in);
    if(!(old==candidate))throw std::runtime_error("cookie order/output/partial mismatch at "+std::to_string(comparisons));
    comparisons++;
    if(fault) for(size_t f=0;f<old.trace.size();f++) {
        if(!(run<upstream_cookie::HttpCookie>(in,f)==run<candidate_cookie::HttpCookie>(in,f)))throw std::runtime_error("cookie native effect fault mismatch");
        faults++;
    }
}
int main(){try{
    for(unsigned field=0;field<6;field++)for(unsigned c=0;c<256;c++)for(unsigned flags=0;flags<16;flags++){
        Input in;in.fields[field]=std::string("a")+char(c)+"z";in.flags=flags;check(in,c%31==0 && flags%5==0);
    }
    for(int64_t expires:{int64_t(-1),int64_t(0),int64_t(1),int64_t(1699999999),int64_t(1700000000),int64_t(1700000010),int64_t(253402300799),int64_t(253402300800),INT64_MAX})
      for(unsigned flags=0;flags<16;flags++)for(unsigned absent=0;absent<64;absent++){
        Input in;in.expires=expires;in.flags=flags;in.absent=absent;check(in,flags==0 && absent%17==0);
      }
    for(unsigned field=0;field<6;field++) {Input in;in.fields[field]="";check(in,true);}
    for(unsigned field:{0u,1u,2u,3u})for(unsigned kind=1;kind<=3;kind++) {
        Input in;in.flags=0;in.fields[field]="illegal;value";
        if(!(run<upstream_cookie::HttpCookie>(in,SIZE_MAX,kind)==run<candidate_cookie::HttpCookie>(in,SIZE_MAX,kind)))throw std::runtime_error("cookie warning reentry mismatch");reentries++;
    }
    std::cout<<"{\"cases\":"<<comparisons<<",\"native_effect_faults\":"<<faults<<",\"warning_reentries\":"<<reentries<<",\"errors\":0}\n";return 0;
}catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}}
