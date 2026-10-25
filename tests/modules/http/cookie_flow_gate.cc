#include "headers_oracle.h"
#include <iostream>
namespace upstream_headers { Scratch *sw_tg_buffer(){static Scratch scratch;return &scratch;} }
namespace candidate_headers { Scratch *sw_tg_buffer(){static Scratch scratch;return &scratch;} }
int main(){try{
    using Pair=std::pair<std::string,std::string>;
    unsigned cases=0;
    auto compare=[&](const std::string &input,bool stop){
        std::vector<Pair> before,after;
        auto run=[&](auto parse,auto scratch,std::vector<Pair>&out){
            std::fill(scratch()->storage.begin(),scratch()->storage.end(),'?');
            parse(input.data(),input.size(),[&](char *key,size_t keylen,char *value,size_t length){
                out.emplace_back(std::string(key,keylen),std::string(value,length));
                return !stop || out.size()!=1;
            });
        };
        run(upstream_headers::parse_cookie,upstream_headers::sw_tg_buffer,before);
        run(candidate_headers::parse_cookie,candidate_headers::sw_tg_buffer,after);
        if(before!=after || upstream_headers::sw_tg_buffer()->storage!=candidate_headers::sw_tg_buffer()->storage)
            throw std::logic_error("Original cookie callback sequence/scratch bytes differ");
        if(stop && before.size()!=1)throw std::logic_error("Ordinary callback stop count");
        ++cases;
    };
    for(const auto &input:std::vector<std::string>{"first=one", "first=one; second=two; last=three", "first=one; flag; empty=; last=three", "name=plain; path=/ordinary; domain=example.test"})
        for(bool stop:{false,true})compare(input,stop);
    for(unsigned count=1;count<=16;++count)for(unsigned width=1;width<=8;++width){
        std::string input;
        for(unsigned i=0;i<count;++i){if(i)input+="; ";input+="field"+std::to_string(i)+"="+std::string(width,char('a'+i));}
        for(bool stop:{false,true})compare(input,stop);
    }
    std::cout<<"{\"ordinary_original_cookie_cases\":"<<cases<<",\"fault_reentry_alias_profiles_executed\":false,\"full_gate_passed\":false}"<<std::endl;
}catch(const std::exception &error){std::cerr<<error.what()<<std::endl;return 1;}}
