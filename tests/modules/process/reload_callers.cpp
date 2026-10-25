// SPDX-License-Identifier: Apache-2.0
// Actual ProcessPool/ReloadTask bodies; deterministic native kill boundary only.
#include <sys/types.h>
#include <signal.h>
#include <cerrno>
extern "C" int swr_test_kill(pid_t,int);
#define kill swr_test_kill
#include SWRO_PROCESS_SOURCE
#undef kill
#include <cassert>
#include <vector>
#include <unordered_map>
#include <algorithm>
#include <cstdio>
static std::unordered_map<pid_t,int> errors;
static std::vector<pid_t> seen;
extern "C" int swr_test_kill(pid_t pid,int signo) {
    assert(signo==SIGTERM || signo==SIGKILL);
    assert(errors.count(pid));seen.push_back(pid);errno=errors.at(pid);return errno?-1:0;
}
int main(){
    swoole_init();
    swoole::Worker workers[3]{};
    for(int n=0;n<3;++n){workers[n].pid=1000000001+n;workers[n].id=n;}
    {
        swoole::ReloadTask task;task.add_workers(workers,3);task.remove(workers[0].pid);
        errors={{workers[1].pid,ESRCH},{workers[2].pid,0}};seen.clear();
        task.kill_one(SIGTERM);
        assert(seen==std::vector<pid_t>({workers[1].pid,workers[2].pid}));
        assert(task.count()==1 && task.exists(workers[2].pid) && task.kill_queue.empty());
    }
    {
        swoole::ReloadTask task;task.add_workers(workers,3);
        errors={{workers[0].pid,ECHILD},{workers[1].pid,EPERM},{workers[2].pid,0}};seen.clear();
        task.kill_one(SIGTERM);
        assert(seen==std::vector<pid_t>({workers[0].pid,workers[1].pid}));
        assert(task.count()==2 && task.exists(workers[1].pid) && task.kill_queue.size()==1);
        task.kill_one(SIGTERM);
        assert(seen.back()==workers[2].pid && task.count()==2 && task.kill_queue.empty());
    }
    {
        swoole::ReloadTask task;task.add_workers(workers,3);
        errors={{workers[0].pid,ESRCH},{workers[1].pid,EPERM},{workers[2].pid,0}};seen.clear();
        task.kill_all(SIGKILL);
        std::sort(seen.begin(),seen.end());
        assert(seen==std::vector<pid_t>({workers[0].pid,workers[1].pid,workers[2].pid}));
        assert(task.count()==3 && task.kill_queue.empty());
    }
    swoole_clean();
    puts("actual reload native queue/map:removed PID,ESRCH/ECHILD,EPERM,success,kill-all retention/order boundaries passed");
}
