#include "proxy_oracle.h"
#include <iostream>
#include <limits>
#include <vector>
void check(bool condition, const char *message) { if (!condition) throw std::runtime_error(message); }
int main() {
    try {
        size_t packed = 0, handshakes = 0, credentials = 0;
        auto pack = [&](const std::string &target, const std::string &host, const std::string &user, const std::string &password, int port) {
            upstream_proxy::HttpProxy before{user,password,target,port};
            candidate_proxy::HttpProxy after{user,password,target,port};
            // Every short prefix, exact capacity, spare capacity, and size query.
            upstream_proxy::String query{nullptr,0,91};
            auto required = before.pack(&query,host);
            std::vector<size_t> capacities;
            for(size_t n=0;n<=std::min(required+2,size_t(64));++n) capacities.push_back(n);
            capacities.insert(capacities.end(),{required,required+1,required+2});
            for (size_t capacity : capacities) {
                std::vector<char> a(capacity+2,char(0xcc)), b=a;
                upstream_proxy::String left{a.data(),capacity,91};
                candidate_proxy::String right{b.data(),capacity,91};
                errno=EINTR; auto count_a=before.pack(&left,host); int error_a=errno;
                errno=EINTR; auto count_b=after.pack(&right,host); int error_b=errno;
                check(count_a==count_b && a==b && error_a==error_b && left.length==right.length,"proxy request differential");
                ++packed;
            }
        };
        std::vector<std::string> text={"", "localhost", "[::1]", std::string("ab\0cd",5), std::string(512,'z'), std::string("x\xffy",3)};
        for (auto &target:text) for(auto &host:text) for(int port:{0,80,-1,65535,std::numeric_limits<int>::min(),std::numeric_limits<int>::max()})
            for(auto &credential:text) pack(target,host,credential,credential,port);
        pack("target","host","","secret",443);
        pack("target","host","user","",443);
        for(size_t u:{0U,1U,253U,254U,255U,256U,512U,1048576U}) for(size_t p:{0U,1U,253U,254U,255U,256U,512U,1048576U}) {
            std::string user(u,'u'), password(p,'p');
            for(unsigned variant=0;variant<4;++variant) {
                if(variant==1&&!user.empty()) user[user.size()/2]=0;
                if(variant==2&&!password.empty()) password[password.size()/2]=0;
                if(variant==3&&!user.empty()) user[0]=0;
                upstream_proxy::HttpProxy before{user,password,"target",443};
                candidate_proxy::HttpProxy after{user,password,"target",443};
                errno=EINTR;auto a=before.get_auth_str();int saved=errno;
                errno=EINTR;auto b=after.get_auth_str();
                check(a==b&&saved==errno,"fixed credential buffer/auth/errno differential");++credentials;
            }
        }
        auto handshake=[&](const std::string &input) {
            upstream_proxy::String left{const_cast<char *>(input.data()),input.size(),input.size()};
            candidate_proxy::String right{left.str,left.size,left.length};
            upstream_proxy::last_error=candidate_proxy::last_error=991;
            errno=EINTR; bool a=upstream_proxy::HttpProxy::handshake(&left); int error_a=errno;
            errno=EINTR; bool b=candidate_proxy::HttpProxy::handshake(&right); int error_b=errno;
            check(a==b && upstream_proxy::last_error==candidate_proxy::last_error && error_a==error_b,"proxy handshake/last-error differential"); ++handshakes;
        };
        std::vector<std::string> responses={"HTTP/1.1 200 Connection established\r\n", "http/1.0 200 a different message with trailing bytes", "HTTP/1.1X200 Connection established\r\n", "HTTP/1.1 407 Proxy authorization needed\r\n", "HTTP/1.1 \t\v\f\r\n200 Connection established\r\n", "HTTP/1.1 "+std::string(60,' '), std::string("HTTP/1.1 \0",10)+std::string(40,'X')};
        for(auto &input:responses) for(size_t n=0;n<=input.size();++n) handshake(input.substr(0,n));
        uint32_t seed=90271; auto next=[&]() { seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed; };
        for(unsigned i=0;i<8192;++i) {
            std::string input=(i%3==0 ? "HTTP/1.1 " : i%3==1 ? "HTTP/1.0X" : "invalid");
            input.append(next()%15,' ');
            if(i%2) input+="200";
            while(input.size()<36+next()%50) input+=char(next()%128);
            handshake(input);
        }
        std::cout<<"{\"pack_cases\":"<<packed<<",\"credential_cases\":"<<credentials<<",\"handshake_cases\":"<<handshakes<<",\"errors\":0}\n";
    } catch(const std::exception &e) { std::cerr<<e.what()<<'\n';return 1; }
}
