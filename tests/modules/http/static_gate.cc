#include "static_oracle.h"
#include <iostream>
static_assert(sizeof(swr_v1_http_static_body_state)==2*sizeof(size_t)+2*sizeof(uint32_t), "static body layout");
static_assert(offsetof(swr_v1_http_static_body_state, phase)==2*sizeof(size_t), "static body phase offset");
static_assert(sizeof(swr_v1_http_static_selection)==3*sizeof(uint32_t), "static selection layout");
void check(bool ok,const char *message) { if(!ok) throw std::runtime_error(message); }
int main(int argc, char **argv) {
    const bool positive_only = argc == 2 && std::string(argv[1]) == "--positive-only";
    try {
        // Initialize the native exception runtime before comparing errno: its
        // first lazy unwind lookup may change errno independently of either path.
        if (!positive_only) {
            try { throw std::runtime_error("initialize native unwinder"); } catch(const std::runtime_error &) {}
        }
        size_t cases=0;
        auto compare=[&](const StaticScenario &scenario,bool head,bool keep_alive,bool modified_header) {
            upstream_static::Server a;candidate_static::Server b;a.scenario=b.scenario=scenario;
            upstream_static::Socket sa{&a.trace};candidate_static::Socket sb{&b.trace};
            upstream_static::Connection ca{73,&sa};candidate_static::Connection cb{73,&sb};
            upstream_static::Buffer ba;candidate_static::Buffer bb;
            upstream_static::http_server::Request ra{};candidate_static::http_server::Request rb{};
            ra.buffer_=&ba;rb.buffer_=&bb;ra.keep_alive=rb.keep_alive=keep_alive;ra.method=rb.method=head ? SW_HTTP_HEAD:SW_HTTP_GET;
            ra.modified_header=rb.modified_header=modified_header ? "if modified" : "";
            a.mutable_request=&ra;b.mutable_request=&rb;
            bool left=false,right=false,throw_a=false,throw_b=false;
            errno=EINTR;try { left=a.select_static_handler(&ra,&ca); } catch(const std::runtime_error &) { throw_a=true; } int ea=errno;
            errno=EINTR;try { right=b.select_static_handler(&rb,&cb); } catch(const std::runtime_error &) { throw_b=true; } int eb=errno;
            if(!(left==right && throw_a==throw_b && a.trace==b.trace && a.events==b.events && ra.trace==rb.trace && ra.keep_alive==rb.keep_alive && ra.method==rb.method && ea==eb)) {
                std::cerr<<"case "<<cases<<" status "<<scenario.status<<" head "<<head<<" autoindex "<<scenario.autoindex<<'\n';
                std::cerr<<"returns "<<left<<":"<<right<<" throws "<<throw_a<<":"<<throw_b<<" errno "<<ea<<":"<<eb<<'\n';
                for(auto &entry:a.trace)std::cerr<<"A "<<entry<<'\n';for(auto &entry:b.trace)std::cerr<<"B "<<entry<<'\n';
                for(auto &entry:ra.trace)std::cerr<<"RA "<<entry<<'\n';for(auto &entry:rb.trace)std::cerr<<"RB "<<entry<<'\n';
                if(a.events!=b.events && !a.events.empty() && !b.events.empty()) std::cerr<<std::get<2>(a.events[0])<<"\n---\n"<<std::get<2>(b.events[0])<<'\n';
                throw std::runtime_error("static response bytes/events/native order differential");
            }
            ++cases;
        };
        for(int status:{SW_HTTP_OK,SW_HTTP_NOT_FOUND,SW_HTTP_PARTIAL_CONTENT,SW_HTTP_RANGE_NOT_SATISFIABLE})
        for(unsigned mode=0;mode<8;++mode) for(bool head:{false,true}) for(bool keep:{false,true}) for(bool modified:{false,true}) {
            if (positive_only && mode == 6) continue;
            StaticScenario s;s.status=status;s.serve=mode!=1;s.modified=mode==2;s.index_ok=mode!=3;s.autoindex=mode==4;s.directory=mode==4;s.index=mode==5;s.throw_on_send=mode==6;
            if(mode==7) s.tasks.clear();compare(s,head,keep,modified);
            if(!s.throw_on_send) {
                s.tasks={{0,0,{}},{2,17,{}}};std::strcpy(s.tasks[0].part_header,"--boundary\r\nfirst\r\n\r\n");std::strcpy(s.tasks[1].part_header,"--boundary\r\nsecond\r\n\r\n");s.content_type="multipart/byteranges; boundary=boundary";compare(s,head,keep,modified);
                s.date=std::string(1500,'d');s.last_modified=std::string("date\0ignored",12);s.mime=std::string(300,'m');compare(s,head,keep,modified);
            }
        }
        if (!positive_only) for(size_t length:{size_t(0),size_t(1),std::numeric_limits<size_t>::max()})
        for(off_t offset:{off_t(0),off_t(17),std::numeric_limits<off_t>::max()}) {
            StaticScenario s;s.status=SW_HTTP_PARTIAL_CONTENT;s.tasks={{offset,length,{}}};s.content_length=0;s.filesize=std::numeric_limits<size_t>::max();
            compare(s,false,true,false);compare(s,true,false,false);
        }
        // Native sends may report errors or change subsequent native metadata.
        // Preserve the original late keep-alive check and single post-header HEAD
        // snapshot; no Rust borrow remains live across any of these callbacks.
        if (!positive_only) for(unsigned keep_change=0;keep_change<7;++keep_change)
        for(unsigned method_change=0;method_change<4;++method_change)
        for(int result:{0,-1}) for(bool head:{false,true}) for(bool keep:{false,true}) {
            StaticScenario s;s.toggle_keep_on_send=keep_change;s.toggle_method_on_send=method_change;s.send_result=result;
            compare(s,head,keep,false);
            s.tasks={{0,0,{}},{2,17,{}}};std::strcpy(s.tasks[0].part_header,"first");std::strcpy(s.tasks[1].part_header,"second");
            compare(s,head,keep,false);
            s.tasks={{0,0,{}}};compare(s,head,keep,false);
            s.tasks.clear();compare(s,head,keep,false);
        }
        std::cout<<"{\"static_response_cases\":"<<cases<<",\"errors\":0,\"positive_only\":"<<(positive_only ? "true" : "false")<<"}\n";
    } catch(const std::exception &e) { std::cerr<<e.what()<<'\n';return 1; }
}
