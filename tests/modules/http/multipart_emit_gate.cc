#include "multipart_headers_oracle.h"
#include <cstdarg>
#include <limits>
struct Result {std::string buffer,alternate;unsigned header,tried;size_t content,header_length;uintptr_t fp;bool form_changed,data_changed,threw;int error;std::vector<std::string>events;};
// Each engine compiles in its own TU: SWR_ENGINE names it, SWR_ENGINE_BODIES its .inc.
#ifdef SWR_ENGINE
#define EMIT_FIXTURE(ns) namespace ns { \
Request *observed=nullptr;multipart_parser *parser=nullptr;std::vector<std::string> events;int append_attempt=0,fail_append=-1,file_failure=0; \
inline unsigned mode=0;inline FormData *alternate_form=nullptr;inline Request *alternate_request=nullptr; \
std::string snapshot(){return std::to_string(observed->multipart_header_parsed)+","+std::to_string(observed->tried_to_dispatch)+","+std::to_string(observed->content_length_)+","+std::to_string(reinterpret_cast<uintptr_t>(parser->fp))+","+std::to_string(errno);} \
void mutate(){if(mode==1){observed->multipart_header_parsed^=1;observed->tried_to_dispatch^=1;if(append_attempt==1)parser->fp=reinterpret_cast<FILE*>(uintptr_t(3));}if(mode==2){observed->header_length_=999;}if(mode==3&&append_attempt==1)observed->form_data_=alternate_form;if(mode==4&&append_attempt==1)parser->data=alternate_request;} \
int emit_fflush(FILE *fp){events.push_back("flush:"+std::to_string(reinterpret_cast<uintptr_t>(fp))+":"+snapshot());if(mode==1)parser->fp=reinterpret_cast<FILE*>(uintptr_t(5));errno=EIO;return -1;} \
int emit_fclose(FILE *fp){events.push_back("close:"+std::to_string(reinterpret_cast<uintptr_t>(fp))+":"+snapshot());errno=ENOSPC;return -1;} \
void emit_trace(const char *format,...){char text[2048];va_list args;va_start(args,format);vsnprintf(text,sizeof(text),format,args);va_end(args);events.push_back("trace:"+std::string(text)+":"+snapshot());} }
EMIT_FIXTURE(SWR_ENGINE)
#undef EMIT_FIXTURE
#undef swoole_trace
#define swoole_trace emit_trace
#define fflush emit_fflush
#define fclose emit_fclose
#include SWR_ENGINE_BODIES
#undef fflush
#undef fclose
#define RUN(ns) Result run_##ns(unsigned kind,bool file,unsigned flags,const std::string &boundary,const std::string &filename,int fail,unsigned mode,size_t header_length){ \
ns::events.clear();ns::append_attempt=0;ns::fail_append=fail;ns::mode=mode;ns::append_hook=ns::mutate; \
ns::Buffer buffer,other;buffer.bytes="initial";buffer.length=buffer.bytes.size();buffer.str=buffer.bytes.data();other.bytes="alternate";other.length=other.bytes.size();other.str=other.bytes.data(); \
ns::String temporary;memcpy(temporary.str,filename.data(),filename.size());temporary.str[filename.size()]=0; \
ns::FormData form{&buffer,"Content-Type",12,&temporary,"unused-template",1234},alt{&other,"Other",5,&temporary,"alternate-template",5678}; \
ns::Request request{&form,0},alt_request{&alt,0};request.header_length_=header_length;request.content_length_=123;request.multipart_header_parsed=flags&1;request.tried_to_dispatch=(flags>>1)&1; \
ns::multipart_parser parser{&request,file?reinterpret_cast<FILE*>(uintptr_t(1)):nullptr,boundary.data(),boundary.size()};ns::observed=&request;ns::parser=&parser;ns::alternate_form=&alt;ns::alternate_request=&alt_request; \
errno=EINTR;bool threw=false;try{int result=0;switch(kind){case 0:result=ns::multipart_on_header_complete(&parser);break;case 1:result=ns::multipart_on_data_end(&parser);break;case 2:result=ns::multipart_on_part_begin(&parser);break;case 3:result=ns::multipart_on_body_end(&parser);break;}if(result)throw std::runtime_error("callback result");}catch(const std::bad_alloc&){threw=true;} \
ns::append_hook=nullptr;return{buffer.bytes,other.bytes,request.multipart_header_parsed,request.tried_to_dispatch,request.content_length_,request.header_length_,reinterpret_cast<uintptr_t>(parser.fp),request.form_data_==&alt,parser.data==&alt_request,threw,errno,ns::events}; }
#define EXPAND_RUN(ns) RUN(ns)
EXPAND_RUN(SWR_ENGINE)
#else
Result run_upstream_multipart_headers(unsigned,bool,unsigned,const std::string &,const std::string &,int,unsigned,size_t);Result run_candidate_multipart_headers(unsigned,bool,unsigned,const std::string &,const std::string &,int,unsigned,size_t);
int main(){try{unsigned cases=0,failures=0;for(unsigned kind=0;kind<4;++kind)for(bool file:{false,true})for(unsigned flags=0;flags<4;++flags)for(const auto &boundary:{std::string("--boundary"),std::string("--b\0inary",9)})for(const auto &filename:{std::string("/private/upload"),std::string("/private/\0tail",14)})for(int fail:{-1,0,1,2,3})for(unsigned mode=0;mode<5;++mode)for(size_t header_length:{size_t(0),size_t(17),size_t(UINT32_MAX)}){
    auto a=run_upstream_multipart_headers(kind,file,flags,boundary,filename,fail,mode,header_length);auto b=run_candidate_multipart_headers(kind,file,flags,boundary,filename,fail,mode,header_length);
    if(a.buffer!=b.buffer||a.alternate!=b.alternate||a.header!=b.header||a.tried!=b.tried||a.content!=b.content||a.header_length!=b.header_length||a.fp!=b.fp||a.form_changed!=b.form_changed||a.data_changed!=b.data_changed||a.threw!=b.threw||a.error!=b.error||a.events!=b.events){std::cerr<<"kind="<<kind<<" file="<<file<<" flags="<<flags<<" fail="<<fail<<" mutation="<<mode<<" header-length="<<header_length<<'\n';throw std::runtime_error("multipart callback publication/IO/bytes/alias trace differential");}++cases;if(a.threw)++failures;
}
std::cout<<"{\"multipart_emit_cases\":"<<cases<<",\"native_append_failures\":"<<failures<<",\"errors\":0}\n";
}catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}}
#endif
