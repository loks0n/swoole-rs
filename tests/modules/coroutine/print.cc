// Complete print body on initialized foreign metadata; mocked output only.
#include "swoole_rs_coroutine_registry.h"
#include <cassert>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <string>
#include <unordered_map>
#include <vector>
namespace swoole {
class Coroutine {
 public:
 enum {STATE_INIT=0,STATE_WAITING=1,STATE_RUNNING=2,STATE_END=3};
 uintptr_t prefix=99;
 int state=0;
 swr_v1_coroutine_status status_={0,0};
 uintptr_t tail=101;
#ifdef SELECTED
 static RustCoroutineRegistry<Coroutine> coroutines;
#else
 static std::unordered_map<long,Coroutine*> coroutines;
#endif
 static void print_list();
};
#ifdef SELECTED
RustCoroutineRegistry<Coroutine> Coroutine::coroutines;
#else
std::unordered_map<long,Coroutine*> Coroutine::coroutines;
#endif
}
static std::string output;
static std::vector<swoole::Coroutine> records;
static void sw_printf(const char *format,long cid,const char *state){
 assert(std::strcmp(format,"Coroutine\t%ld\t%s\n")==0);
 char buffer[128];int n=std::snprintf(buffer,sizeof(buffer),format,cid,state);assert(n>0 && static_cast<size_t>(n)<sizeof(buffer));output.append(buffer,n);
 // Metadata-only output barrier: every later record must read its fresh state.
 for(auto &record:records){record.state=2;record.status_.state=2;}
}
namespace swoole {
#include "print-body.inc"
}
int main(){
 for(int seed=0;seed<4;seed++)for(int count:{0,1,2,13,65,129}){
  swoole::Coroutine::coroutines.clear();records.clear();records.resize(count);output.clear();
  for(int n=0;n<count;n++){records[n].state=(n+seed)%4;records[n].status_.state=records[n].state;long cid=(n%3==0?-1L:1L)*(n*257+seed+1);swoole::Coroutine::coroutines[cid]=&records[n];}
  swoole::Coroutine::print_list();
  size_t lines=0;for(char c:output)if(c=='\n')lines++;assert(lines==static_cast<size_t>(count));
  for(auto &record:records)assert(record.prefix==99 && record.tail==101);
  std::cout<<seed<<':'<<count<<'\n'<<output;
 }
 swoole::Coroutine::coroutines.clear();
}
