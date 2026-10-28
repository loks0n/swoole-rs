#include "dispatch_oracle.h"
#include "allocation_oracle.h"
#include <iostream>
#include <climits>
#include <thread>
#include <atomic>
#include <cerrno>
void check(bool yes,const char *message){if(!yes)throw std::runtime_error(message);}
int main(){
    unsigned routes=0,proxies=0,proxy_faults=0,statuses=0;
    try {
        for(unsigned ws=0;ws<256;++ws)for(unsigned h2:{0u,1u,255u}) {
            upstream_dispatch::Connection a;candidate_dispatch::Connection b;a.websocket_status=b.websocket_status=ws;a.http2_stream=b.http2_stream=h2;
            upstream_dispatch::Socket sa{&a};candidate_dispatch::Socket sb{&b};upstream_dispatch::Protocol pa;candidate_dispatch::Protocol pb;
            upstream_dispatch::PacketLength la;candidate_dispatch::PacketLength lb;
            upstream_dispatch::RecvData da;candidate_dispatch::RecvData db;
            for(unsigned operation=0;operation<3;++operation){
                upstream_dispatch::reset();candidate_dispatch::reset();int old=0,current=0;
                if(operation==0){old=upstream_dispatch::get_package_length(&pa,&sa,&la);current=candidate_dispatch::get_package_length(&pb,&sb,&lb);}
                if(operation==1){old=upstream_dispatch::get_package_length_size(&sa);current=candidate_dispatch::get_package_length_size(&sb);}
                if(operation==2){old=upstream_dispatch::dispatch_frame(&pa,&sa,&da);current=candidate_dispatch::dispatch_frame(&pb,&sb,&db);}
                check(old==current&&la.seen==lb.seen&&upstream_dispatch::ws_calls==candidate_dispatch::ws_calls&&upstream_dispatch::h2_calls==candidate_dispatch::h2_calls&&upstream_dispatch::dispatch_calls==candidate_dispatch::dispatch_calls&&upstream_dispatch::error_calls==candidate_dispatch::error_calls,"transport result/call routing");
                if(candidate_dispatch::seen_proto)check(candidate_dispatch::seen_proto==&pb,"protocol pointer");
                if(candidate_dispatch::seen_socket)check(candidate_dispatch::seen_socket==&sb,"socket pointer");
                if(candidate_dispatch::seen_data)check(candidate_dispatch::seen_data==&db,"data pointer");++routes;
            }
        }
        const std::string long_name(200,'x');
        for(const std::string &host:{std::string(),std::string("host"),long_name})for(const std::string &user:{std::string(),std::string("u\0tail",6),long_name})for(const std::string &pwd:{std::string(),std::string("p\0tail",6),long_name}){
            size_t total=0;
            for(size_t nth=0;nth<=total;++nth){
                upstream_dispatch::HttpProxy::last_created=nullptr;candidate_dispatch::HttpProxy::last_created=nullptr;
                bool of=false,nf=false;size_t count=0,sizes[128]={};
                allocation::begin(nth);try{upstream_dispatch::HttpProxy::create(host,-123,user,pwd);}catch(const std::bad_alloc&){of=true;}allocation::end();count=allocation::count;check(count<=128,"proxy trace overflow");std::copy(allocation::sizes,allocation::sizes+count,sizes);
                allocation::begin(nth);try{candidate_dispatch::HttpProxy::create(host,-123,user,pwd);}catch(const std::bad_alloc&){nf=true;}allocation::end();
                auto *a=upstream_dispatch::HttpProxy::last_created;auto *b=candidate_dispatch::HttpProxy::last_created;
                check(of==nf&&count==allocation::count&&std::equal(sizes,sizes+count,allocation::sizes)&&bool(a)==bool(b),"proxy init fault sequence");
                if(a&&b)check(a->host==b->host&&a->port==b->port&&a->username==b->username&&a->password==b->password,"proxy partial fields");
                // The pinned raw-pointer creator leaks this unpublished object on
                // assignment failure. Inspect then explicitly dispose test facades;
                // production cleanup is not claimed fixed by the decision port.
                delete a;delete b;
                if(!nth){total=count;++proxies;}else++proxy_faults;
            }
        }
        auto status=[&](int code){errno=EINTR;const char *a=upstream_dispatch::get_status_message(code);int before=errno;errno=EINTR;const char *b=candidate_dispatch::get_status_message(code);int after=errno;check(before==after&&std::strcmp(a,b)==0,"unknown/known status text/errno");++statuses;};
        for(int code=-512;code<=1024;++code)status(code);status(INT_MIN);status(INT_MAX);
        auto *old_tls=upstream_dispatch::get_status_message(-999);auto *new_tls=candidate_dispatch::get_status_message(-999);
        check(old_tls==upstream_dispatch::get_status_message(-1000)&&new_tls==candidate_dispatch::get_status_message(-1000),"TLS fallback reference");
        std::atomic<unsigned> ready{0};std::exception_ptr errors[2];uintptr_t old_ptr[2]={},new_ptr[2]={};
        auto thread=[&](unsigned id){try{old_ptr[id]=reinterpret_cast<uintptr_t>(upstream_dispatch::get_status_message(-12345));new_ptr[id]=reinterpret_cast<uintptr_t>(candidate_dispatch::get_status_message(-12345));++ready;while(ready.load()!=2)std::this_thread::yield();for(unsigned n=0;n<1024;++n){int code=-int(2000+id*1024+n);check(std::strcmp(upstream_dispatch::get_status_message(code),candidate_dispatch::get_status_message(code))==0,"thread status isolation");}}catch(...){errors[id]=std::current_exception();}};
        std::thread t1(thread,0),t2(thread,1);t1.join();t2.join();for(auto &e:errors)if(e)std::rethrow_exception(e);
        check(old_ptr[0]!=old_ptr[1]&&new_ptr[0]!=new_ptr[1],"distinct TLS fallback storage");
        std::cout<<"{\"route_cases\":"<<routes<<",\"proxy_cases\":"<<proxies<<",\"proxy_allocation_faults\":"<<proxy_faults<<",\"status_cases\":"<<statuses<<",\"thread_status_cases\":2048,\"errors\":0}\n";
    }catch(const std::exception &e){allocation::end();std::cerr<<e.what()<<'\n';return 1;}
}
