#include "multipart_oracle.h"
struct Result {int returned,error;size_t buffer_length,offset,upload_size;unsigned flags;bool file,threw;std::vector<std::string> events;bool operator==(const Result &r)const{return returned==r.returned&&error==r.error&&buffer_length==r.buffer_length&&offset==r.offset&&upload_size==r.upload_size&&flags==r.flags&&file==r.file&&threw==r.threw&&events==r.events;}};
struct Scenario {size_t length=4,buffer_length=3,maximum=32,upload_size=0,upload_maximum=32,write_count=4;bool file=false,fail_append=false;unsigned flags=0;int io=0;};
// Each engine compiles in its own TU: SWR_ENGINE names it, SWR_ENGINE_BODIES its .inc.
#ifdef SWR_ENGINE
#define ENGINE_RUN(ns) \
Result data_##ns(const Scenario &s){ns::Buffer buffer;buffer.length=s.buffer_length;ns::multipart_parser parser;ns::FormData form{&buffer,s.upload_size,s.upload_maximum,&parser};ns::Request request;request.form_data_=&form;request.max_length_=s.maximum;request.excepted=s.flags&1;request.unavailable=(s.flags>>1)&1;request.too_large=(s.flags>>2)&1;parser.data=&request; \
 parser.fp=s.file?reinterpret_cast<FILE*>(uintptr_t(1)):nullptr;ns::real_stdio=s.io!=0;if(s.io==1)parser.fp=tmpfile();if(s.io==2)parser.fp=fopen("/dev/null","r");if(s.io&&!parser.fp)throw std::runtime_error("stdio setup");ns::observed=&request;ns::events.clear();ns::write_count=s.write_count;ns::throw_append=s.fail_append;char data[64]={};int returned=0;bool threw=false;errno=EINTR;try{returned=ns::multipart_on_data(&parser,data,s.length);}catch(const std::bad_alloc&){threw=true;} \
 Result result{returned,errno,buffer.length,buffer.offset,form.upload_filesize,request.excepted|(request.unavailable<<1)|(request.too_large<<2),parser.fp!=nullptr,threw,ns::events};if(s.io&&parser.fp)fclose(parser.fp);return result;} \
Result parse_##ns(ssize_t processed,size_t length,unsigned excepted){ns::Buffer buffer;buffer.length=length;ns::multipart_parser parser;ns::FormData form{&buffer,0,0,&parser};ns::Request request;request.form_data_=&form;request.excepted=1;ns::observed=&request;ns::events.clear();ns::parser_result=processed;ns::parser_excepted=excepted;int returned=request.parse_multipart_data(&buffer);return {returned,errno,buffer.length,buffer.offset,0,request.excepted,false,false,ns::events};}
// Bodies are compiled in this TU so their static callbacks remain callable.
#include SWR_ENGINE_BODIES
#undef fwrite
#undef fclose
#define EXPAND_RUN(ns) ENGINE_RUN(ns)
EXPAND_RUN(SWR_ENGINE)
#else
Result data_upstream_multipart(const Scenario &);Result data_candidate_multipart(const Scenario &);
Result parse_upstream_multipart(ssize_t,size_t,unsigned);Result parse_candidate_multipart(ssize_t,size_t,unsigned);
int main(){try{try{throw std::bad_alloc();}catch(const std::bad_alloc&){}size_t cases=0,failures=0;auto compare=[&](const Scenario &s){auto a=data_upstream_multipart(s),b=data_candidate_multipart(s);if(!(a==b)){std::cerr<<"data case "<<cases<<" mismatch\n";for(auto &e:a.events)std::cerr<<"old "<<e<<'\n';for(auto &e:b.events)std::cerr<<"new "<<e<<'\n';throw std::runtime_error("data mismatch");}++cases;failures+=a.threw;};
 for(size_t n:{0U,1U,4U,16U,64U})for(size_t limit:{0U,4U,16U,128U})for(bool file:{false,true})for(size_t written:{0U,1U,4U,64U})for(unsigned flags:{0U,1U,2U,4U,7U}){Scenario s;s.length=n;s.maximum=s.upload_maximum=limit;s.buffer_length=s.upload_size=4;s.file=file;s.write_count=written;s.flags=flags;compare(s);if(!file){s.fail_append=true;compare(s);}}
 std::mt19937 rng(71812);for(unsigned i=0;i<2048;++i){Scenario s;s.length=rng()%65;s.maximum=rng()%257;s.upload_maximum=rng()%257;s.buffer_length=rng()%129;s.upload_size=rng()%257;s.file=rng()%2;s.write_count=rng()%65;s.flags=rng()%8;compare(s);}
 size_t stdio=0;for(int io:{1,2})for(size_t n:{0U,1U,16U,64U}){Scenario s;s.file=true;s.io=io;s.length=n;s.maximum=s.upload_maximum=128;compare(s);++stdio;}
 size_t parses=0;for(ssize_t n:{ssize_t(-2),ssize_t(-1),ssize_t(0),ssize_t(1),ssize_t(16),ssize_t(128)})for(size_t length:{0U,1U,16U,128U})for(unsigned excepted:{0U,1U}){auto a=parse_upstream_multipart(n,length,excepted),b=parse_candidate_multipart(n,length,excepted);if(!(a==b))throw std::runtime_error("parser result mismatch");++parses;}
 std::cout<<"{\"data_cases\":"<<cases<<",\"native_append_failures\":"<<failures<<",\"actual_stdio_cases\":"<<stdio<<",\"parser_result_cases\":"<<parses<<",\"errors\":0}\n";return 0;}catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}}
#endif
