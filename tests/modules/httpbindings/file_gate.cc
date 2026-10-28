#include "file_oracle.h"
thread_local Oracle*oracle;
int main(){
 size_t states=0,faults=0,false_returns=0,ranges=0,undefined_ranges=0;unsigned errors=0;
 auto check=[&](unsigned bits,size_t length,unsigned hook,size_t fault){auto a=upstream_file::run(bits,length,hook,fault),b=candidate_file::run(bits,length,hook,fault);++states;if(fault!=SIZE_MAX)++faults;if(!a.returned)++false_returns;if(!(a==b)&&errors++<5)std::cerr<<"file mismatch bits="<<bits<<" length="<<length<<" hook="<<hook<<" fault="<<fault<<"\n";return a;};
 for(unsigned bits=0;bits<512;bits++)for(size_t length:{size_t(0),size_t(1),size_t(16384),SIZE_MAX})for(unsigned hook=0;hook<5;hook++)check(bits,length,hook,SIZE_MAX);
 for(unsigned bits=0;bits<512;bits++){auto a=check(bits,17,0,SIZE_MAX);for(size_t f=0;f<a.trace.size();f++)check(bits,17,0,f);}
 auto range=[&](int64_t size,int64_t offset,int64_t length){
  // Subtraction outside int64 has no defined original C++ result. Do not execute
  // or count the undefined reference path as a passing parity case.
  if(size>=offset&&(__int128(size)-offset)>INT64_MAX){++undefined_ranges;return;}
  auto a=upstream_file::range(size,offset,length),b=candidate_file::range(size,offset,length);++ranges;if(!(a==b)&&errors++<5)std::cerr<<"range mismatch "<<size<<" "<<offset<<" "<<length<<"\n";
 };
 std::vector<int64_t>values={INT64_MIN,INT64_MIN+1,-65536,-1,0,1,17,65536,INT64_MAX-1,INT64_MAX};
 for(auto size:values)for(auto offset:values)for(auto length:values)range(size,offset,length);
 uint64_t random=0x783fad963cb421e5ULL;auto next=[&](){random^=random<<13;random^=random>>7;random^=random<<17;int64_t n;memcpy(&n,&random,sizeof n);return n;};
 for(unsigned i=0;i<131072;i++){auto size=next(),offset=next(),length=next();range(size,offset,(i&7)?length:0);}
 // Native header failure resets publication without marking end; IO failure
 // closes before marking end. Successful zero-length file marks before close.
 auto headerfail=upstream_file::run(8|32,1,0,SIZE_MAX),iofail=upstream_file::run(8|64,1,0,SIZE_MAX),empty=upstream_file::run(64,0,0,SIZE_MAX);
 if(headerfail.returned||headerfail.flags&1||headerfail.flags&2)++errors;
 if(iofail.returned||iofail.flags&2||iofail.trace.back()!="close:pending")++errors;
 if(!empty.returned||!(empty.flags&2)||empty.trace.back()!="close:ended")++errors;
 std::cout<<"{\"file_states\":"<<states<<",\"native_effect_exits\":"<<faults<<",\"native_false_returns\":"<<false_returns<<",\"defined_ranges\":"<<ranges<<",\"undefined_reference_ranges_excluded\":"<<undefined_ranges<<",\"errors\":"<<errors<<"}\n";
 return errors?1:0;
}
