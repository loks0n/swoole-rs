// Real Server/SyncClient/Context APIs. One scenario per isolated process.
#include "swoole_api.h"
#include "swoole_server.h"
#include "swoole_http.h"
#include "swoole_client.h"
#include "swoole_signal.h"
#include <algorithm>
#include <thread>
#include <fstream>
#include <iostream>
#include <cassert>
#include <dlfcn.h>
using namespace swoole;
static std::string hex(const std::string &s){static const char c[]="0123456789abcdef";std::string out;for(unsigned char b:s){out+=c[b>>4];out+=c[b&15];}return out;}
static void fields(std::string &out,const std::unordered_map<std::string,std::string>&m){std::vector<std::string> rows;for(auto&kv:m)rows.push_back(hex(kv.first)+":"+hex(kv.second));std::sort(rows.begin(),rows.end());for(auto&r:rows)out+=r+";";out+="|";}
int main(int argc,char **argv){
    Dl_info loaded{};
    if(!dladdr(reinterpret_cast<const void *>(&http_server::listen), &loaded) || !loaded.dli_fname)return 13;
    std::cerr << "SWR_WRAPPER_LIBRARY=" << loaded.dli_fname << std::endl;
    Dl_info core{};
    if(!dladdr(reinterpret_cast<const void *>(&swoole_init), &core) || !core.dli_fname)return 14;
    std::cerr << "SWR_CORE_LIBRARY=" << core.dli_fname << std::endl;
    if(argc!=2)return 2;std::string scenario=argv[1],body,extra;bool multipart=false;
    if(scenario=="form"){body="a=1&b=%00";extra="Content-Type: application/x-www-form-urlencoded\r\n";}
    else if(scenario=="multipart"||scenario=="file"){
        multipart=true;extra="Content-Type: multipart/form-data; boundary=abc\r\n";
        if(scenario=="file")body="--abc\r\nContent-Disposition: form-data; name=\"up\"; filename=\"x.bin\"\r\nContent-Type: application/octet-stream\r\n\r\n"+std::string("x\0y",3)+"\r\n--abc--\r\n";
        else body="\r\n--abc\r\nContent-Disposition: form-data; name=\"a\"\r\n\r\n"+std::string("x\0y",3)+"\r\n--abc\r\nContent-Disposition: form-data; name=\"b\"\r\n\r\ntwo\r\n--abc--\r\n";
    }else if(scenario!="get"&&scenario!="empty-query")return 3;
    std::string path=scenario=="empty-query"?"/p?":"/p?a=1?b=2";
    std::string request=(scenario=="get"||scenario=="empty-query"?"GET ":"POST ")+path+" HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n"+extra+"Content-Length: "+std::to_string(body.size())+"\r\n\r\n"+body;
    swoole_init();swoole_set_log_level(SW_LOG_ERROR);
    std::vector<std::string> files;std::string response;int result=0;std::thread client;
    auto server=http_server::listen(":0",[&](http_server::Context &ctx){
        std::string out=hex(ctx.request_path)+"|"+hex(ctx.query_string)+"|"+std::to_string(ctx.version)+"|"+std::to_string(ctx.keepalive)+"|"+std::to_string(ctx.post_form_urlencoded)+"|"+hex(ctx.body)+"|";
        fields(out,ctx.headers);fields(out,ctx.form_data);
        std::vector<std::string> uploaded;for(auto&kv:ctx.files){files.push_back(kv.second);std::ifstream f(kv.second,std::ios::binary);std::string data((std::istreambuf_iterator<char>(f)),{});uploaded.push_back(hex(kv.first)+":"+hex(data));}std::sort(uploaded.begin(),uploaded.end());for(auto&s:uploaded)out+=s+";";
        ctx.setStatusCode(201);ctx.setHeader("X-Witness",std::string("first\0hidden",12));if(!ctx.end(out))result=4;
    });
    if(!server)return 5;server->worker_num=1;
    server->onWorkerStart=[&](Server*s,Worker*){client=std::thread([&,s]{
        swoole_signal_block_all();network::SyncClient c(SW_SOCK_TCP);
        if(!c.connect("127.0.0.1",s->get_primary_port()->port))result=6;
        else{if(c.send(request.data(),request.size())!=(ssize_t)request.size())result=7;char buf[4096];while(true){auto n=c.recv(buf,sizeof(buf));if(n>0)response.append(buf,n);else{if(n<0)result=8;break;}}c.close();}
        kill(s->get_master_pid(),SIGTERM);
    });};
    if(server->start()!=SW_OK)result=9;if(client.joinable())client.join();
    bool cleaned=true;for(auto&f:files)if(access(f.c_str(),F_OK)==0)cleaned=false;
    if(!cleaned)result=10;if(scenario=="file"&&files.size()!=1)result=12;
    if(response.find("201 Created")==std::string::npos||response.find("X-Witness: first\r\n")==std::string::npos)result=11;
    std::cout<<"{\"scenario\":\""<<scenario<<"\",\"wire_hex\":\""<<hex(response)<<"\",\"cleanup\":"<<(cleaned?"true":"false")<<",\"exit\":"<<result<<"}"<<std::endl;
    server.reset();swoole_clean();return result;
}
