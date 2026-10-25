#include "request_lifecycle_oracle.h"
#include <cerrno>
#undef fclose
#undef unlink
static void check(bool yes,const char *message){if(!yes)throw std::runtime_error(message);}
struct Outcome {std::vector<std::string> events;std::string body,path;size_t maximum=0,header_length=0;bool linked=false,restored=false;int init_errno=0,destroy_errno=0;};
#define RUN_REQUEST(ns) \
static Outcome run_##ns(const std::string &body,const std::string &directory,bool file,bool direct){ \
 ns::events.clear();ns::next_id=0;ns::observed=nullptr; \
 auto *request=new ns::Request();auto *original=new ns::String(4096); \
 const std::string header="normal-header";original->append(header.data(),header.size());original->append(body.data(),body.size()); \
 request->buffer_=original;request->header_length_=header.size();request->form_data_=new ns::FormData(); \
 request->form_data_->multipart_boundary_buf="normal-boundary";request->form_data_->multipart_boundary_len=15; \
 ns::Server server;server.upload_tmp_dir=directory;server.upload_max_filesize=8192;ns::events.clear();ns::observed=request; \
 errno=EINTR;if(!request->init_multipart_parser(&server)){std::cerr<<"Normal request initialization failed; partial object is not destroyed or probed\n";std::_Exit(1);} \
 const int init_errno=errno;Outcome outcome;outcome.init_errno=init_errno;auto *form=request->form_data_; \
 outcome.body.assign(request->buffer_->str,request->buffer_->length);outcome.path=form->upload_tmpfile_fmt_;outcome.maximum=form->upload_max_filesize;outcome.header_length=original->length; \
 outcome.linked=form->multipart_parser_->data==request && form->multipart_buffer_==original && request->buffer_!=original && std::string(form->upload_tmpfile->str,form->upload_tmpfile->length)==form->upload_tmpfile_fmt_; \
 if(file){form->multipart_parser_->fp=tmpfile();if(!form->multipart_parser_->fp){std::cerr<<"Positive tmpfile setup unavailable\n";std::_Exit(1);}} \
 errno=EINTR;if(direct){request->destroy_multipart_parser();outcome.destroy_errno=errno;outcome.restored=request->buffer_==original && request->form_data_==nullptr;}else outcome.restored=true; \
 delete request;if(!direct)outcome.destroy_errno=errno;ns::observed=nullptr;outcome.events=ns::events;delete original;return outcome; \
}
RUN_REQUEST(upstream_request_lifecycle)
RUN_REQUEST(candidate_request_lifecycle)
#undef RUN_REQUEST
int main(){try{
 size_t cases=0;
 const std::vector<std::string> bodies={"","body","normal multipart data",std::string("binary\0payload",14),std::string(1024,'b')};
 for(const auto &body:bodies)for(const std::string &path:{std::string("/virtual/upload"),std::string("/virtual/with space")})for(bool file:{false,true})for(bool direct:{false,true}){
  const auto old=run_upstream_request_lifecycle(body,path,file,direct);const auto selected=run_candidate_request_lifecycle(body,path,file,direct);
  check(old.init_errno==selected.init_errno && old.destroy_errno==selected.destroy_errno,"normal native errno observations");
  check(old.events==selected.events,"native parser/buffer/stdio/virtual-unlink effect order and field observations");
  check(old.body==body && selected.body==body && old.path==path+"/swoole.upfile.XXXXXX" && old.path==selected.path,"normal buffer and upload format bytes");
  check(old.maximum==8192 && old.maximum==selected.maximum && old.header_length==13 && old.header_length==selected.header_length && old.linked && selected.linked && old.restored && selected.restored,"normal ownership links/trim/restoration");
  ++cases;
 }
 upstream_request_lifecycle::observed=nullptr;candidate_request_lifecycle::observed=nullptr;
 upstream_request_lifecycle::events.clear();candidate_request_lifecycle::events.clear();
 delete new upstream_request_lifecycle::Request();delete new candidate_request_lifecycle::Request();
 check(upstream_request_lifecycle::events.empty() && candidate_request_lifecycle::events.empty(),"normal empty request destructor");
 std::cout<<"{\"normal_request_lifecycle_cases\":"<<cases<<",\"empty_destructor_groups\":1,\"errors\":0,\"partial_failure_reentry_profiles_executed\":false}\n";
 return 0;
}catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}}
