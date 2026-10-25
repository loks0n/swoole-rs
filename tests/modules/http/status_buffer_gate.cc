// Exact existing ordinary status/errno/TLS assertions from dispatch_gate.cc;
// unrelated route/index/proxy/fault profiles are not executed here.
#include "headers_oracle.h"
#include <atomic>
#include <climits>
#include <iostream>
#include <thread>
namespace upstream_headers { const char *get_status_message(int);
#ifdef SWR_HTTP_STATUS_CODES
extern int list_of_status_code[128];
#endif
}
namespace candidate_headers { const char *get_status_message(int); }
void check(bool value,const char *message){if(!value)throw std::logic_error(message);}
int main(){try{
    unsigned statuses=0,code_slots=0;
#ifdef SWR_HTTP_STATUS_CODES
    static_assert(sizeof(::swoole::http_server::list_of_status_code)==128*sizeof(int32_t),"Original array width");
    static_assert(alignof(int)==alignof(int32_t),"Original int alignment");
    for(unsigned i=0;i<128;++i){check(upstream_headers::list_of_status_code[i]==::swoole::http_server::list_of_status_code[i],"All original public array slots");++code_slots;}
    int *binding=::swoole::http_server::list_of_status_code;
    const int old_first=upstream_headers::list_of_status_code[0],selected_first=binding[0];
    upstream_headers::list_of_status_code[0]=777;binding[0]=777;
    check(::swoole::http_server::list_of_status_code==binding && binding[0]==upstream_headers::list_of_status_code[0],"Mutable direct public array binding");
    check(std::strcmp(upstream_headers::get_status_message(100),candidate_headers::get_status_message(100))==0,"Status lookup independent of public array mutations");
    upstream_headers::list_of_status_code[0]=old_first;binding[0]=selected_first;
#endif
        auto status=[&](int code){errno=EINTR;const char *a=upstream_headers::get_status_message(code);int before=errno;errno=EINTR;const char *b=candidate_headers::get_status_message(code);int after=errno;check(before==after&&std::strcmp(a,b)==0,"unknown/known status text/errno");++statuses;};
        for(int code=-512;code<=1024;++code)status(code);status(INT_MIN);status(INT_MAX);
        auto *old_tls=upstream_headers::get_status_message(-999);auto *new_tls=candidate_headers::get_status_message(-999);
        check(old_tls==upstream_headers::get_status_message(-1000)&&new_tls==candidate_headers::get_status_message(-1000),"TLS fallback reference");
        std::atomic<unsigned> ready{0};std::exception_ptr errors[2];uintptr_t old_ptr[2]={},new_ptr[2]={};
        auto thread=[&](unsigned id){try{old_ptr[id]=reinterpret_cast<uintptr_t>(upstream_headers::get_status_message(-12345));new_ptr[id]=reinterpret_cast<uintptr_t>(candidate_headers::get_status_message(-12345));++ready;while(ready.load()!=2)std::this_thread::yield();for(unsigned n=0;n<1024;++n){int code=-int(2000+id*1024+n);check(std::strcmp(upstream_headers::get_status_message(code),candidate_headers::get_status_message(code))==0,"thread status isolation");}}catch(...){errors[id]=std::current_exception();}};
        std::thread t1(thread,0),t2(thread,1);t1.join();t2.join();for(auto &e:errors)if(e)std::rethrow_exception(e);
        check(old_ptr[0]!=old_ptr[1]&&new_ptr[0]!=new_ptr[1],"distinct TLS fallback storage");
    std::cout<<"{\"public_code_slots\":"<<code_slots<<",\"status_cases\":"<<statuses<<",\"thread_status_cases\":2048,\"full_gate_passed\":false}"<<std::endl;
}catch(const std::exception &error){std::cerr<<error.what()<<std::endl;return 1;}}
