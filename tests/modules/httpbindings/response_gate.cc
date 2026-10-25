#include "response_oracle.h"
thread_local Oracle *oracle;
int main(){try{
 const char*locale=getenv("HTTPBINDINGS_LOCALE");if(locale&&!setlocale(LC_ALL,locale)){std::cerr<<"Unsupported locale "<<locale<<'\n';return 77;}
 size_t tails=0,headers=0,faults=0,assertions=0;
 for(uint32_t mask=0;mask<512;mask++)for(uint32_t facts=0;facts<64;facts++)for(size_t length:{size_t(0),size_t(1),size_t(4096)})for(unsigned hook=0;hook<4;hook++){
  auto a=upstream_response::tail(mask,facts,length,hook,SIZE_MAX),b=candidate_response::tail(mask,facts,length,hook,SIZE_MAX);
  if(!(a==b))throw std::runtime_error("response tail mismatch mask="+std::to_string(mask)+" facts="+std::to_string(facts)+" len="+std::to_string(length)+" hook="+std::to_string(hook));tails++;
  assertions+=std::find(a.trace.begin(),a.trace.end(),"assert:0")!=a.trace.end();
  if(mask%127==0&&facts%11==0&&hook==0)for(size_t fail=0;fail<a.trace.size();fail++){
   if(!(upstream_response::tail(mask,facts,length,hook,fail)==candidate_response::tail(mask,facts,length,hook,fail)))throw std::runtime_error("response native effect exit mismatch");faults++;
  }
 }
 // Retain native long conversion without exercising its LONG_MIN overflow.
 for(size_t length:{size_t(LONG_MAX),SIZE_MAX}){
  auto a=upstream_response::tail(0,0,length,0,SIZE_MAX),b=candidate_response::tail(0,0,length,0,SIZE_MAX);if(!(a==b))throw std::runtime_error("native integer conversion mismatch");tails++;
 }
 for(const std::string&name:{"Server","Connection","Date","Content-Length","Content-Type","Transfer-Encoding","Content-Encoding","custom"})for(unsigned byte=0;byte<256;byte++)for(unsigned position=0;position<3;position++){
  std::string key=name;if(position==0)key[0]=char(byte);else if(position==1)key+=char(byte);else for(char&c:key)if(c>='A'&&c<='Z')c+=32;
  if(upstream_response::header(key)!=candidate_response::header(key))throw std::runtime_error("response known header mismatch");headers++;
 }
 auto native=upstream_response::tail(2|16,1,0,0,SIZE_MAX);
 if(native.output!="\r\n"||native.published!=1)throw std::runtime_error("native upgrade early-finalization witness");
 std::cout<<"{\"tail_scenarios\":"<<tails<<",\"header_names\":"<<headers<<",\"native_effect_exits\":"<<faults<<",\"preserved_assertion_failures\":"<<assertions<<",\"errors\":0}\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
