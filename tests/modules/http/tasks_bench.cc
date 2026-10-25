#include "tasks_oracle.h"
#include "tasks_candidate.h"
#include <chrono>
struct Workload {const char *name;unsigned parts;bool snapshot;};
static const Workload workloads[]={{"parse-full",0,false},{"snapshot-full",0,true},{"parse-1",1,false},{"snapshot-1",1,true},{"parse-17",17,false},{"snapshot-17",17,true},{"parse-65",65,false},{"snapshot-65",65,true},{"parse-257",257,false},{"snapshot-257",257,true}};
static std::string range_for(unsigned count){std::string text="bytes=";for(unsigned i=0;i<count;++i){if(i)text+=',';text+=std::to_string(i*3)+'-'+std::to_string(i*3+1);}return text;}
static uint64_t mix(uint64_t hash,uint64_t value){return (hash^value)*1099511628211ULL;}
template<class Tasks>static uint64_t consume(uint64_t hash,const Tasks &tasks){for(const auto &task:tasks){hash=mix(hash,task.offset);hash=mix(hash,task.length);for(unsigned char byte:task.part_header)hash=mix(hash,byte);}return hash;}
static uint64_t run_native(const Workload &work,const std::string &range,size_t iterations){
 uint64_t hash=1469598103934665603ULL;upstream_tasks::Server server;
 for(size_t i=0;i<iterations;++i){upstream_tasks::StaticHandler handler(&server,"/file",5);handler.filesize=1048576;handler.parse_range(work.parts?range.c_str():nullptr,nullptr);
 hash=mix(hash,handler.content_length);
 if(work.snapshot){auto snapshot=handler.tasks;hash=mix(hash,snapshot.size());hash=consume(hash,snapshot);} }
 return hash;
}
static uint64_t run_selected(const Workload &work,const std::string &range,size_t iterations){
 uint64_t hash=1469598103934665603ULL;candidate_tasks::Server server;
 for(size_t i=0;i<iterations;++i){candidate_tasks::StaticHandlerV2 handler(&server,"/file",5);auto *core=candidate_tasks::StaticHandler::last_core;core->filesize=1048576;handler.parse_range(work.parts?range.c_str():nullptr,nullptr);
 hash=mix(hash,handler.get_content_length());
 if(work.snapshot){auto snapshot=handler.copy_tasks();hash=mix(hash,snapshot.size());hash=consume(hash,snapshot);} }
 return hash;
}
int main(int argc,char **argv){try{
 upstream_tasks::record_trace=candidate_tasks::record_trace=false;
 if(argc==2 && std::string(argv[1])=="--verify-only"){
  std::vector<std::pair<const Workload *,uint64_t>> results;
  for(const auto &work:workloads){const auto range=range_for(work.parts);const auto old=run_native(work,range,1);const auto selected=run_selected(work,range,1);if(old!=selected)throw std::runtime_error("normal task workload checksum mismatch");results.emplace_back(&work,old);}
  std::cout<<"{\"verified\":true,\"timed\":false,\"workloads\":[";bool comma=false;for(const auto &row:results){if(comma)std::cout<<',';comma=true;std::cout<<"{\"name\":\""<<row.first->name<<"\",\"parts\":"<<row.first->parts<<",\"iterations_per_engine\":1,\"checksum\":"<<row.second<<'}';}std::cout<<"]}\n";return 0;
 }
 // Prepared only. Invocation requires a separately acknowledged exclusive lease.
 if(argc!=5 || std::string(argv[1])!="--measure")throw std::runtime_error("use --verify-only or --measure ENGINE WORKLOAD ITERATIONS");
 const std::string engine=argv[2];if(engine!="native" && engine!="selected")throw std::runtime_error("unknown engine");const Workload *chosen=nullptr;for(const auto &work:workloads)if(work.name==std::string(argv[3]))chosen=&work;if(!chosen)throw std::runtime_error("unknown workload");const size_t iterations=std::stoull(argv[4]);if(!iterations || iterations>1000000)throw std::runtime_error("bounded iteration count required");const auto range=range_for(chosen->parts);
 const auto start=std::chrono::steady_clock::now();const uint64_t checksum=engine=="native"?run_native(*chosen,range,iterations):run_selected(*chosen,range,iterations);const auto elapsed=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-start).count();std::cout<<"{\"engine\":\""<<engine<<"\",\"workload\":\""<<chosen->name<<"\",\"iterations\":"<<iterations<<",\"checksum\":"<<checksum<<",\"elapsed_ns\":"<<elapsed<<"}\n";return 0;
}catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}}
