#include "codec_oracle.h"
thread_local Oracle *oracle;
int main(){try{size_t states=0,exits=0,false_returns=0,warnings=0,partial_failures=0;
 if(!CODEC_CAPABILITIES){std::cout<<"{\"codec_states\":0,\"compression_compiled\":false,\"coverage_status\":\"unsupported\"}\n";return 77;}
 if(CODEC_CAPABILITIES&1){auto z=upstream_codec::run(0,1,1,SIZE_MAX);if(z.level!=1||!z.success||!z.compressed)throw std::runtime_error("native zlib zero-level witness");}
 if(CODEC_CAPABILITIES&2){auto b=upstream_codec::run(127,3,1,SIZE_MAX);if(b.level!=11||!b.success)throw std::runtime_error("native Brotli published-clamp witness");}
 if(CODEC_CAPABILITIES&4){auto z=upstream_codec::run(-10,4,65,SIZE_MAX);if(z.level!=97||!z.success||std::find(z.trace.begin(),z.trace.end(),"zstd:-5:256:288")==z.trace.end())throw std::runtime_error("native Zstd captured-local/reentry witness");}
 for(int level=-128;level<128;level++)for(int method:{-1,0,1,2,3,4,5,127})for(unsigned config=0;config<128;config++){
  auto a=upstream_codec::run(level,method,config,SIZE_MAX),b=candidate_codec::run(level,method,config,SIZE_MAX);
  if(!(a==b))throw std::runtime_error("codec mismatch level="+std::to_string(level)+" method="+std::to_string(method)+" config="+std::to_string(config));states++;
  false_returns+=!a.success;
  warnings+=std::any_of(a.trace.begin(),a.trace.end(),[](const std::string&s){return s.find("warning:")==0;});
  partial_failures+=!a.success&&!a.buffer.empty()&&a.buffer[0]==0xa5;
  if((level==-128||level==-1||level==0||level==1||level==9||level==10||level==11||level==127)&&(config==1||config==9||config==17||config==33||config==65||config==73||config==81||config==97))for(size_t fail=0;fail<a.trace.size();fail++){
   if(!(upstream_codec::run(level,method,config,fail)==candidate_codec::run(level,method,config,fail)))throw std::runtime_error("codec native exit mismatch");exits++;
  }
 }
 std::cout<<"{\"codec_states\":"<<states<<",\"native_false_returns\":"<<false_returns<<",\"native_warning_states\":"<<warnings<<",\"native_failed_partial_writes\":"<<partial_failures<<",\"native_effect_exits\":"<<exits<<",\"capabilities\":"<<CODEC_CAPABILITIES<<",\"compression_compiled\":"<<(CODEC_CAPABILITIES?"true":"false")<<",\"errors\":0}\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
