// Canonical public event wrapper calls against one optimized library per process.
#include "swoole_api.h"
#include "swoole_pipe.h"
#include <chrono>
#include <iostream>
#include <iomanip>
#include <dlfcn.h>
int main(int argc,char**argv){
    if(argc!=2)return 2;bool check=std::string(argv[1])=="check";auto loops=check?1:std::stoull(argv[1]);if(!loops||loops>10000000)return 3;
    Dl_info facade{},core{};
    if(!dladdr(reinterpret_cast<const void *>(&swoole_event_add_or_update),&facade)||!facade.dli_fname||
       !dladdr(reinterpret_cast<const void *>(&swoole_init),&core)||!core.dli_fname)return 8;
    swoole_init();swoole_set_log_level(SW_LOG_ERROR);if(swoole_event_init(SW_EVENTLOOP_WAIT_EXIT))return 4;
    int64_t ns=0;
    { swoole::UnixSocket p(true,SOCK_DGRAM);if(!p.ready())return 5;auto sock=p.get_socket(false);
    auto start=check?std::chrono::steady_clock::time_point{}:std::chrono::steady_clock::now();
    for(uint64_t i=0;i<loops;i++)if(swoole_event_add_or_update(sock,SW_EVENT_READ)||swoole_event_add_or_update(sock,SW_EVENT_WRITE))return 6;
    if(!check)ns=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-start).count();
    if(swoole_event_get_socket(sock->get_fd())!=sock||swoole_event_del(sock)||swoole_event_free())return 7;
    }
    swoole_clean();std::cout<<"{\"nanoseconds\":"<<ns<<",\"operations\":"<<loops*2<<",\"errors\":0,\"facade_library\":"<<std::quoted(facade.dli_fname)<<",\"core_library\":"<<std::quoted(core.dli_fname)<<"}"<<std::endl;
}
