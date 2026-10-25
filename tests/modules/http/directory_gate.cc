#include "directory_oracle.h"
#include "directory_candidate.h"
static void check(bool ok,const char *message){if(!ok)throw std::runtime_error(message);}
int main(){try{
 size_t cases=0;
 std::vector<std::vector<std::string>> listings={
  {".",".."}, {"z.txt",".","a.txt","..","z.txt"},
  {"index.html","README.md",".","..","a b","a&b","<name>","é.txt"},
  {std::string(200,'x'),"a.txt",".",".."}};
 for(unsigned count:{1u,17u,65u,257u,1024u}) {
  std::vector<std::string> entries={".",".."};
  for(unsigned i=count;i--;)entries.emplace_back("file-"+std::to_string(i)+".txt");
  entries.push_back(entries.back());listings.push_back(std::move(entries));
 }
 for(const auto &entries:listings) for(const std::string &path:{std::string("/"),std::string("/normal"),std::string("/normal/")})
 for(unsigned mode=0;mode<4;++mode) for(size_t capacity:{16u,128u,32768u}) {
  upstream_directory::names=candidate_directory::names=entries;
  upstream_directory::trace.clear();candidate_directory::trace.clear();
  upstream_directory::Server a;candidate_directory::Server b;a.http_autoindex=b.http_autoindex=true;
  if(mode){a.http_index_files=std::make_shared<std::vector<std::string>>();b.http_index_files=std::make_shared<std::vector<std::string>>();
   *a.http_index_files=*b.http_index_files=mode==1?std::vector<std::string>{"missing"}:mode==2?std::vector<std::string>{"README.md","index.html","a.txt"}:std::vector<std::string>{"a.txt","index.html","README.md"};}
  upstream_directory::StaticHandler old(&a,path.data(),path.size());candidate_directory::StaticHandlerV2 selected(&b,path.data(),path.size());
  check(old.try_serve_index_file()==selected.try_serve_index_file(),"index priority result");
  check(old.get_dir_files()==selected.get_dir_files(),"directory scan result");
  check(old.get_dir_files()==selected.get_dir_files(),"cached directory scan result");
  IndexBuffer left(capacity),right(capacity);
  check(old.make_index_page(&left)==selected.make_index_page(&right),"page result length");
  check(left.storage==right.storage && left.length==right.length && left.size==right.size && left.offset==right.offset && left.events==right.events,"page bytes/native storage effects");
  check(upstream_directory::trace==candidate_directory::trace,"native scan/cache/index call order");
  ++cases;
 }
 std::cout<<"{\"directory_cases\":"<<cases<<",\"errors\":0,\"normal_controls_only\":true}\n";
 return 0;
}catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}}
