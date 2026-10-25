#include "tasks_oracle.h"
#include "tasks_candidate.h"
#include <cerrno>
static void check(bool value,const char *message){if(!value)throw std::runtime_error(message);}
struct Snapshot {std::vector<swr_v2_http_static_task> tasks;std::vector<std::string> trace;std::string type,end;size_t length=0;int status=0,error=0,type_reference=0;bool native_tasks_empty=false;};
static Snapshot old_case(size_t filesize,const char *range,const char *date,const std::string &mime,const std::string &boundary,unsigned repeat){
 upstream_tasks::Server server;upstream_tasks::StaticHandler handler(&server,"/file",5);handler.filesize=filesize;handler.mime=mime;handler.boundary=boundary;upstream_tasks::trace.clear();
 errno=EINTR;handler.parse_range(range,date);if(repeat)handler.parse_range(repeat==1?"bytes=0-0":(repeat==2?nullptr:""),nullptr);
 Snapshot out;for(const auto &part:handler.tasks){swr_v2_http_static_task copy;copy.offset=part.offset;copy.length=part.length;memcpy(copy.part_header,part.part_header,256);out.tasks.push_back(copy);}const auto &type=handler.get_content_type();out.type_reference=&type==&handler.mime?1:(&type==&handler.content_type?2:0);out.type=type;out.end=handler.end_part;out.length=handler.content_length;out.status=handler.status_code;out.error=errno;out.trace=upstream_tasks::trace;return out;
}
static Snapshot selected_case(size_t filesize,const char *range,const char *date,const std::string &mime,const std::string &boundary,unsigned repeat){
 candidate_tasks::Server server;Snapshot out;
 {candidate_tasks::StaticHandlerV2 handler(&server,"/file",5);auto *core=candidate_tasks::StaticHandler::last_core;core->filesize=filesize;core->mime=mime;core->boundary=boundary;candidate_tasks::trace.clear();
 errno=EINTR;handler.parse_range(range,date);if(repeat)handler.parse_range(repeat==1?"bytes=0-0":(repeat==2?nullptr:""),nullptr);
 out.tasks=handler.copy_tasks();const auto &type=handler.get_content_type();out.type_reference=&type==&core->mime?1:(&type==&core->content_type?2:0);out.type=type;out.end=handler.get_end_part();out.length=handler.get_content_length();out.status=handler.status_code;out.error=errno;out.trace=candidate_tasks::trace;out.native_tasks_empty=core->tasks.empty();}
 // This is Native-owned send scratch. All data remains valid after Rust owner drop.
 for(const auto &task:out.tasks)check(memchr(task.part_header,0,256)!=nullptr,"snapshot initialized header terminator");
 return out;
}
int main(){try{
 size_t cases=0;
 for(size_t size:{size_t(1),size_t(17),size_t(4096)})for(const char *range:{static_cast<const char *>(nullptr),"","bytes=0-0","bytes=0-","bytes=-1","bytes=0-0,1-2","bytes=1-3,5-7"})for(const char *date:{static_cast<const char *>(nullptr),"unmodified","modified"})for(const std::string &mime:{std::string("text/plain"),std::string("application/octet-stream")})for(const std::string &boundary:{std::string("fixed-boundary"),std::string("second-normal-boundary")})for(unsigned repeat:{0u,1u,2u,3u}){
  const auto old=old_case(size,range,date,mime,boundary,repeat);const auto selected=selected_case(size,range,date,mime,boundary,repeat);
  check(old.tasks.size()==selected.tasks.size(),"owned task count/snapshot");
  for(size_t i=0;i<old.tasks.size();++i)check(old.tasks[i].offset==selected.tasks[i].offset && old.tasks[i].length==selected.tasks[i].length && memcmp(old.tasks[i].part_header,selected.tasks[i].part_header,256)==0,"copied offsets/lengths/all initialized part header bytes");
  check(old.type==selected.type && old.end==selected.end && old.length==selected.length && old.status==selected.status,"range response bytes/accounting/status");
  check(old.type_reference==selected.type_reference && selected.type_reference==(selected.tasks.size()>1?2:1),"Native MIME/content string reference identity");
  check(old.trace==selected.trace && old.error==selected.error,"native MIME/boundary/date effects and errno");check(selected.native_tasks_empty,"legacy native task collection remains empty");++cases;
 }
 std::cout<<"{\"normal_task_owner_cases\":"<<cases<<",\"errors\":0,\"normal_controls_only\":true}\n";return 0;
}catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}}
