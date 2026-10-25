/* C11 caller ABI; initialized foreign record, no actual printing/Coroutine. */
#include "swoole_rs_coroutine.h"
#include <assert.h>
#include <stddef.h>
#include <string.h>
struct record { uintptr_t prefix; swr_v1_coroutine_status status; uintptr_t tail; };
int main(void){
 void *owner=0;struct record object={11,{0,0},22};
 assert(swr_v1_coroutine_registry_insert(&owner,17,(uintptr_t)&object)==0);
 swr_v1_coroutine_registry_print_cursor cursor={0,0};
 swr_v1_coroutine_registry_print_action step=swr_v1_coroutine_registry_print_step(owner,&cursor,0,0);
 assert(step.action==1 && step.token==(uintptr_t)&object);
 step=swr_v1_coroutine_registry_print_step(owner,&cursor,&object,offsetof(struct record,status));
 assert(step.action==3 && step.cid==17 && strcmp(step.label,"[INIT]")==0);
 assert(swr_v1_coroutine_registry_print_step(owner,&cursor,0,SIZE_MAX).action==0);
 assert(object.prefix==11 && object.tail==22);
 swr_v1_coroutine_registry_drop(&owner);
 cursor.entry=0;cursor.phase=0;
 assert(swr_v1_coroutine_registry_print_step(0,&cursor,0,SIZE_MAX).action==0);
 return 0;
}
