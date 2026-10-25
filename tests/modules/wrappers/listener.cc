// Exact listen address prefix; mock native server records effects without IO.
#include "swoole_rs_wrappers.h"
#include <cassert>
#include <cerrno>
#include <cstdlib>
#include <functional>
#include <iostream>
#include <memory>
#include <sstream>
#include <string>
#include <vector>
#include "numbers.inc"
static std::ostringstream trace;
constexpr int SW_SOCK_TCP=1;
struct Context {};
struct Port {};
struct Server {
    enum class Mode { BASE=1,PROCESS=2 };
    std::string host;int port=0;Port endpoint;
    explicit Server(Mode mode) { trace<<"new:"<<int(mode)<<';'; }
    ~Server() { trace<<"drop;"; }
    Port *add_port(int type,const char *address,int number) {
        host=address;port=number;trace<<"add:"<<type<<':'<<host.size()<<':'<<host<<':'<<port<<';';return &endpoint;
    }
};
static void swoole_warning(const char *message) { trace<<"warn:"<<message<<';'; }
namespace original {
#include "original.inc"
}
namespace selected {
#include "selected.inc"
}
template<class F>static std::string run(F function,const std::string &address,int mode) {
    trace.str("");trace.clear();errno=0;
    auto server=function(address,[](Context &){},mode);
    int error=errno;trace<<"result:"<<bool(server)<<':'<<error<<';';server.reset();return trace.str();
}
int main() {
    static_assert(sizeof(SwrWrapperListenerPlan)==16&&offsetof(SwrWrapperListenerPlan,valid)==8,"listener ABI");
    uint64_t cases=0,seed=0x61646472657373;
    auto next=[&](){seed^=seed<<13;seed^=seed>>7;seed^=seed<<17;return seed;};
    std::vector<std::string> inputs={"",":0","127.0.0.1:9501","localhost","host:","::1:9501",":-1",":9999999999999999999999999999",std::string("\0:42",4),std::string("name\0:5",7)};
    for(unsigned i=0;i<4096;i++) {
        std::string input(next()%128,'x');for(char &c:input)c=char(next());inputs.push_back(input);
    }
    for(const auto &input:inputs) {
        auto plan=swr_v1_wrappers_listener_plan(reinterpret_cast<const uint8_t *>(input.data()),input.size());
        auto separator=input.find(':');bool valid=separator!=input.npos;
        assert(plan.separator==(valid?separator:input.size()));assert(plan.valid==valid);assert(plan.default_host==(valid&&separator==0));
        for(int mode:{1,2}) { assert(run(original::listen,input,mode)==run(selected::listen,input,mode));++cases; }
    }
    auto empty=swr_v1_wrappers_listener_plan(nullptr,0);assert(!empty.separator&&!empty.valid&&!empty.default_host);++cases;
    std::cout<<"listener-prefix "<<cases<<" exact-prefix/direct-ABI cases PASS\n";
}
