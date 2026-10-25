#include "settings_oracle.h"
thread_local Oracle*oracle;
int main(){try{size_t states=0,exits=0,returns_false=0,incomplete=0;
#ifdef SW_HAVE_COMPRESSION
 Input alias;alias.table["http_compression_level"]={1,false,0,"false",{}};alias.table["compression_level"]={1,true,200,"fallback",{}};
 auto first=upstream_settings::run(alias,SIZE_MAX);if(first.level!=0||std::find(first.trace.begin(),first.trace.end(),"lookup:compression_level")!=first.trace.end())throw std::runtime_error("native false-value alias witness");
 alias.table["http_compression_level"].kind=0;auto fallback=upstream_settings::run(alias,SIZE_MAX);if(fallback.level!=200)throw std::runtime_error("native null alias fallback witness");
 Input invalid;invalid.table["http_compression_types"]={3,true,0,"invalid",{}};invalid.table["compression_types"]={4,true,0,"fallback",{}};
 auto bad=upstream_settings::run(invalid,SIZE_MAX);if(!bad.returned_false||bad.completed||!bad.replaced||!bad.types.empty()||bad.websocket)throw std::runtime_error("native allocate-before-type-error witness");
#endif
 Input directory;directory.dir_ok=false;directory.table["upload_tmp_dir"]={3,true,0,"new",{}};
 auto stopped=upstream_settings::run(directory,SIZE_MAX);if(stopped.completed||stopped.upload!="old"||stopped.websocket!=17)throw std::runtime_error("native WebSocket-before-directory-error witness");
 std::vector<std::string>keys={"http_parse_cookie","http_parse_post","http_parse_files","http_compression","http_compression_level","compression_level","http_gzip_level","http_compression_min_length","compression_min_length","http_compression_types","compression_types","upload_tmp_dir"};
 std::vector<int64_t>levels={INT64_MIN,-1,0,1,255,256,INT64_MAX};
 for(unsigned mask=0;mask<4096;mask++)for(unsigned variation=0;variation<8;variation++){
  Input in;in.dir_ok=variation&1;in.hook=variation%4;
  for(unsigned k=0;k<keys.size();k++)if(mask&(1u<<k)){
   zval z;z.kind=(variation==0)?0:1;z.truth=(variation+k)%2;z.number=levels[(variation+k)%levels.size()];z.text=keys[k]+":"+std::to_string(variation);
   if(k==9||k==10){z.kind=variation%3==0?0:variation%3==1?3:4;z.array={{3,false,0,"text/plain",{}},{3,false,0,"",{}},{3,false,0,"application/json",{}}};}
   if(k==11&&variation==7)z.text="";
   in.table[keys[k]]=z;
  }
  auto a=upstream_settings::run(in,SIZE_MAX),b=candidate_settings::run(in,SIZE_MAX);
  if(!(a==b))throw std::runtime_error("settings mismatch mask="+std::to_string(mask)+" variation="+std::to_string(variation));states++;returns_false+=a.returned_false;incomplete+=!a.completed;
  if(mask%127==0&&variation%3==0)for(size_t fail=0;fail<a.trace.size();fail++){
   if(!(upstream_settings::run(in,fail)==candidate_settings::run(in,fail)))throw std::runtime_error("settings native effect exit mismatch");exits++;
  }
 }
 std::cout<<"{\"settings_states\":"<<states<<",\"native_effect_exits\":"<<exits<<",\"native_false_returns\":"<<returns_false<<",\"native_incomplete_returns\":"<<incomplete<<",\"errors\":0}\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
