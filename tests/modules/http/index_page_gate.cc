#include "index_page_oracle.h"
static size_t cases=0, failures=0;
static void compare(const std::string &path,const std::set<std::string> &entries,size_t capacity,unsigned fail=0,bool positive_only=false){
 upstream_index::StaticHandler old_handler;old_handler.dir_path=path;old_handler.dir_files=entries;old_handler.read_ok=positive_only||(cases%2)==0;
 candidate_index::StaticHandler new_handler;new_handler.dir_path=path;new_handler.dir_files=entries;new_handler.read_ok=old_handler.read_ok;
 IndexBuffer old_buffer(capacity),new_buffer(capacity);old_buffer.fail=fail;new_buffer.fail=fail;
 bool old_throw=false,new_throw=false;size_t old_result=0,new_result=0;
 errno=EINTR;try{old_result=old_handler.make_index_page(&old_buffer);}catch(const std::bad_alloc&){old_throw=true;}int saved=errno;
 errno=EINTR;try{new_result=new_handler.make_index_page(&new_buffer);}catch(const std::bad_alloc&){new_throw=true;}
 if(old_result!=new_result||old_throw!=new_throw||saved!=errno||old_handler.dir_path!=new_handler.dir_path||old_handler.reads!=new_handler.reads||old_buffer.storage!=new_buffer.storage||old_buffer.length!=new_buffer.length||old_buffer.size!=new_buffer.size||old_buffer.offset!=new_buffer.offset||old_buffer.events!=new_buffer.events){
  std::cerr<<"case "<<cases<<" path "<<path<<" entries "<<entries.size()<<" capacity "<<capacity<<" fail "<<fail<<" throw "<<old_throw<<"/"<<new_throw<<" result "<<old_result<<"/"<<new_result<<" errno "<<saved<<"/"<<errno<<" length "<<old_buffer.length<<"/"<<new_buffer.length<<" size "<<old_buffer.size<<"/"<<new_buffer.size<<'\n';
  for(auto e:old_buffer.events)std::cerr<<"old reserve "<<e<<'\n';for(auto e:new_buffer.events)std::cerr<<"new reserve "<<e<<'\n';
  std::abort();
 }
 ++cases;if(old_throw)++failures;
}
int main(int argc,char **argv){
 if(argc==2&&std::string(argv[1])=="--positive-only") {
  const std::vector<std::set<std::string>> entries={{},{"."},{".."},{"a.txt","b.txt","a b"}};
  for(const char *path:{"/","/dir","/dir/","/a b"})
   for(const auto &files:entries)for(size_t capacity:{16U,128U,1024U,32768U})compare(path,files,capacity,0,true);
  std::cout<<"{\"positive_page_cases\":"<<cases<<",\"native_allocation_failure_cases\":"<<failures
           <<",\"fault_profiles_executed\":false,\"full_gate_passed\":false,\"errors\":"<<failures<<"}\n";
  return failures!=0;
 }
 if(argc!=1)return 2;
 try{throw std::bad_alloc();}catch(const std::bad_alloc&){}
 std::vector<std::set<std::string>> entries={{},{"."},{".."},{".","..","file.txt"},{"file.txt","other.txt","<script>","a b","a&b",std::string("a\0b",3)}, {std::string(255,'z'),std::string(4096,'x')}};
 std::vector<std::string> paths={"/","/dir","/dir/","/a b&<x>",std::string("/\0hidden",8),std::string(4095,'p')};
 for(const auto &path:paths)for(const auto &files:entries)for(size_t capacity:{16U,128U,1024U,32768U})for(unsigned fail:{0U,1U,2U,3U,4U})compare(path,files,capacity,fail);
 std::mt19937 rng(23118);
 for(unsigned trial=0;trial<512;++trial){std::set<std::string> files;for(unsigned n=rng()%16;n--;){std::string file;for(unsigned length=rng()%80;length--;)file.push_back(static_cast<char>(rng()%256));files.insert(file);}compare(paths[rng()%paths.size()],files,16U<<(rng()%8));}
 // Unknown/unsupported metadata must leave both output and count untouched.
 swr_v1_http_index_page_input input{};input.part=3;uint8_t bytes[8];memset(bytes,0xcc,sizeof(bytes));size_t written=77;
 assert(swr_v1_http_index_page(&input,bytes,sizeof(bytes),&written)<0&&written==77);for(auto b:bytes)assert(b==0xcc);
 // Zero storage made the legacy FORMAT_GROW alignment loop non-progressing.
 candidate_index::StaticHandler corrected;corrected.dir_path="/";IndexBuffer zero(0);zero.length=0;assert(corrected.make_index_page(&zero)>0);
 std::cout<<"{\"page_differential_cases\":"<<cases<<",\"native_allocation_failure_cases\":"<<failures<<",\"corrected_zero_capacity_cases\":1,\"invalid_metadata_groups\":1,\"errors\":0}"<<'\n';
}
