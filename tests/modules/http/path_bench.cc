#include "path_bench_oracle.h"
struct Fixture {
 std::string root;
 Fixture(){char pattern[]="/tmp/swr-http-path-bench-XXXXXX";char *made=mkdtemp(pattern);if(!made)throw std::runtime_error("mkdtemp");char canonical[PATH_MAX];if(!realpath(made,canonical))throw std::runtime_error("realpath");root=canonical;if(::mkdir((root+"/sub").c_str(),0755)!=0)throw std::runtime_error("mkdir");std::ofstream(root+"/file.txt")<<"ordinary fixture\n";if(::symlink((root+"/file.txt").c_str(),(root+"/link.txt").c_str())!=0)throw std::runtime_error("symlink");}
 ~Fixture(){::unlink((root+"/link.txt").c_str());::unlink((root+"/file.txt").c_str());::rmdir((root+"/sub").c_str());::rmdir(root.c_str());}
 PathWorkload work(const std::string &name){PathWorkload w;w.root=root;if(name=="file")w.url="/file.txt";else if(name=="missing")w.url="/missing.txt";else if(name=="relative")w.url="/sub/../file.txt";else if(name=="symlink")w.url="/link.txt";else if(name=="index"){w.url="/sub";w.index=true;}else if(name=="location-miss"){w.url="/file.txt";w.location_miss=true;}else throw std::runtime_error("workload");return w;}
};
struct Snapshot {bool result;int status;size_t length;std::string filename,directory;bool operator==(const Snapshot &r)const{return result==r.result&&status==r.status&&length==r.length&&filename==r.filename&&directory==r.directory;} };
template<class Server,class Handler>Snapshot run_once(const PathWorkload &work){Server server(work);Handler handler(&server,work.url);bool result=handler.try_serve();return {result,handler.status_code,handler.l_filename,std::string(handler.filename,handler.l_filename),handler.dir_path};}
static Snapshot check(const PathWorkload &work){auto old=run_once<upstream_path::Server,upstream_path::StaticHandler>(work);auto candidate=run_once<candidate_path::Server,candidate_path::StaticHandler>(work);if(!(old==candidate))throw std::runtime_error("native/Rust output differs");return old;}
template<class Server,class Handler>int measure(const PathWorkload &work,const Snapshot &expected,const std::string &engine,const std::string &name,size_t iterations){
 Server server(work);size_t signature=0;auto step=[&](){Handler handler(&server,work.url);bool result=handler.try_serve();return handler.l_filename+size_t(handler.status_code)+size_t(result);};
 for(unsigned i=0;i<128;++i)step();
 auto start=std::chrono::steady_clock::now();for(size_t i=0;i<iterations;++i)signature+=step();auto finish=std::chrono::steady_clock::now();
 size_t wanted=iterations*(expected.length+size_t(expected.status)+size_t(expected.result));
 if(signature!=wanted)throw std::runtime_error("timed result differs");check(work);
 std::cout<<"{\"engine\":\""<<engine<<"\",\"workload\":\""<<name<<"\",\"operations\":"<<iterations<<",\"ns\":"<<std::chrono::duration_cast<std::chrono::nanoseconds>(finish-start).count()<<",\"signature\":"<<signature<<",\"errors\":0}\n";return 0;
}
int main(int argc,char **argv){try{Fixture fixture;if(argc==2&&std::string(argv[1])=="--check"){for(const char *name:{"file","missing","relative","symlink","index","location-miss"})check(fixture.work(name));std::cout<<"{\"actual_filesystem_workloads\":6,\"errors\":0}\n";return 0;}if(argc!=4)throw std::runtime_error("engine workload iterations required");std::string engine=argv[1],name=argv[2];size_t iterations=std::stoull(argv[3]);if(!iterations)throw std::runtime_error("zero iterations");auto work=fixture.work(name);auto expected=check(work);if(engine=="native")return measure<upstream_path::Server,upstream_path::StaticHandler>(work,expected,engine,name,iterations);if(engine=="rust")return measure<candidate_path::Server,candidate_path::StaticHandler>(work,expected,engine,name,iterations);throw std::runtime_error("engine");}catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}}
