#include "path_oracle.h"
#include <iostream>
#include <new>
static bool fail_allocation=false;
static size_t failing_size=0;
void *operator new(size_t size) { if(fail_allocation && (failing_size==0 || size==failing_size)) { fail_allocation=false;throw std::bad_alloc(); }if(void *p=std::malloc(size ? size:1))return p;throw std::bad_alloc(); }
void operator delete(void *p) noexcept { std::free(p); }
void operator delete(void *p,size_t) noexcept { std::free(p); }
void *operator new[](size_t size) { return ::operator new(size); }
void operator delete[](void *p) noexcept { ::operator delete(p); }
void operator delete[](void *p,size_t) noexcept { ::operator delete(p); }
void check(bool value,const char *message) { if(!value)throw std::runtime_error(message); }
int main() {
    try {
        size_t cases=0;
        auto compare=[&](const PathScenario &config) {
            upstream_path::active=candidate_path::active=&config;upstream_path::stat_calls=candidate_path::stat_calls=0;upstream_path::trace.clear();candidate_path::trace.clear();
            upstream_path::Server sa(config);candidate_path::Server sb(config);
            upstream_path::StaticHandler a(&sa,config);candidate_path::StaticHandler b(&sb,config);
            errno=EINTR;bool left=a.try_serve();int ea=errno;
            errno=EINTR;bool right=b.try_serve();int eb=errno;
            if(!(left==right && ea==eb && a.status_code==b.status_code && a.last==b.last && a.l_filename==b.l_filename && a.dir_path==b.dir_path && a.request_url==b.request_url && std::memcmp(a.filename,b.filename,sizeof(a.filename))==0 && std::memcmp(&a.file_stat,&b.file_stat,sizeof(a.file_stat))==0 && upstream_path::trace==candidate_path::trace)) {
                std::cerr<<"case "<<cases<<" url "<<config.url<<" root "<<config.root<<" return "<<left<<":"<<right<<" errno "<<ea<<":"<<eb<<" filename-length "<<a.l_filename<<":"<<b.l_filename<<'\n';
                for(auto &v:upstream_path::trace)std::cerr<<"A "<<v<<'\n';for(auto &v:candidate_path::trace)std::cerr<<"B "<<v<<'\n';
                throw std::runtime_error("static path policy/state/byte/IO-order differential");
            }
            ++cases;
        };
        std::vector<std::string> urls={"","/file.txt","/file.txt?version=1#position","/file.txt#before?after","/../file.txt","/a..b","/%2e%2e/file.txt","/hello+world","/%00after","/%ff%2Ffile","/%bad%3","/UPPER",std::string("/file\0../suffix",15)};
        for(auto &url:urls) for(unsigned mode=0;mode<16;++mode) for(bool last:{false,true}) {
            PathScenario s;s.url=url;s.initial_last=last;s.mime=mode%2;s.index=mode&2;s.autoindex=mode&4;
            if(mode&8)s.locations={"/missing","/upper"};
            for(mode_t type:{S_IFREG,S_IFDIR,S_IFLNK,S_IFIFO}) {s.modes={static_cast<mode_t>(type|0644),S_IFREG|0644};s.stat_ok={true,true};compare(s);s.stat_ok={false};compare(s);s.stat_ok={true,false};compare(s);}
            s.stat_ok={true,true};s.canonical_ok=false;compare(s);
            s.canonical_ok=true;s.canonical="/outside/file.txt";compare(s);
            s.locations={""};s.rewritten="/rewritten.txt?query";compare(s);
        }
        for(size_t root_length:{size_t(0),size_t(1),size_t(PATH_MAX-2),size_t(PATH_MAX-1),size_t(PATH_MAX)}) for(auto &url:std::vector<std::string>{"","x","xx","?query","/suffix"}) {
            PathScenario s;s.root=std::string(root_length,'r');s.url=url;compare(s);s.locations={"nonmatching"};compare(s);s.initial_last=true;compare(s);
        }
        for(auto &url:std::vector<std::string>{std::string("/file\0../suffix",15),"/UPPER?x","/x#before?after"}) {
            PathScenario s;s.url=url;s.locations={std::string("/file\0DIFFERENT",15),"/upper?x"};s.mime=false;compare(s);
        }
        for(bool last:{false,true}) {
            PathScenario config;config.root=std::string(PATH_MAX+1,'r');config.initial_last=last;
            candidate_path::active=&config;candidate_path::trace.clear();candidate_path::stat_calls=0;
            candidate_path::Server server(config);candidate_path::StaticHandler handler(&server,config);
            check(handler.try_serve()==last && handler.status_code==(last ? SW_HTTP_NOT_FOUND:SW_HTTP_OK) && handler.l_filename==12 && handler.dir_path=="old-directory" && candidate_path::stat_calls==0,"corrected oversized root policy");
            check(candidate_path::trace==std::vector<std::string>{"rewrite"},"oversized root avoids native filesystem");
            check(std::string(handler.filename)=="old-filename","oversized root leaves storage unchanged");
        }
        for(bool last:{false,true}) {
            PathScenario config;config.url="/"+std::string(100,'x')+"?query";config.initial_last=last;
            upstream_path::active=candidate_path::active=&config;upstream_path::stat_calls=candidate_path::stat_calls=0;
            upstream_path::trace.clear();candidate_path::trace.clear();upstream_path::trace.reserve(16);candidate_path::trace.reserve(16);
            upstream_path::Server sa(config);candidate_path::Server sb(config);
            upstream_path::StaticHandler a(&sa,config);candidate_path::StaticHandler b(&sb,config);
            failing_size=0; // Fail the next native allocation; libc++ rounds string capacity.
            bool failed_a=false,failed_b=false;
            fail_allocation=true;try { a.try_serve(); }catch(const std::bad_alloc &) { failed_a=true; }fail_allocation=false;
            fail_allocation=true;try { b.try_serve(); }catch(const std::bad_alloc &) { failed_b=true; }fail_allocation=false;
            check(failed_a && failed_b && a.l_filename==12 && b.l_filename==12 && a.dir_path.empty() && b.dir_path.empty() && a.last==b.last && a.status_code==b.status_code && std::memcmp(a.filename,b.filename,sizeof(a.filename))==0 && std::memcmp(&a.file_stat,&b.file_stat,sizeof(a.file_stat))==0 && upstream_path::trace==candidate_path::trace && upstream_path::stat_calls==0 && candidate_path::stat_calls==0,"native directory allocation-failure publication/timing differential");
        }
        size_t index_cases=0;
        for(auto &name:std::vector<std::string>{"","index.html","../other","under/child",std::string("a\0after",7),std::string(1000,'i')})
        for(mode_t mode:{S_IFREG,S_IFDIR,S_IFLNK}) for(bool stat_ok:{false,true}) {
            PathScenario config;config.modes={mode};config.stat_ok={stat_ok};
            upstream_path::active=candidate_path::active=&config;upstream_path::stat_calls=candidate_path::stat_calls=0;upstream_path::trace.clear();candidate_path::trace.clear();
            upstream_path::Server sa(config);candidate_path::Server sb(config);upstream_path::StaticHandler a(&sa,config);candidate_path::StaticHandler b(&sb,config);
            for(unsigned repeat=0;repeat<2;++repeat) {
                errno=EINTR;bool left=a.set_filename(name);int ea=errno;
                errno=EINTR;bool right=b.set_filename(name);int eb=errno;
                check(left==right && ea==eb && a.l_filename==b.l_filename && a.l_filename==12 && std::memcmp(a.filename,b.filename,sizeof(a.filename))==0 && std::memcmp(&a.file_stat,&b.file_stat,sizeof(a.file_stat))==0 && upstream_path::trace==candidate_path::trace,"index filename bytes/repeated-slash/IO differential");++index_cases;
            }
        }
        {
            PathScenario config;candidate_path::active=&config;candidate_path::stat_calls=0;candidate_path::trace.clear();
            candidate_path::Server server(config);candidate_path::StaticHandler handler(&server,config);
            char prior[PATH_MAX];std::memcpy(prior,handler.filename,sizeof(prior));
            check(!handler.set_filename(std::string(PATH_MAX,'i')) && candidate_path::stat_calls==0 && candidate_path::trace.empty() && std::memcmp(prior,handler.filename,sizeof(prior))==0 && handler.l_filename==12,"corrected index overflow avoids mutation/IO");
        }
        std::cout<<"{\"path_policy_cases\":"<<cases<<",\"index_path_cases\":"<<index_cases<<",\"corrected_index_cases\":1,\"corrected_root_cases\":2,\"native_allocation_failure_cases\":2,\"errors\":0}\n";
    }catch(const std::exception &error) { std::cerr<<error.what()<<'\n';return 1; }
}
