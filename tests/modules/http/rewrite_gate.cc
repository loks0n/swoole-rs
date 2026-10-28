#include "rewrite_oracle.h"
using Rules=std::vector<std::pair<std::string,std::string>>;
static size_t cases=0,failures=0;
static void compare(const std::string &url,const Rules &rules,bool fail=false){
 upstream_rewrite::Server old;candidate_rewrite::Server candidate;
 for(auto &r:rules){old.add_rewrite_rule(r.first,r.second);candidate.add_rewrite_rule(r.first,r.second);}
 if(bool(old.rewrite_rules)!=bool(candidate.rewrite_rules))throw std::runtime_error("rule owner mismatch");
 if(old.rewrite_rules){if(old.rewrite_rules->size()!=candidate.rewrite_rules->size())throw std::runtime_error("rule count");for(size_t i=0;i<rules.size();++i){auto &a=(*old.rewrite_rules)[i];auto &b=(*candidate.rewrite_rules)[i];if(a.pattern!=b.pattern||a.replacement!=b.replacement||a.is_regex!=b.is_regex)throw std::runtime_error("rule classification");}}
 upstream_rewrite::http_server::StaticHandler a(url);candidate_rewrite::http_server::StaticHandler b(url);a.fail_publish=b.fail_publish=fail;bool x=false,y=false,tx=false,ty=false;
 try{x=old.apply_rewrite_rules(&a);}catch(const std::bad_alloc&){tx=true;}
 try{y=candidate.apply_rewrite_rules(&b);}catch(const std::bad_alloc&){ty=true;}
 if(x!=y||tx!=ty||a.url!=b.url||a.original!=b.original||a.publications!=b.publications)throw std::runtime_error("rewrite outcome mismatch case "+std::to_string(cases));
 if(tx&&(a.url!=url||b.url!=url))throw std::runtime_error("failed publication changed request");
 ++cases;failures+=tx;
}
int main(){try{try{throw std::bad_alloc();}catch(const std::bad_alloc&){}
 std::vector<Rules> rules={ {},{{"",""}},{{"","/fallback"}},{{"/a","/b"}},{{"/a","/a"}},{{"/a","/first"},{"/a","/second"}},{{"~^/a$~","/regex"},{"/","/literal"}},{{"~[~","invalid"},{"/a","fallback"}},{{"~a~","a"},{"","fallback"}},{{"~~","x"}},{{"~(a)(b)~","$2/$1"}},{{"~","/literal"}},{{std::string("/a\0",3),std::string("/b\0",3)}} };
 std::vector<std::string> urls={"","/","/a","/a/b","/ab","/aa",std::string("/a\0tail",7),std::string(4096,'a')};
 for(auto &url:urls)for(auto &r:rules){compare(url,r);compare(url,r,true);}
 {std::mt19937 rng(34129);for(unsigned i=0;i<2048;++i){std::string url;for(unsigned n=rng()%80;n--;)url.push_back(static_cast<char>(rng()%256));Rules r;for(unsigned n=rng()%8;n--;){std::string prefix=url.substr(0,url.empty()?0:rng()%(url.size()+1)),replacement;for(unsigned m=rng()%80;m--;)replacement.push_back(static_cast<char>(rng()%256));if(rng()%2)prefix="mismatch"+prefix;r.emplace_back(prefix,replacement);}compare(url,r);}}
 upstream_rewrite::Server a;candidate_rewrite::Server b;if(a.apply_rewrite_rules(nullptr)||b.apply_rewrite_rules(nullptr))throw std::runtime_error("null rules short circuit");
 std::cout<<"{\"rewrite_cases\":"<<cases<<",\"native_publication_failures\":"<<failures<<",\"null_rule_short_circuit_groups\":1,\"errors\":0}\n";return 0;}catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}}
