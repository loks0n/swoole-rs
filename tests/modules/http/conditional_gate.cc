#include "conditional_oracle.h"
#undef strptime
#undef mktime
#undef gmtime
std::vector<std::string> calendar_events;
static std::string fields(const tm *value) {
 if (!value) return "null";
 std::ostringstream out;
 for (int field : {value->tm_sec,value->tm_min,value->tm_hour,value->tm_mday,value->tm_mon,value->tm_year,value->tm_wday,value->tm_yday,value->tm_isdst}) out << field << ',';
 return out.str();
}
char *calendar_strptime(const char *text,const char *format,tm *value) {
 char *end = ::strptime(text,format,value);
 int saved = errno;
 calendar_events.push_back(std::string("parse:")+format+":"+(end?std::to_string(end-text):"null")+":"+fields(value)+":"+std::to_string(saved));
 errno=saved; return end;
}
time_t calendar_mktime(tm *value) {
 time_t result=::mktime(value);int saved=errno;
 calendar_events.push_back("make:"+std::to_string(result)+":"+fields(value)+":"+std::to_string(saved));
 errno=saved;return result;
}
tm *calendar_gmtime(const time_t *value) {
 tm *result=::gmtime(value);int saved=errno;
 calendar_events.push_back("gmt:"+std::to_string(*value)+":"+fields(result)+":"+std::to_string(saved));
 errno=saved;return result;
}
static size_t cases=0;
static void compare(const std::string &date,time_t file,long offset,int kind) {
 upstream_conditional::Server old_server;old_server.timezone_=offset;
 candidate_conditional::Server new_server;new_server.timezone_=offset;
 upstream_conditional::StaticHandler old_handler;old_handler.serv=&old_server;old_handler.file_mtime=file;
 candidate_conditional::StaticHandler new_handler;new_handler.serv=&new_server;new_handler.file_mtime=file;
 // Short-circuited inputs must never dereference the server pointer.
 if(date.empty()||(kind==0&&date.size()>63)){old_handler.serv=nullptr;new_handler.serv=nullptr;}
 calendar_events.clear();errno=EINTR;
 bool original=kind?old_handler.is_modified_range(date):old_handler.is_modified(date);
 int old_errno=errno;auto events=calendar_events;
 calendar_events.clear();errno=EINTR;
 bool candidate=kind?new_handler.is_modified_range(date):new_handler.is_modified(date);
 if(original!=candidate||old_errno!=errno||events!=calendar_events){
  std::cerr<<"case "<<cases<<" kind "<<kind<<" date size "<<date.size()<<" date "<<date<<" original "<<original<<" candidate "<<candidate<<" errno "<<old_errno<<"/"<<errno<<'\n';
  for(auto &event:events)std::cerr<<"old "<<event<<'\n';
  for(auto &event:calendar_events)std::cerr<<"new "<<event<<'\n';
  std::abort();
 }
 ++cases;
}
int main(){
 // Warm libc's timezone/locale state before errno/call-order observations.
 setenv("LC_ALL","C",1);setlocale(LC_ALL,"C");
 std::vector<std::string> dates={"","invalid","Sun, 06 Nov 1994 08:49:37 GMT","Sun, 06 Nov 1994 08:49:37 UTC","Sunday, 06-Nov-94 08:49:37 GMT","Sun Nov  6 08:49:37 1994","Sun, 06 Nov 1994 08:49:37 GMT suffix","Mon, 29 Feb 2000 00:00:00 GMT","Fri, 29 Feb 1900 00:00:00 GMT","Sun, 32 Nov 1994 08:49:37 GMT","Sun, 06 Nov 1994 25:49:37 GMT","Sun, 06 Nov 1994 08:49:60 GMT","Sunday, 06-Nov-68 08:49:37 GMT","Sunday, 06-Nov-69 08:49:37 GMT",std::string(63,'x'),std::string(64,'x'),std::string(1000,'x')};
 dates.emplace_back("Sun, 06 Nov 1994 08:49:37 GMT\0ignored",34);
 dates.emplace_back("Sun, 06 Nov\0 1994 08:49:37 GMT",29);
 size_t seed_dates=dates.size();
 for(size_t i=0;i<seed_dates;++i){
  std::string value=dates[i];
  for(size_t length=1;length<value.size();++length)dates.push_back(value.substr(0,length));
 }
 for(const char *zone:{"UTC0","EST5EDT","JST-9"}){
  setenv("TZ",zone,1);tzset();tm warm{};warm.tm_year=94;warm.tm_mon=10;warm.tm_mday=6;::mktime(&warm);
  time_t zero=0;::gmtime(&zero);
  for(const auto &date:dates)for(time_t file:{time_t(-2208988800LL),time_t(-1),time_t(0),time_t(784111776),time_t(784111777),time_t(784111778),time_t(4102444800LL)})for(long offset:{-3600L,0L,32400L})for(int kind:{0,1})compare(date,file,offset,kind);
 }
 std::mt19937 rng(42819);for(unsigned i=0;i<2048;++i){std::string date;for(unsigned n=rng()%100;n--; )date.push_back(static_cast<char>(rng()%128));for(int kind:{0,1})compare(date,784111777,0,kind);}
 // Original successful parse + unrepresentable gmtime dereferences null: only the correction is exercised.
 candidate_conditional::StaticHandler corrected;corrected.file_mtime=std::numeric_limits<time_t>::max();calendar_events.clear();
 assert(!corrected.is_modified_range("Sun, 06 Nov 1994 08:49:37 GMT"));
 assert(calendar_events.size()==2&&calendar_events.back().find(":null:")!=std::string::npos);
 candidate_conditional::Server server;server.timezone_=std::numeric_limits<long>::min();corrected.serv=&server;corrected.file_mtime=0;
 assert(!corrected.is_modified("Sun, 06 Nov 1994 08:49:37 GMT"));
 std::cout<<"{\"differential_cases\":"<<cases<<",\"corrected_null_gmtime_cases\":1,\"corrected_signed_overflow_cases\":1,\"errors\":0}"<<'\n';
}
