#include <cassert>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <poll.h>
#ifdef __linux__
#include <sys/epoll.h>
#else
#include <sys/event.h>
#endif
#include "swoole_rs_reactor.h"
static_assert(sizeof(swr_v1_reactor_batch_cursor)==sizeof(size_t)*2,"batch cursor ABI");
static_assert(sizeof(swr_v1_reactor_batch_record)==sizeof(uintptr_t)+16,"batch record ABI");
static_assert(offsetof(swr_v1_reactor_batch_record,fd)==sizeof(uintptr_t),"fd ABI");
static_assert(offsetof(swr_v1_reactor_batch_record,mask)==sizeof(uintptr_t)+4,"mask ABI");
static_assert(offsetof(swr_v1_reactor_batch_record,filter)==sizeof(uintptr_t)+8,"filter ABI");
static_assert(offsetof(swr_v1_reactor_batch_record,kind)==sizeof(uintptr_t)+12,"kind ABI");
int main() {
    unsigned observations=0;
    pollfd polls[3]={{7,POLLIN,0},{8,POLLIN,POLLIN},{9,POLLOUT,POLLOUT}};
    swr_v1_reactor_batch_cursor cursor{};swr_v1_reactor_batch_record record{};
    for(size_t i=0;i<3;i++)if(polls[i].revents!=0) {
        assert(swr_v1_reactor_poll_record(polls,3,&cursor,1,&record)==1);
        assert(cursor.current==i && record.fd==polls[i].fd && record.kind==1);
        assert(record.mask==unsigned(polls[i].revents==POLLIN?1:2));++observations;
    }
    assert(swr_v1_reactor_poll_record(polls,3,&cursor,1,&record)==0);
    int tokens[3]={1,2,3};cursor={};
#ifdef __linux__
    epoll_event events[3]{};
    for(size_t i=0;i<3;i++) {events[i].data.ptr=&tokens[i];events[i].events=i==1?EPOLLOUT:EPOLLIN;}
    for(size_t i=0;i<3;i++) {
        assert(swr_v1_reactor_epoll_record(events,3,&cursor,1,&record)==1);
        assert(record.token==reinterpret_cast<uintptr_t>(events[i].data.ptr));
        assert(record.mask==unsigned(i==1?2:1) && record.kind==1 && record.fd==0 && record.filter==0);++observations;
    }
    assert(swr_v1_reactor_epoll_record(events,3,&cursor,1,&record)==0);
#else
    struct kevent events[3]{};
    EV_SET(&events[0],7,EVFILT_READ,0,0,0,nullptr);
    EV_SET(&events[1],8,EVFILT_READ,0,0,0,&tokens[1]);
    EV_SET(&events[2],9,EVFILT_WRITE,0,0,0,&tokens[2]);
    for(size_t i=0;i<3;i++)if(events[i].udata) {
        assert(swr_v1_reactor_kqueue_record(events,3,&cursor,1,&record)==1);
        assert(cursor.current==i && record.token==reinterpret_cast<uintptr_t>(events[i].udata));
        assert(record.filter==events[i].filter && record.mask==unsigned(i==1?1:2) && record.kind==1);++observations;
    }
    assert(swr_v1_reactor_kqueue_record(events,3,&cursor,1,&record)==0);
#endif
    std::cout<<"{\"genuine_array_records\":"<<observations<<",\"record_size\":"<<sizeof(record)<<",\"record_alignment\":"<<alignof(decltype(record))<<",\"positive_only\":true}\n";
}
