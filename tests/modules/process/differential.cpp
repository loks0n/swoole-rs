// SPDX-License-Identifier: Apache-2.0
// Independent pinned C++ decision expressions; callbacks/effects remain native.
#include "swoole_rs_process.h"
#include <cassert>
#include <climits>
#include <cstddef>
#include <cstdint>
#include <cstdio>
static_assert(sizeof(swr_v1_process_exit_observation)==8 && offsetof(swr_v1_process_exit_observation,callback_called)==4,"exit C ABI");
static_assert(sizeof(swr_v1_process_exit_budget_result)==8 && offsetof(swr_v1_process_exit_budget_result,timeout_msec)==4,"budget C ABI");
int main(){
 size_t checks=0;
 for(int bits=0;bits<32;++bits){bool a=bits&1,b=bits&2,c=bits&4,d=bits&8,e=bits&16;
  auto step=swr_v1_process_worker_exit(a,b,c);auto action=a?0:(b&&!c)?1:2;assert(step.action==action && step.callback_called==(c||(!a&&b&&!c)));++checks;
  bool discard;if(!a){discard=!(c&&!d);}else{discard=b;}assert(swr_v1_process_discard_data(a,b,c,d)==discard);++checks;
  assert(swr_v1_process_task_action(a,b,c)==(a?1:b?2:c?3:0));++checks;
  assert(swr_v1_process_finish_error(a,b)==(a?1:b?2:0));++checks;
  assert(swr_v1_process_reload_action(a,b)==(a?1:b?2:0));++checks;
  assert(swr_v1_process_reload_kill(a,b,c)==(!a?0:(b||c)?1:2));++checks;
  (void)e;
 }
 const int remaining[]={INT_MIN,-1,0,1,2,1000,INT_MAX/1000};
 const int timeout[]={INT_MIN,-1,0,1,999,1000,INT_MAX};
 for(int r:remaining)for(int t:timeout){bool timed_out=false,update=false;int expected=t;if(r<=0)timed_out=true;else{int limit=r*1000;if(t<0||t>limit){update=true;expected=limit;}}
  auto plan=swr_v1_process_exit_budget(r,t);assert(plan.timed_out==timed_out&&plan.update_timeout==update&&plan.timeout_msec==expected);++checks;
 }
 uint32_t random=0x518bc19u;
 for(int n=0;n<100000;++n){random^=random<<13;random^=random>>17;random^=random<<5;int32_t flags=static_cast<int32_t>(random);for(int bits=0;bits<4;++bits){bool cb=bits&1,co=bits&2;int expected=flags;if(cb)expected|=4;else if(co)expected|=8;assert(swr_v1_process_result_flags(flags,cb,co,4,8)==expected);++checks;}}
 std::printf("%zu independent worker/task/reload/budget decisions passed\n",checks);
}
