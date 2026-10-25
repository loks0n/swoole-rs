#include "multipart_parser_oracle.h"
namespace upstream_multipart_parser {std::vector<std::string>files,logs;}
namespace candidate_multipart_parser {std::vector<std::string>files,logs;}
#undef swoole_trace
#define swoole_trace(...) ((void)0)
#undef swoole_sys_warning
#define swoole_sys_warning(...) log()
#undef swoole_error_log
#define swoole_error_log(...) log()
#include "upstream_multipart_parser.inc"
#include "candidate_multipart_parser.inc"
struct Result {std::string body;std::vector<std::string> uploads,logs;std::vector<unsigned>flags;std::vector<bool>returns;size_t content,length;unsigned completed;bool operator==(const Result&r)const{return body==r.body&&uploads==r.uploads&&logs==r.logs&&flags==r.flags&&returns==r.returns&&content==r.content&&length==r.length&&completed==r.completed;}};
std::string read_file(const std::string &name){std::ifstream file(name,std::ios::binary);return {std::istreambuf_iterator<char>(file),std::istreambuf_iterator<char>()};}
#define RUN(ns) Result run_##ns(const std::string &body,const std::vector<size_t>&cuts,unsigned maximum,unsigned upload_maximum){ \
ns::files.clear();ns::logs.clear();ns::String output,temp,input;ns::FormData form;form.multipart_buffer_=&output;form.upload_tmpfile=&temp;form.upload_tmpfile_fmt_="/tmp/swr-http-parser-XXXXXX";form.upload_max_filesize=upload_maximum;ns::Request request;request.form_data_=&form;request.max_length_=maximum;auto *parser=multipart_parser_init("boundary",8,&ns::mt_parser_settings);if(!parser)throw std::bad_alloc();form.multipart_parser_=parser;parser->data=&request;Result result;size_t previous=0; \
for(size_t cut:cuts){input.clear();input.append(body.data()+previous,cut-previous);previous=cut;bool returned=request.parse_multipart_data(&input);result.returns.push_back(returned);result.flags.push_back(request.excepted|(request.unavailable<<1)|(request.too_large<<2)|(request.multipart_header_parsed<<3));if(!returned||request.excepted)break;} \
if(parser->fp){fflush(parser->fp);fclose(parser->fp);parser->fp=nullptr;} \
result.body.assign(output.str,output.length);for(auto &file:ns::files){result.uploads.push_back(read_file(file));size_t pos=0;while((pos=result.body.find(file,pos))!=std::string::npos){result.body.replace(pos,file.size(),"<UPLOAD>");pos+=8;}unlink(file.c_str());} \
result.logs=ns::logs;result.content=request.content_length_;result.length=output.length;result.completed=request.tried_to_dispatch;multipart_parser_free(parser);return result;}
RUN(upstream_multipart_parser)
RUN(candidate_multipart_parser)
#undef RUN
int main(){try{size_t cases=0,split_cases=0,completed=0;auto check=[&](const std::string &body,const std::vector<size_t>&cuts,unsigned maximum,unsigned upload_maximum,bool file,const std::string &payload){auto a=run_upstream_multipart_parser(body,cuts,maximum,upload_maximum);auto b=run_candidate_multipart_parser(body,cuts,maximum,upload_maximum);if(!(a==b)){std::cerr<<"case="<<cases<<" maximum="<<maximum<<" upload="<<upload_maximum<<" cuts=";for(auto cut:cuts)std::cerr<<cut<<',';std::cerr<<"\nnative="<<a.body<<"\nrust="<<b.body<<'\n';throw std::runtime_error("actual multipart parser/file/state mismatch");}if(maximum==65536&&upload_maximum==65536){if(!a.completed||a.flags.empty()||a.flags.back()!=0||a.content!=a.length||a.uploads.size()!=size_t(file)||(file&&a.uploads[0]!=payload))throw std::runtime_error("independent complete upload/body assertion");for(bool returned:a.returns)if(!returned)throw std::runtime_error("complete parser rejected input");}++cases;if(cuts.size()>1)++split_cases;if(a.completed)++completed;};
for(bool file:{false,true})for(bool prefix:{false,true})for(auto payload:std::vector<std::string>{"","normal upload bytes",std::string("binary\0payload\r\n",16)}){
std::string body;if(prefix)body="--boundary\r\nContent-Disposition: form-data; name=field\r\n\r\nvalue\r\n";
body+="--boundary\r\nContent-Disposition: form-data; name=part";if(file)body+="; filename=sample.txt";body+="\r\nContent-Type: application/octet-stream\r\n\r\n";size_t data_start=body.size();body+=payload;size_t data_end=body.size();body+="\r\n--boundary--\r\n";
for(unsigned maximum:{0U,64U,65536U})for(unsigned upload_maximum:{0U,4U,65536U}){check(body,{body.size()},maximum,upload_maximum,file,payload);for(size_t cut=data_start;cut<=data_end;++cut)check(body,{cut,body.size()},maximum,upload_maximum,file,payload);
for(size_t step:{size_t(1),size_t(2),size_t(7)}){std::vector<size_t>cuts;for(size_t at=data_start;at<body.size();at+=step)cuts.push_back(at);cuts.push_back(body.size());check(body,cuts,maximum,upload_maximum,file,payload);}}}
std::cout<<"{\"actual_parser_file_cases\":"<<cases<<",\"split_cases\":"<<split_cases<<",\"completed_cases\":"<<completed<<",\"errors\":0}\n";
}catch(const std::exception&error){std::cerr<<error.what()<<'\n';return 1;}}
