// SPDX-License-Identifier: Apache-2.0
#include "swoole_rs_ossupport.h"
#include <cassert>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <limits>
#include <sys/stat.h>
#include <vector>
int main() {
    size_t checks = 0;
    const size_t values[] = {0,1,2,8,64,128,1024,std::numeric_limits<size_t>::max()};
    const double times[] = {-1.,-0.,0.0005,0.5,1.,100.,std::numeric_limits<double>::infinity()};
    for(auto cpu:values) for(auto core:values) for(auto workers:values) for(auto wait:times) for(auto idle:times) {
        auto p=swr_v1_os_pool_config(cpu,core,workers,wait,idle);
        auto expected_core=core==0?cpu:std::max(size_t(1),core);
        auto expected_workers=workers==0?cpu*size_t(8):std::max(expected_core,workers);
        assert(p.core==expected_core && p.workers==expected_workers);
        assert(p.wait==(wait==0?0.001:wait) && p.idle==(idle==0?1.:idle));++checks;
    }
    for(auto waiting:values) for(auto threads:values) for(auto workers:values) for(auto threshold:times) for(auto age:times) {
        const size_t expected=waiting==0&&threads<workers&&threshold>0&&age>threshold?1:0;
        assert(swr_v1_os_pool_expand(waiting,threads,workers,threshold,age)==expected);++checks;
    }
    for(int perms=-1024;perms<2048;++perms){assert(swr_v1_os_permissions(perms)==((perms<=0||perms>=01000)?0666:perms));++checks;}
    for(int flags=-128;flags<128;++flags) for(int nowait: {1,8,2048}) for(bool block:{false,true}) {
        assert(swr_v1_os_queue_flags(flags,block,nowait)==(block?flags&~nowait:flags|nowait));++checks;
    }
    for(int result=-2;result<3;++result)for(bool a:{false,true})for(bool b:{false,true}){
        assert(swr_v1_os_fs_error(result,a)==(result==0?0:a?1:2));
        assert(swr_v1_os_random_error(result,a,b)==(result==-1&&(a||b)));
        assert(swr_v1_os_sendfile_action(result,a)==(result==-1?(a?1:2):result==0?0:3));checks+=3;
    }
    for(size_t n=0;n<1024;++n){std::vector<unsigned char> data(n, 'x');
        for(size_t term=0;term<=n;++term){
            if(term<n)data[term]=(term%2==0)?0:'\n';
            size_t expected=0;for(size_t i=0;i<n;++i)if(data[i]==0||data[i]=='\n'){expected=i+1;break;}
            assert(swr_v1_os_line_end(data.data(),data.size())==expected);++checks;
            if(term<n)data[term]='x';
        }
    }
    for(auto length:values)for(auto maximum:values){assert(swr_v1_os_content(length,maximum)==(length==0?1:length>maximum?2:0));++checks;}
    for(bool succeeded:{false,true})for(mode_t mode:{mode_t(0),mode_t(S_IFREG),mode_t(S_IFREG|0644),mode_t(S_IFDIR|0755),mode_t(S_IFIFO|0600),mode_t(S_IFCHR|0600),mode_t(S_IFLNK|0777)}) {
        const int32_t expected=!succeeded?1:S_ISREG(mode)?0:2;
        assert(swr_v1_os_file_size_action(succeeded,mode,S_IFMT,S_IFREG)==expected);++checks;
    }
    for(bool handler:{false,true})for(bool canceled:{false,true}){assert(swr_v1_os_event_action(handler,canceled)==(!handler?1:canceled?2:0));++checks;}
    for(bool interrupted:{false,true})for(bool again:{false,true}){assert(swr_v1_os_queue_error(interrupted,again)==(interrupted?1:again?2:3));++checks;}
    for(bool event:{false,true})for(bool handler:{false,true})for(bool canceled:{false,true})for(bool timeout:{false,true})for(size_t closing:{size_t(0),size_t(1),size_t(128)}) {
        int expected=event?(!handler?2:canceled?3:1):(timeout&&closing==0?4:0);
        assert(swr_v1_os_worker_action(event,handler,canceled,timeout,closing)==expected);++checks;
    }
    printf("%zu independent native expression/byte comparisons passed\n",checks);
}
