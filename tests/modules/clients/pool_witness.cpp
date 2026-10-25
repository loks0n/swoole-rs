#include <algorithm>
#include <array>
#include <cstdint>
#include <deque>
#include <iostream>
#include <map>
#include <string>
#include <vector>
#include <sys/wait.h>
#include <unistd.h>
#include "swoole_rs_clients_pool.h"
#ifdef SWR_CLIENTS_POOL_TEST_ALLOCATION
extern "C" void swr_test_clients_pool_allocation_budget(intptr_t);
#endif
struct NativeToken {static unsigned destroyed;unsigned id=0;~NativeToken(){++destroyed;}};
unsigned NativeToken::destroyed=0;
static int faults(NativeToken *tokens){
#ifdef SWR_CLIENTS_POOL_TEST_ALLOCATION
    for(int budget=0;budget<4;++budget){
        SwooleRustClientPool pool;swr_test_clients_pool_allocation_budget(budget);bool caught=false;
        try{pool.push("fault",tokens);}catch(const std::bad_alloc&){caught=true;}
        swr_test_clients_pool_allocation_budget(-1);
        if(!caught||pool.state("fault").kind!=unsigned(budget==3?1:0)||pool.state("fault").length!=0)return 20+budget;
        pool.push("fault",tokens);if(pool.take("fault")!=tokens)return 24;pool.remove_empty("fault");
    }
    SwooleRustClientPool pool;pool.push("growth",tokens);size_t count=1;bool caught=false;
    swr_test_clients_pool_allocation_budget(0);
    for(size_t i=0;i<65536;++i){try{pool.push("growth",tokens);++count;}catch(const std::bad_alloc&){caught=true;break;}}
    swr_test_clients_pool_allocation_budget(-1);
    if(!caught||pool.state("growth").length!=count)return 25;
    while(count--)if(pool.take("growth")!=tokens)return 26;
    if(pool.state("growth").kind!=1)return 27;pool.remove_empty("growth");
#endif
    return 0;
}
int main(){
    std::array<NativeToken,32> tokens;for(unsigned i=0;i<tokens.size();++i)tokens[i].id=i;
    int fault_result=faults(tokens.data());if(fault_result)return fault_result;
    std::vector<std::string> keys={"","x",std::string("x\0y",3),std::string("\0",1),"other",std::string(4096,'z')};
    std::string bytes;for(unsigned i=0;i<256;++i)bytes.push_back(char(i));keys.push_back(bytes);
    {
        SwooleRustClientPool pool;std::map<std::string,std::deque<void*>> expected;
        if(pool.state("absent").kind||pool.take("absent"))return 1;
        uint64_t random=0x91cd81a63ULL;
        for(size_t operation=0;operation<100000;++operation){
            random=random*6364136223846793005ULL+1442695040888963407ULL;
            const auto&key=keys[(random>>8)%keys.size()];unsigned choice=(random>>32)%4;
            auto found=expected.find(key);
            if(choice<2){void *token=&tokens[(random>>48)%tokens.size()];pool.push(key,token);expected[key].push_back(token);}
            else if(choice==2){void *token=nullptr;if(found!=expected.end()&&!found->second.empty()){token=found->second.front();found->second.pop_front();}if(pool.take(key)!=token)return 2;}
            else{pool.remove_empty(key);if(found!=expected.end()&&found->second.empty())expected.erase(found);}
            for(const auto&probe:keys){auto item=expected.find(probe);auto state=pool.state(probe);unsigned kind=item==expected.end()?0:(item->second.empty()?1:2);size_t length=item==expected.end()?0:item->second.size();if(state.kind!=kind||state.length!=length)return 3;}
        }
    }
    // Rust teardown reclaims its containers, never native tokens. This differs
    // from the original raw-queue leak and is not an allocation-parity claim.
    if(NativeToken::destroyed!=0)return 4;
    {
        SwooleRustClientPool pool;const std::string key("fork\0fifo",9);
        pool.push(key,&tokens[0]);pool.push(key,&tokens[1]);
        pid_t child=fork();if(child<0)return 5;
        if(child==0){int code=0;
            if(pool.take(key)!=&tokens[0])code=6;
            pool.push(key,&tokens[2]);if(pool.take(key)!=&tokens[1]||pool.take(key)!=&tokens[2])code=7;
            pool.remove_empty(key);if(pool.state(key).kind)code=8;
            pool.~SwooleRustClientPool();if(NativeToken::destroyed)code=9;
            _exit(code);
        }
        int status=0;if(waitpid(child,&status,0)!=child||!WIFEXITED(status)||WEXITSTATUS(status)!=0)return 10;
        if(pool.state(key).length!=2||pool.take(key)!=&tokens[0]||pool.take(key)!=&tokens[1])return 11;
        pool.remove_empty(key);
    }
    if(NativeToken::destroyed!=0)return 12;
    std::cout<<"{\"operations\":100000,\"state_checks\":700000,\"fork_cases\":1,\"nonempty_teardown_cases\":1,\"native_tokens_destroyed_by_pool\":0"
#ifdef SWR_CLIENTS_POOL_TEST_ALLOCATION
        <<",\"injected_failure_prefix_cases\":5"
#endif
        <<"}\n";
}
