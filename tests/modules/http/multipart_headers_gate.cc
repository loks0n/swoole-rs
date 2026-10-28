#include "multipart_headers_oracle.h"
#define FIXTURE(ns) namespace ns { \
Request *observed=nullptr;multipart_parser *parser=nullptr;std::vector<std::string>events;int append_attempt=0,fail_append=-1,file_failure=0; \
String *sw_tg_buffer(){static String value;return &value;} \
std::string snapshot(){return std::to_string(observed->excepted)+","+std::to_string(observed->form_data_->upload_filesize)+","+std::to_string(parser->fp!=nullptr)+","+std::to_string(errno);} \
int swoole_tmpfile(char *name){events.push_back("tmp:"+std::string(name)+":"+snapshot());name[0]='!';errno=EACCES;return file_failure==1?-1:3;} \
FILE *multipart_fdopen(int fd,const char *mode){events.push_back("open:"+std::to_string(fd)+":"+mode+":"+snapshot());errno=ENOSPC;return file_failure==2?nullptr:reinterpret_cast<FILE*>(uintptr_t(2));} \
void multipart_warning(){events.push_back("warning:"+snapshot());errno=EIO;} }
FIXTURE(upstream_multipart_headers)
FIXTURE(candidate_multipart_headers)
#undef FIXTURE
#define swoole_trace(...) ((void)0)
#define swoole_sys_warning(...) multipart_warning()
#define fdopen multipart_fdopen
#include "upstream_multipart_headers.inc"
#include "candidate_multipart_headers.inc"
#undef fdopen
struct Result {std::string buffer,temp;size_t uploaded;unsigned excepted;uintptr_t fp;int error;bool threw;std::vector<std::string>events;std::vector<char>scratch;};
#define RUN(ns) Result run_##ns(const std::string &name,const std::string &value,int fail,int file,bool seeded){ \
ns::events.clear();ns::append_attempt=0;ns::fail_append=fail;ns::file_failure=file;auto *scratch=ns::sw_tg_buffer();std::fill(scratch->bytes.begin(),scratch->bytes.end(),'?'); \
ns::Buffer buffer;ns::String temporary;ns::FormData form{&buffer,nullptr,0,&temporary,"/tmp/upload.XXXXXX",1234};ns::Request request{&form,unsigned(seeded)};ns::multipart_parser parser{&request,seeded?reinterpret_cast<FILE*>(uintptr_t(1)):nullptr};ns::observed=&request;ns::parser=&parser; \
errno=EINTR;bool threw=false;try{if(ns::multipart_on_header_field(&parser,name.data(),name.size())!=0)throw std::runtime_error("header field");if(ns::multipart_on_header_value(&parser,value.data(),value.size())!=0)throw std::runtime_error("header value");}catch(const std::bad_alloc&){threw=true;} \
return {buffer.bytes,std::string(temporary.str,24),form.upload_filesize,request.excepted,reinterpret_cast<uintptr_t>(parser.fp),errno,threw,ns::events,scratch->bytes}; }
RUN(upstream_multipart_headers)
RUN(candidate_multipart_headers)
#undef RUN
int main(){try{unsigned cases=0,failures=0;auto check=[&](const std::string &name,const std::string &value,int fail,int file,bool seeded){auto a=run_upstream_multipart_headers(name,value,fail,file,seeded);auto b=run_candidate_multipart_headers(name,value,fail,file,seeded);if(a.buffer!=b.buffer||a.temp!=b.temp||a.uploaded!=b.uploaded||a.excepted!=b.excepted||a.fp!=b.fp||a.error!=b.error||a.threw!=b.threw||a.events!=b.events||a.scratch!=b.scratch){std::cerr<<"name="<<name<<" value="<<value<<" append="<<fail<<" file="<<file<<" seeded="<<seeded<<'\n';throw std::runtime_error("multipart header effects/scratch/state mismatch");}++cases;if(a.threw)++failures;};
const std::vector<std::string>names={"Content-Disposition","content-disposition","CONTENT-DISPOSITION","Content-Disposition ","Content-Type","",std::string("content-disposition\0x",21)};
const std::vector<std::string>values={"","form-data; name=\"x\"","filename","filename=","FiLeNaMe=\"x.txt\"; filename=\"y\"","filename =x;filename=z","=filename;\tfilename=ignored",";; \r\nfilename=x;other=y",std::string("form-data\0;filename=x",21),"filename=x\0", "fileName;other=value"};
// Warm native exception/stdio-independent paths before comparing errno.
check("Content-Disposition","filename=x",0,0,false);
for(auto &name:names)for(auto &value:values)for(int fail:{-1,0,1,2,3})for(int file:{0,1,2})for(bool seeded:{false,true})check(name,value,fail,file,seeded);
uint32_t seed=7829341;auto next=[&](){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;};for(unsigned i=0;i<2048;++i){std::string value;for(unsigned j=0,n=next()%12;j<n;++j){value+="; \t"[next()%3];value+=next()%4?"name":"filename";if(next()%3){value+='=';for(unsigned k=0,n=next()%20;k<n;++k)value+="a; =\t\r\n"[next()%7];}}check("content-disposition",value,-1,next()%3,next()%2);}
std::cout<<"{\"multipart_header_cases\":"<<cases<<",\"native_append_failures\":"<<failures<<",\"errors\":0}\n";
}catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}}
