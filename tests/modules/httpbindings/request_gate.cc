#include "request_oracle.h"
#include <iostream>
thread_local Oracle *oracle;
thread_local Scratch scratch;
struct Result {
    int code=0;bool exited=false;std::vector<std::string>trace;std::string state,temporary;
    std::map<std::string,std::vector<std::string>> headers,server;
    bool operator==(const Result&r)const{return code==r.code&&exited==r.exited&&trace==r.trace&&state==r.state&&temporary==r.temporary&&headers==r.headers&&server==r.server;}
};
using Callback=int(*)(llhttp_t*,const char*,size_t);
Result invoke(Callback callback,std::string name,const std::string &value,unsigned method,unsigned flags,size_t fail=SIZE_MAX,bool mutate=false){
 Oracle local;oracle=&local;local.fail=fail;std::fill(std::begin(scratch.str),std::end(scratch.str),'Z');HttpContext ctx;
 ctx.current_header_name=name.data();ctx.current_header_name_len=name.size();ctx.parse_cookie=flags&1;ctx.enable_compression=flags&2;ctx.co=flags&4;ctx.server.found=flags&8;ctx.server.port.open_websocket_protocol=flags&16;ctx.boundary=flags&32;
 llhttp_t parser{&ctx,method};Result r;
 if(mutate)local.observe=[&](const std::string&s){if(s.find("zval:")==0)for(char&c:name)c='x';};
 try{r.code=callback(&parser,value.data(),value.size());}catch(const Exit&){r.exited=true;}
 r.trace=local.trace;r.headers=ctx.request.header.hash;r.server=ctx.request.server.hash;
 r.state=std::to_string(ctx.websocket)+":"+std::to_string(ctx.recv_chunked)+":"+std::to_string(ctx.request.post_form_urlencoded)+":"+std::to_string(ctx.server.conn.websocket_status)+":"+std::to_string(ctx.compression)+":"+std::to_string(ctx.initializations)+":"+ctx.request.cookie.text+":"+std::to_string(ctx.request.path_len)+":"+(ctx.request.path?std::string(ctx.request.path,ctx.request.path_len):"")+":"+ctx.request.get.text;
 r.temporary.assign(scratch.str,sizeof(scratch.str));return r;
}
static size_t headers=0,faults=0,urls=0,tokens=0,trims=0,keys=0;
void header_case(const std::string&name,const std::string&value,unsigned method,unsigned flags,bool fault=false,bool mutate=false){
 auto a=invoke(upstream_request::call_header,name,value,method,flags,SIZE_MAX,mutate);auto b=invoke(candidate_request::call_header,name,value,method,flags,SIZE_MAX,mutate);
 if(!(a==b))throw std::runtime_error("header callback mismatch case"+std::to_string(headers)+" name="+name+" value="+value+" method="+std::to_string(method)+" flags="+std::to_string(flags));headers++;
 if(fault)for(size_t f=0;f<a.trace.size();f++){if(!(invoke(upstream_request::call_header,name,value,method,flags,f)==invoke(candidate_request::call_header,name,value,method,flags,f)))throw std::runtime_error("header effect exit mismatch");faults++;}
}
void token_case(const std::string &input,const std::string&value){
 Oracle local;oracle=&local;std::fill(std::begin(scratch.str),std::end(scratch.str),'Z');bool a=upstream_request::swoole_http_token_list_contains_value(input.data(),input.size(),value.c_str());std::string before(scratch.str,sizeof(scratch.str));std::fill(std::begin(scratch.str),std::end(scratch.str),'Z');bool b=candidate_request::swoole_http_token_list_contains_value(input.data(),input.size(),value.c_str());
 if(a!=b||before!=std::string(scratch.str,sizeof(scratch.str)))throw std::runtime_error("token result/scratch mismatch case"+std::to_string(tokens));tokens++;
}
void token_alias_case(const std::string &input,size_t offset,bool scratch_alias){
 auto run=[&](bool candidate){
  std::string source=input;std::fill(std::begin(scratch.str),std::end(scratch.str),'Z');scratch.str[sizeof(scratch.str)-1]=0;memcpy(scratch.str,"websocket,\0",11);
  const char*value=scratch_alias?scratch.str+offset:source.c_str()+offset;
  bool result=candidate?candidate_request::swoole_http_token_list_contains_value(source.data(),source.size(),value):upstream_request::swoole_http_token_list_contains_value(source.data(),source.size(),value);
  return std::make_pair(result,std::string(scratch.str,sizeof(scratch.str)));
 };
 if(run(false)!=run(true))throw std::runtime_error("token aliased value/scratch mismatch");tokens++;
}
int main(){try{
 Oracle pin;oracle=&pin;
 std::string prefix=std::string("websocket").substr(0,sizeof(const char*)-1);
 if(!upstream_request::swoole_http_token_list_contains_value(prefix.data(),prefix.size(),"websocket"))throw std::runtime_error("pinned pointer-size token witness changed");
 std::string quoted="\"\"\"a";size_t quoted_len=quoted.size();char*quoted_out=upstream_request::call_trim(&quoted[0],&quoted_len);
 if(quoted_out-&quoted[0]!=2||quoted_len!=2||std::string(quoted_out,quoted_len)!="\"a")throw std::runtime_error("pinned shrinking quote witness changed");
 std::string hyphen="-Foo";upstream_request::call_key(&hyphen[0],hyphen.size());if(hyphen!="-foo")throw std::runtime_error("pinned header-key witness changed");
 std::vector<std::string>names={"cookie","COOKIE","upgrade","Upgrade","content-type","CONTENT-TYPE","accept-encoding","transfer-encoding","host","user-agent","accept","content-length","authorization","connection","x-custom",std::string("host\0xyz",8)};
 std::vector<std::string>values={"","websocket","websock","WebSocket, other","other,\t websocket \r\n, tail","application/x-www-form-urlencoded; charset=x","multipart/form-data; boundary=abc","gzip, deflate","chunked; extension",std::string("websocket\0other",15)};
 for(auto&name:names)for(auto&value:values)for(unsigned method:{0u,1u,3u,4u,5u,28u,29u,255u})for(unsigned flags:{0u,1u,2u,3u,7u,8u,15u,16u,31u,32u,63u})header_case(name,value,method,flags,method==3&&flags==63);
 for(auto&name:names)header_case(name,"v",3,63,false,true);
 for(auto&name:names)for(unsigned byte=0;byte<256;byte++){
  auto altered=name;if(!altered.empty())altered[byte%altered.size()]=char(byte);header_case(altered,"multipart/form-data; boundary=b",3,63);
 }
 for(unsigned byte=0;byte<256;byte++)for(auto &value:values){token_case(std::string("other,")+char(byte)+value+char(byte)+",tail", "websocket");token_case(value,std::string("x")+char(byte));}
 for(auto &value:values)for(auto &target:values)token_case(value,target);
 for(auto &value:values){for(size_t offset=0;offset<=value.size();offset++)token_alias_case(value,offset,false);for(size_t offset:{0u,1u,3u,7u,9u})token_alias_case(value,offset,true);}
 for(unsigned length=0;length<24;length++)for(unsigned mask=0;mask<256;mask++){
  std::string input(length,'"');for(size_t i=0;i<input.size();i++)if(mask&(1u<<(i%8)))input[i]=char((mask+i)%256);
  auto a=input,b=input;size_t al=a.size(),bl=b.size();char*ap=upstream_request::call_trim(&a[0],&al);char*bp=candidate_request::call_trim(&b[0],&bl);if(al!=bl||ap-&a[0]!=bp-&b[0]||a!=b)throw std::runtime_error("quote trim mismatch");trims++;
  for(int sign:{-1,0,1}){a=input;b=input;upstream_request::call_key(&a[0],sign*int(length));candidate_request::call_key(&b[0],sign*int(length));if(a!=b)throw std::runtime_error("response key mismatch");keys++;}
 }
 for(unsigned length=0;length<128;length++)for(unsigned pos=0;pos<=length;pos++){
  std::string input(length,'x');if(pos<length)input[pos]='?';if(length>3)input[1]=0;
  auto a=invoke(upstream_request::call_url,"",input,0,0),b=invoke(candidate_request::call_url,"",input,0,0);if(!(a==b))throw std::runtime_error("URL callback mismatch");urls++;
 }
 std::cout<<"{\"header_callbacks\":"<<headers<<",\"native_effect_faults\":"<<faults<<",\"token_cases\":"<<tokens<<",\"quote_trims\":"<<trims<<",\"response_keys\":"<<keys<<",\"url_callbacks\":"<<urls<<",\"errors\":0}\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
