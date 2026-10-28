#include "server_oracle.h"
#include <iostream>
#include <climits>
thread_local Oracle*oracle;
struct Result{int status=0;bool exited=false;std::vector<std::string>trace;bool operator==(const Result&r)const{return status==r.status&&exited==r.exited&&trace==r.trace;}};
Result accept_run(void(*call)(AcceptSocket*,AcceptServer*),bool connection,long cid,int error,size_t fail=SIZE_MAX){
 Oracle local;oracle=&local;local.accept_connection=connection;local.cid=cid;local.accept_error=error;local.fail=fail;AcceptSocket socket;AcceptServer server;local.accept_server=&server;Result result;
 try{call(&socket,&server);}catch(const Exit&){result.exited=true;}
 result.trace=local.trace;result.status=server.running;return result;
}
int main(){try{size_t routes=0,accepts=0;
 zend::Callable callbacks[4]={{0},{1},{2},{3}};
 std::vector<std::string>patterns={"/","/a","/A","/a/b",std::string("/a\0q",4),""};
 for(unsigned mask=0;mask<64;mask++)for(unsigned def=0;def<5;def++)for(auto&path:patterns)for(unsigned byte=0;byte<256;byte+=7){
  upstream_server::HandlerServer old;candidate_server::HandlerServer now;old.default_handler=now.default_handler=def<4?&callbacks[def]:nullptr;
  for(unsigned i=0;i<6;i++)if(mask&(1u<<i)){old.handlers[patterns[i]]=&callbacks[i%4];now.handlers[patterns[i]]=&callbacks[i%4];}
  std::string modified=path+char(byte);RouteContext ctx{{modified.data(),modified.size()}};
  if(old.get_handler(&ctx)!=now.get_handler(&ctx))throw std::runtime_error("handler iteration/identity mismatch");routes++;
 }
 for(unsigned connection=0;connection<2;connection++)for(long cid:{LONG_MIN,long(-1),long(0),long(1),LONG_MAX})for(int error=-1;error<=4100;error++){
  auto a=accept_run(upstream_server::call_accept,connection,cid,error),b=accept_run(candidate_server::call_accept,connection,cid,error);
  if(!(a==b))throw std::runtime_error("accept native loop/effect mismatch");accepts++;
  if(error%109==0)for(size_t f=0;f<a.trace.size();f++)if(!(accept_run(upstream_server::call_accept,connection,cid,error,f)==accept_run(candidate_server::call_accept,connection,cid,error,f)))throw std::runtime_error("accept native effect exit mismatch");
 }
 std::cout<<"{\"handler_routes\":"<<routes<<",\"accept_outcomes\":"<<accepts<<",\"errors\":0}\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
