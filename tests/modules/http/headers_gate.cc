#include "headers_oracle.h"
#include <iostream>
#include <cstring>
#define DEFINE_FIXTURE(namespace_name) namespace namespace_name { \
Allocation events[32]; unsigned attempts=0;int fail_at=-1;Request *observed=nullptr;FormData *allocated[32];unsigned owned=0; \
FormData::FormData() { if(attempts>=32)throw std::runtime_error("too many allocations"); \
    events[attempts]={observed->known_length,observed->keep_alive,observed->chunked,observed->nobody_chunked,observed->header_parsed,observed->content_length_,errno}; \
    if(int(attempts++)==fail_at)throw std::bad_alloc();allocated[owned++]=this;errno=EINTR; } \
Scratch *sw_tg_buffer(){static Scratch scratch;return &scratch;} \
void reset(){for(unsigned i=0;i<owned;++i)delete allocated[i];owned=attempts=0;fail_at=-1;std::fill(sw_tg_buffer()->storage.begin(),sw_tg_buffer()->storage.end(),'?');} }
DEFINE_FIXTURE(upstream_headers)
DEFINE_FIXTURE(candidate_headers)
#undef DEFINE_FIXTURE
void check(bool value,const char *message){if(!value)throw std::runtime_error(message);}
int main(){try{
    unsigned cases=0;
    auto metadata=[&](const std::string &fields,bool seeded,int fail){
        upstream_headers::reset();candidate_headers::reset();
        std::string input="GET / HTTP/1.1\r\n"+fields+"\r\n";
        upstream_headers::Buffer a{input.data(),input.size()};candidate_headers::Buffer b{input.data(),input.size()};
        upstream_headers::Request before;candidate_headers::Request after;before.buffer_=&a;after.buffer_=&b;
        before.header_length_=after.header_length_=input.size();
        if(seeded){before.content_length_=after.content_length_=41;before.known_length=after.known_length=1;before.keep_alive=after.keep_alive=1;before.nobody_chunked=after.nobody_chunked=1;before.header_parsed=after.header_parsed=1;}
        upstream_headers::observed=&before;candidate_headers::observed=&after;upstream_headers::fail_at=candidate_headers::fail_at=fail;
        bool failed_a=false,failed_b=false;errno=0;try{before.parse_header_info();}catch(const std::bad_alloc&){failed_a=true;}int error=errno;
        errno=0;try{after.parse_header_info();}catch(const std::bad_alloc&){failed_b=true;}
        if(error!=errno||failed_a!=failed_b||before.content_length_!=after.content_length_||before.known_length!=after.known_length||before.keep_alive!=after.keep_alive||before.chunked!=after.chunked||before.nobody_chunked!=after.nobody_chunked||before.header_parsed!=after.header_parsed||before.excepted!=after.excepted) {
            std::cerr<<"fields="<<fields<<" seeded="<<seeded<<" fail="<<fail<<"\n";
            std::cerr<<"errno "<<error<<"/"<<errno<<" content "<<before.content_length_<<"/"<<after.content_length_<<" flags "<<before.known_length<<before.keep_alive<<before.chunked<<before.nobody_chunked<<before.header_parsed<<before.excepted<<"/"<<after.known_length<<after.keep_alive<<after.chunked<<after.nobody_chunked<<after.header_parsed<<after.excepted<<"\n";
        }
        check(error==errno&&failed_a==failed_b&&before.content_length_==after.content_length_&&before.known_length==after.known_length&&before.keep_alive==after.keep_alive&&before.chunked==after.chunked&&before.nobody_chunked==after.nobody_chunked&&before.header_parsed==after.header_parsed&&before.excepted==after.excepted,"metadata fields/errno/exception timing");
        check(upstream_headers::attempts==candidate_headers::attempts,"allocation event count");
        for(unsigned i=0;i<upstream_headers::attempts;++i){auto &x=upstream_headers::events[i];auto &y=candidate_headers::events[i];check(x.known==y.known&&x.alive==y.alive&&x.chunked==y.chunked&&x.nobody==y.nobody&&x.parsed==y.parsed&&x.content==y.content&&x.error==y.error,"state at allocation boundary");}
        check((before.form_data_==nullptr)==(after.form_data_==nullptr),"multipart ownership publication");
        if(before.form_data_){check(before.form_data_->multipart_boundary_len==after.form_data_->multipart_boundary_len&&std::string(before.form_data_->multipart_boundary_buf,before.form_data_->multipart_boundary_len)==std::string(after.form_data_->multipart_boundary_buf,after.form_data_->multipart_boundary_len),"multipart span");}
        upstream_headers::reset();candidate_headers::reset();++cases;
    };
    const std::vector<std::string> fields={"", "Content-Length: 0\r\n", "content-length: +41\r\n", "Content-Length: -1\r\n", "Content-Length: 18446744073709551616\r\n", "Content-Length: -18446744073709551615\r\n", "Content-Length: junk\r\n", "Content-Length:\t42\r\n", "Connection: keep-alive-extra\r\n", "Connection: close\r\n", "Transfer-Encoding: chunked-extra\r\n", "Transfer-Encoding: gzip, chunked\r\n", "Content-Type: multipart/form-data; boundary=abc\r\n", "Content-Type: multipart/form-data\r\n", "Content-Type: text/plain\r\n", "XContent-Length: 1\r\n", " Content-Length: 4\r\n"};
    for(auto &x:fields)for(auto &y:fields)for(bool seeded:{false,true})metadata(x+y,seeded,-1);
    const std::string multi="Content-Length: 18446744073709551616\r\nContent-Type: multipart/form-data; boundary=a\r\nContent-Length: 0\r\nTransfer-Encoding: chunked\r\nContent-Type: multipart/form-data; boundary=b\r\nConnection: keep-alive\r\n";
    for(int fail:{-1,0,1})for(bool seeded:{false,true})metadata(multi,seeded,fail);
    auto cookies=[&](const std::string &input,unsigned mode){
        upstream_headers::reset();candidate_headers::reset();using Pair=std::pair<std::string,std::string>;std::vector<Pair>a,b;
        auto run=[&](auto parse,auto scratch,std::vector<Pair>&out){
            try{parse(input.data(),input.size(),[&](char *key,size_t keylen,char *value,size_t value_len){
                out.emplace_back(std::string(key,keylen),std::string(value,value_len));
                if(mode==1&&out.size()==1)return false;
                if(mode==2&&out.size()==1)throw std::runtime_error("callback");
                if(mode==3&&out.size()==1)parse("n=1; rewritten=2; final=3",25,[&](char*k,size_t kl,char*v,size_t vl){out.emplace_back(std::string(k,kl),std::string(v,vl));return true;});
                if(mode==4&&value_len)value[0]='!';
                if(mode==5&&out.size()==1&&input=="a=1;b=2;c=3;d=4")scratch()->str[4]='z';
                return true;});}catch(const std::runtime_error&e){check(std::string(e.what())=="callback","unexpected callback failure");}
            return std::vector<char>(scratch()->storage.begin(),scratch()->storage.end());
        };
        auto aa=run(upstream_headers::parse_cookie,upstream_headers::sw_tg_buffer,a);auto bb=run(candidate_headers::parse_cookie,candidate_headers::sw_tg_buffer,b);
        check(a==b&&aa==bb,"cookie callback/recursive mutation/scratch differential");++cases;
    };
    for(auto &input:std::vector<std::string>{"","a=b",";; a =x=y; =bad;novalue;\tlast=", "form-data; name=\"x\"; filename=\"a.txt\"", "a=1;b=2;c=3;d=4",std::string("a=x\0b=y",7)})for(unsigned mode=0;mode<6;++mode)cookies(input,mode);
    uint32_t seed=11293;auto next=[&](){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;};
    for(unsigned trial=0;trial<2048;++trial){std::string input;for(unsigned i=0,n=1+next()%16;i<n;++i){input+="; \t"[next()%3];input+='a'+next()%26;if(next()%2){input+='=';for(unsigned j=0,n=next()%12;j<n;++j)input+="ab ;=\t\r\n"[next()%8];}}cookies(input,trial%3);}
    auto small=candidate_headers::sw_tg_buffer();
    for(bool alias:{false,true}) {
        std::vector<char>(4,'?').swap(small->storage);small->str=small->storage.data();small->size=4;
        const char input[]="a=b;";if(alias)std::memcpy(small->str,input,4);
        unsigned count=0;candidate_headers::parse_cookie(alias?small->str:input,4,[&](char*k,size_t kl,char*v,size_t vl){check(std::string(k,kl)=="a"&&std::string(v,vl)=="b","grown scratch bytes");++count;return true;});
        check(count==1&&small->size>=5,"scratch reserve and alias rebasing");
    }
    small->reserve(65536);
    std::cout<<"{\"header_cookie_differential_cases\":"<<cases<<",\"corrected_scratch_cases\":2,\"errors\":0}\n";
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
