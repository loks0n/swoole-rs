// Included only by explicitly prepared optimized model binaries. --check-workloads
// does not read a clock; measurement commands require the coordinator's real lease.
#include <chrono>
#include "swoole_rs.h"
struct RewriteWorkload {
    Rules rules;
    std::string url="/file/item";
    bool configure=false;
};
static RewriteWorkload rewrite_workload(const std::string &name) {
    RewriteWorkload w;
    if(name=="literal-hit")w.rules={{"/file","/assets"}};
    else if(name=="literal-miss")w.rules={{"/different","/assets"}};
    else if(name=="regex-hit")w.rules={{"~^/file/(.*)$~","/assets/$1"}};
    else if(name=="regex-miss")w.rules={{"~^/different/(.*)$~","/assets/$1"}};
    else if(name=="ordered-16"||name=="configure-16") {
        for(unsigned i=0;i<15;++i)w.rules.emplace_back("/different/"+std::to_string(i),"/unused");
        w.rules.emplace_back("/file","/assets");
        w.configure=name=="configure-16";
    } else throw std::runtime_error("unknown prepared rewrite workload");
    return w;
}
template<class Server>static void configure_rewrite_work(Server &server,const RewriteWorkload &w) {
    for(const auto &rule:w.rules)server.add_rewrite_rule(rule.first,rule.second);
}
template<class Handler>static size_t rewrite_signature(const Handler &handler,bool changed) {
    size_t signature=changed;
    signature=signature*131+handler.publications;
    for(unsigned char byte:handler.url)signature=signature*131+byte;
    return signature;
}
template<class Server,class Handler>static size_t rewrite_work_step(Server &server,const RewriteWorkload &w) {
    Handler handler(w.url);
    const bool changed=server.apply_rewrite_rules(&handler);
    return rewrite_signature(handler,changed);
}
static size_t check_rewrite_work(const RewriteWorkload &w) {
    reference::Server a;selected::Server b;
    configure_rewrite_work(a,w);configure_rewrite_work(b,w);
    reference::http_server::StaticHandler x(w.url);selected::http_server::StaticHandler y(w.url);
    const bool old=a.apply_rewrite_rules(&x),candidate=b.apply_rewrite_rules(&y);
    if(old!=candidate||x.url!=y.url||x.original!=y.original||x.publications!=y.publications)
        throw std::runtime_error("prepared rewrite bytes/publication mismatch");
    return rewrite_signature(x,old);
}
template<class Server,class Handler>static int measure_rewrite_work(const std::string &engine,const std::string &name,size_t iterations) {
    const auto w=rewrite_workload(name);
    const size_t expected=check_rewrite_work(w);
    Server reused;
    if(!w.configure)configure_rewrite_work(reused,w);
    auto step=[&]() {
        if(w.configure) {
            Server scoped;configure_rewrite_work(scoped,w);
            return rewrite_work_step<Server,Handler>(scoped,w);
        }
        return rewrite_work_step<Server,Handler>(reused,w);
    };
    for(unsigned i=0;i<32;++i)if(step()!=expected)throw std::runtime_error("prepared warmup checksum");
    size_t signature=0;
    const auto begin=std::chrono::steady_clock::now();
    for(size_t i=0;i<iterations;++i)signature+=step();
    const auto end=std::chrono::steady_clock::now();
    if(signature!=expected*iterations||check_rewrite_work(w)!=expected)throw std::runtime_error("measured checksum mismatch");
    std::cout<<"{\"engine\":\""<<engine<<"\",\"workload\":\""<<name<<"\",\"operations\":"<<iterations
             <<",\"ns\":"<<std::chrono::duration_cast<std::chrono::nanoseconds>(end-begin).count()
             <<",\"signature\":"<<signature<<",\"timed\":true}\n";
    return 0;
}
static int rewrite_workload_command(int argc,char **argv) {
    if(argc==2&&std::string(argv[1])=="--check-workloads") {
        const auto abi=swr_v1_abi_version();const auto features=swr_v1_feature_bits();
        if(abi!=1||(features&(uint64_t(1)<<8))==0)throw std::runtime_error("prepared actual FFI HTTP ABI missing");
        size_t signature=0;
        for(const char *name:{"literal-hit","literal-miss","regex-hit","regex-miss","ordered-16","configure-16"})signature+=check_rewrite_work(rewrite_workload(name));
        std::cout<<"{\"workloads\":6,\"signature\":"<<signature<<",\"abi\":"<<abi<<",\"feature_bits\":"<<features<<",\"verified\":true,\"timed\":false}\n";
        return 0;
    }
    if(argc!=4)throw std::runtime_error("engine workload iterations required; measurement needs an actual exclusive lease");
    const std::string engine=argv[1],name=argv[2];
    const size_t iterations=std::stoull(argv[3]);
    if(!iterations)throw std::runtime_error("positive iterations required");
    if(engine=="native")return measure_rewrite_work<reference::Server,reference::http_server::StaticHandler>(engine,name,iterations);
    if(engine=="rust")return measure_rewrite_work<selected::Server,selected::http_server::StaticHandler>(engine,name,iterations);
    throw std::runtime_error("unknown engine");
}
