#include "emission_oracle.h"
thread_local Oracle*oracle;
int main(){
 size_t states=0,faults=0,false_returns=0,partial_failures=0;unsigned errors=0;
 auto check=[&](unsigned bits,size_t length,bool null,bool ending,unsigned failed,unsigned hook,size_t fault){
  auto a=upstream_emission::run(bits,length,null,ending,failed,hook,fault);
  auto b=candidate_emission::run(bits,length,null,ending,failed,hook,fault);
  ++states;if(fault!=SIZE_MAX)++faults;if(a.returned==0)++false_returns;
  if(a.returned==0&&a.trace.end()!=std::find_if(a.trace.begin(),a.trace.end(),[](const std::string&s){return s.find("send:")==0;}))++partial_failures;
  if(!(a==b)){
   if(errors++<5){std::cerr<<"mismatch bits="<<bits<<" length="<<length<<" null="<<null<<" end="<<ending<<" sendfail="<<failed<<" hook="<<hook<<" fault="<<fault<<"\n";size_t n=std::max(a.trace.size(),b.trace.size());for(size_t i=0;i<n;i++){auto x=i<a.trace.size()?a.trace[i]:"(missing)",y=i<b.trace.size()?b.trace[i]:"(missing)";if(x!=y)std::cerr<<i<<" native="<<x.substr(0,100)<<" candidate="<<y.substr(0,100)<<"\n";}}
  }
  return a;
 };
 for(unsigned bits=0;bits<8192;bits++)for(size_t length:{size_t(0),size_t(1),size_t(17)})for(unsigned failed=0;failed<4;failed++)for(bool ending:{false,true})check(bits,length,false,ending,failed,0,SIZE_MAX);
 for(unsigned bits=0;bits<512;bits++)for(size_t length:{size_t(16383),size_t(16384),size_t(16385),size_t(32768)})for(unsigned failed=0;failed<4;failed++)check(bits,length,false,true,failed,0,SIZE_MAX);
 for(unsigned bits=0;bits<512;bits++)for(unsigned hook=1;hook<=4;hook++)for(bool ending:{false,true})check(bits,17,false,ending,0,hook,SIZE_MAX);
 for(unsigned bits=0;bits<256;bits++){
  check(bits,0,true,true,0,0,SIZE_MAX);
  for(bool ending:{false,true}){auto r=check(bits,17,false,ending,0,0,SIZE_MAX);for(size_t f=0;f<r.trace.size();f++)check(bits,17,false,ending,0,0,f);}
 }
 for(unsigned bits=0;bits<256;bits++)for(unsigned failed=0;failed<4;failed++)check(bits|8192,0,false,true,failed,0,SIZE_MAX);
 // Independent native witnesses: header publication precedes empty warning;
 // failed split body marks end before close, failed split header only resets header.
 auto empty=upstream_emission::run(16,0,false,false,0,0,SIZE_MAX);
 if(empty.returned!=0||!(empty.flags&2)||empty.trace.empty()||empty.trace.back().find("warning:")!=0)++errors;
 auto headerfail=upstream_emission::run(16,16385,false,true,1,0,SIZE_MAX);
 auto bodyfail=upstream_emission::run(16,16385,false,true,2,0,SIZE_MAX);
 if(headerfail.returned!=0||(headerfail.flags&2)||(headerfail.flags&256))++errors;
 if(bodyfail.returned!=0||!(bodyfail.flags&256)||bodyfail.trace.back()!="close:ended")++errors;
 auto trailerfail=upstream_emission::run(4|8|16,0,false,true,2,0,SIZE_MAX);
 if(trailerfail.returned!=1||!(trailerfail.flags&256)||trailerfail.flags&(4|8))++errors;
 std::cout<<"{\"emission_states\":"<<states<<",\"native_effect_exits\":"<<faults<<",\"native_false_returns\":"<<false_returns<<",\"failed_send_prefixes\":"<<partial_failures<<",\"errors\":"<<errors<<"}\n";
 return errors?1:0;
}
