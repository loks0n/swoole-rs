#include "directory_oracle.h"
#include "directory_candidate.h"
#include <chrono>
#include <cstdint>
struct Workload {const char *name;unsigned entries;bool page;};
static const Workload workloads[]={
 {"scan-17",17,false},{"scan-65",65,false},{"scan-257",257,false},{"scan-1024",1024,false},
 {"page-17",17,true},{"page-65",65,true},{"page-257",257,true},{"page-1024",1024,true}};
static void prepare(const Workload &work){
 std::vector<std::string> entries={".",".."};
 for(unsigned i=work.entries;i--;)entries.emplace_back("file-"+std::to_string(i)+".txt");
 entries.push_back(entries.back());
 upstream_directory::names=candidate_directory::names=std::move(entries);
 upstream_directory::record_trace=candidate_directory::record_trace=false;
}
template<class Server>static Server server(){
 Server value;value.http_autoindex=true;
 value.http_index_files=std::make_shared<std::vector<std::string>>(std::initializer_list<std::string>{"absent","file-0.txt"});
 return value;
}
template<class Handler,class Server>static uint64_t run(Server &serv,const Workload &work,size_t iterations){
 uint64_t sum=1469598103934665603ULL;
 for(size_t i=0;i<iterations;++i){
  Handler handler(&serv,"/normal",7);
  if(!handler.get_dir_files() || !handler.try_serve_index_file() || !handler.has_index_file())throw std::runtime_error("normal workload index selection");
  sum=(sum^1u)*1099511628211ULL;
  if(work.page){
   IndexBuffer buffer(32);const size_t length=handler.make_index_page(&buffer);
   if(length!=buffer.length)throw std::runtime_error("normal workload page length");
   for(size_t j=0;j<length;++j)sum=(sum^static_cast<unsigned char>(buffer.str[j]))*1099511628211ULL;
  }
 }
 return sum;
}
int main(int argc,char **argv){try{
 if(argc==2 && std::string(argv[1])=="--verify-only"){
  std::vector<std::pair<const Workload *,uint64_t>> results;
  for(const auto &work:workloads){
   prepare(work);auto old=server<upstream_directory::Server>();auto selected=server<candidate_directory::Server>();
   const auto left=run<upstream_directory::StaticHandler>(old,work,1);
   const auto right=run<candidate_directory::StaticHandlerV2>(selected,work,1);
   if(left!=right)throw std::runtime_error("normal workload checksum mismatch");
   results.emplace_back(&work,left);
  }
  std::cout<<"{\"verified\":true,\"timed\":false,\"workloads\":[";
  bool comma=false;
  for(const auto &result:results){
   if(comma)std::cout<<',';comma=true;
   std::cout<<"{\"name\":\""<<result.first->name<<"\",\"entries\":"<<result.first->entries<<",\"iterations_per_engine\":1,\"checksum\":"<<result.second<<'}';
  }
  std::cout<<"]}\n";return 0;
 }
 // This branch is prepared only. Calling it requires the external host-wide
 // exclusive measurement lease; correctness/preparation never enters it.
 if(argc!=5 || std::string(argv[1])!="--measure")throw std::runtime_error("use --verify-only or --measure ENGINE WORKLOAD ITERATIONS");
 const std::string engine=argv[2];if(engine!="native" && engine!="selected")throw std::runtime_error("unknown engine");
 const Workload *chosen=nullptr;for(const auto &work:workloads)if(work.name==std::string(argv[3]))chosen=&work;
 if(!chosen)throw std::runtime_error("unknown workload");
 const size_t iterations=std::stoull(argv[4]);if(!iterations || iterations>1000000)throw std::runtime_error("bounded iteration count required");
 prepare(*chosen);auto old=server<upstream_directory::Server>();auto selected=server<candidate_directory::Server>();
 const auto start=std::chrono::steady_clock::now();
 const uint64_t checksum=engine=="native"?run<upstream_directory::StaticHandler>(old,*chosen,iterations):run<candidate_directory::StaticHandlerV2>(selected,*chosen,iterations);
 const auto elapsed=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-start).count();
 std::cout<<"{\"engine\":\""<<engine<<"\",\"workload\":\""<<chosen->name<<"\",\"iterations\":"<<iterations<<",\"checksum\":"<<checksum<<",\"elapsed_ns\":"<<elapsed<<"}\n";
 return 0;
}catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}}
