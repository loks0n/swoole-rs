#include "payload_oracle.h"
thread_local Oracle *oracle;
int main(){try{
 const char*locale=getenv("HTTPBINDINGS_LOCALE");if(locale&&!setlocale(LC_ALL,locale)){std::cerr<<"Unsupported locale "<<locale<<'\n';return 77;}
 // Independent pinned-native witnesses: these deliberately retain quirks.
 std::string advertised="br;q=0,gzip,deflate,zstd";
 auto preference=upstream_payload::compression(advertised,advertised.size(),77);
 int expected=(PAYLOAD_CAPABILITIES&2)?3:(PAYLOAD_CAPABILITIES&1)?1:(PAYLOAD_CAPABILITIES&4)?4:77;
 if(preference.method!=expected)throw std::runtime_error("native substring/preference witness");
 auto unchanged=upstream_payload::compression("GZIP",4,77);
 if(unchanged.method!=77||unchanged.accepted)throw std::runtime_error("native no-match method-retention witness");
 auto prefix=upstream_payload::body(Input{32,"\r\nx","",0,true},SIZE_MAX);
 if(std::find(prefix.trace.begin(),prefix.trace.end(),"multipart:x")==prefix.trace.end())throw std::runtime_error("native first multipart EOL witness");
 size_t body=0,complete=0,options=0,compression=0,faults=0;
 std::vector<std::string>values={"","a","\r","\n","\r\n\r\nx","\n\r",std::string("\r\n\0binary",9),std::string(8192,'x')};
 for(uint32_t flags=0;flags<128;flags++)for(const auto&bytes:values)for(size_t previous:{size_t(0),size_t(3)})for(bool parsed:{false,true}){
  Input in{flags,bytes,flags&8?"previous":"",previous,parsed};
  auto a=upstream_payload::body(in,SIZE_MAX),b=candidate_payload::body(in,SIZE_MAX);if(!(a==b))throw std::runtime_error("body mismatch "+std::to_string(flags));body++;
  if(previous==0&&bytes.size()<10)for(size_t f=0;f<a.trace.size();f++){if(!(upstream_payload::body(in,f)==candidate_payload::body(in,f)))throw std::runtime_error("body native fault mismatch");faults++;}
  a=upstream_payload::complete(in,SIZE_MAX);b=candidate_payload::complete(in,SIZE_MAX);if(!(a==b))throw std::runtime_error("completion mismatch "+std::to_string(flags));complete++;
  if(previous==0&&bytes.size()<10)for(size_t f=0;f<a.trace.size();f++){if(!(upstream_payload::complete(in,f)==candidate_payload::complete(in,f)))throw std::runtime_error("completion native fault mismatch");faults++;}
 }
 for(const std::string&name:{"parse_cookie","parse_body","parse_files","enable_compression","compression_level","websocket_compression","upload_tmp_dir","unknown"})for(unsigned byte=0;byte<256;byte++)for(unsigned position=0;position<3;position++){
  std::string key=name;if(position==0)key[0]=char(byte);else if(position==1)key+=char(byte);else for(char&c:key)if(c>='a'&&c<='z')c-=32;
  zval value{std::string("v\0x",3),bool(byte%2),long(byte)-127};
  for(bool reentry:{false,true}){
   auto a=upstream_payload::option(key,value,SIZE_MAX,reentry),b=candidate_payload::option(key,value,SIZE_MAX,reentry);if(!(a==b))throw std::runtime_error("option mismatch");options++;
   if(byte%31==0)for(size_t f=0;f<a.trace.size();f++){if(!(upstream_payload::option(key,value,f,reentry)==candidate_payload::option(key,value,f,reentry)))throw std::runtime_error("option native fault mismatch");faults++;}
  }
 }
 std::vector<std::string>encodings={"","gzip","GZIP","deflate","br","zstd","gzip, br","br;q=0,deflate","zstd,gzip","brrrr",std::string("x\0br",4)};
 for(unsigned byte=0;byte<256;byte++)for(const auto&encoding:encodings)for(int method:{-1,0,1,2,3,4,5,77}){
  std::string modified=char(byte)+encoding+char(byte);
  for(size_t n:{modified.size(),size_t(modified.size()+(UINT64_C(1)<<32))}){
   auto a=upstream_payload::compression(modified,n,method),b=candidate_payload::compression(modified,n,method);if(!(a==b))throw std::runtime_error("compression mismatch");compression++;
  }
 }
 std::cout<<"{\"body_callbacks\":"<<body<<",\"completion_callbacks\":"<<complete<<",\"option_states\":"<<options<<",\"compression_states\":"<<compression<<",\"native_fault_exits\":"<<faults<<",\"capabilities\":"<<PAYLOAD_CAPABILITIES<<",\"errors\":0}\n";
 return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
