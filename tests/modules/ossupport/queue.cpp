// SPDX-License-Identifier: Apache-2.0
// Opaque token FIFO, native serialization, quiescent fork and payload nonownership.
#include "swoole_rs_ossupport.h"
#include <cassert>
#include <queue>
#include <vector>
#include <thread>
#include <mutex>
#include <atomic>
#include <cstdint>
#include <limits>
#include <unistd.h>
#include <sys/wait.h>
#include <cstdio>
static uint64_t random_state=0x61b8a4c386f15392ULL;
static uintptr_t next_random(){random_state^=random_state<<13;random_state^=random_state>>7;random_state^=random_state<<17;return random_state;}
int main(){
    auto *queue=swr_v1_os_queue_create();assert(queue);
    assert(swr_v1_os_queue_count(queue)==0);
    assert(!swr_v1_os_queue_front(queue).present && !swr_v1_os_queue_pop(queue).present);
    std::queue<uintptr_t> control;
    size_t operations=0;
    for(size_t i=0;i<200000;++i){
        auto random=next_random();
        if(control.empty() || ((random&1) && control.size()<4096)){
            uintptr_t token=(i%7==0)?0:(i%11==0)?std::numeric_limits<uintptr_t>::max():random;
            assert(swr_v1_os_queue_push(queue,token));control.push(token);
        }else{
            auto item=swr_v1_os_queue_pop(queue);assert(item.present && item.token==control.front());control.pop();
        }
        assert(swr_v1_os_queue_count(queue)==control.size());auto front=swr_v1_os_queue_front(queue);
        assert(front.present==!control.empty());if(front.present)assert(front.token==control.front());++operations;
    }
    while(!control.empty()){auto item=swr_v1_os_queue_pop(queue);assert(item.present && item.token==control.front());control.pop();++operations;}
    assert(swr_v1_os_queue_push(queue,0));assert(swr_v1_os_queue_push(queue,std::numeric_limits<uintptr_t>::max()));
    pid_t child=fork();assert(child>=0);
    if(child==0){auto a=swr_v1_os_queue_pop(queue);auto b=swr_v1_os_queue_pop(queue);bool ok=a.present&&a.token==0&&b.present&&b.token==std::numeric_limits<uintptr_t>::max()&&!swr_v1_os_queue_pop(queue).present;swr_v1_os_queue_destroy(queue);_exit(ok?0:1);}
    int status;assert(waitpid(child,&status,0)==child && WIFEXITED(status)&&WEXITSTATUS(status)==0);
    assert(swr_v1_os_queue_count(queue)==2 && swr_v1_os_queue_pop(queue).present && swr_v1_os_queue_pop(queue).present);
    std::mutex lock;std::atomic<size_t> finished{0};std::vector<std::vector<uintptr_t>> seen(4);std::vector<std::thread> threads;
    for(size_t producer=0;producer<4;++producer)threads.emplace_back([&,producer](){for(size_t n=0;n<4096;++n){std::lock_guard<std::mutex> guard(lock);assert(swr_v1_os_queue_push(queue,1+producer*4096+n));}++finished;});
    for(size_t consumer=0;consumer<3;++consumer)threads.emplace_back([&](){while(true){std::lock_guard<std::mutex> guard(lock);auto item=swr_v1_os_queue_pop(queue);if(item.present){assert(item.token>=1 && item.token<=4*4096);auto token=item.token-1;seen[token/4096].push_back(token%4096);}else if(finished==4)break;}});
    for(auto &thread:threads)thread.join();
    for(auto &sequence:seen){assert(sequence.size()==4096);for(size_t n=0;n<sequence.size();++n)assert(sequence[n]==n);}
    swr_v1_os_queue_destroy(queue);
    struct Payload { int *count; ~Payload(){++*count;} };
    int destroyed=0;auto *payload=new Payload{&destroyed};queue=swr_v1_os_queue_create();assert(queue);
    assert(swr_v1_os_queue_push(queue,reinterpret_cast<uintptr_t>(payload)));swr_v1_os_queue_destroy(queue);assert(destroyed==0);delete payload;assert(destroyed==1);
    swr_v1_os_queue_destroy(nullptr);
    printf("%zu FIFO model operations,16384 native-serialized concurrent tokens,quiescent fork and payload nonownership passed\n",operations);
}
