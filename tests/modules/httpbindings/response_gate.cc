#include "response_oracle.h"
int main(){try{
 const char*locale=getenv("HTTPBINDINGS_LOCALE");if(locale&&!setlocale(LC_ALL,locale)){std::cerr<<"Unsupported locale "<<locale<<'\n';return 77;}
 size_t headers=0;
 for(const std::string&name:{"Server","Connection","Date","Content-Length","Content-Type","Transfer-Encoding","Content-Encoding","custom"})for(unsigned byte=0;byte<256;byte++)for(unsigned position=0;position<3;position++){
  std::string key=name;if(position==0)key[0]=char(byte);else if(position==1)key+=char(byte);else for(char&c:key)if(c>='A'&&c<='Z')c+=32;
  if(upstream_response::header(key)!=candidate_response::header(key))throw std::runtime_error("response known header mismatch");headers++;
 }
 std::cout<<"{\"header_names\":"<<headers<<",\"errors\":0}\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
