// Positive original callback continuations; no short/invalid/overflow oracle.
#include "test_core.h"
#include <iostream>
#include <vector>
using swoole::String;
static unsigned checks=0;
static void check(bool ok,const char *label) { if(!ok)throw std::runtime_error(label); ++checks; }
int main() {
    SwooleG.std_allocator={std::malloc,std::calloc,std::realloc,std::free}; SwooleG.pagesize=4096;
    try {
        {
            String value("xxone\r\n"); value.offset=2; unsigned callbacks=0;
            check(value.split("\r\n",2,[&](const char *p,size_t n){ ++callbacks; check(std::string(p,n)=="xxone\r\n","initial prefix"); value.offset=3; return false; })==-1,"false result");
            check(callbacks==1 && value.offset==3,"false callback offset side effect preserved");
            value.offset=2; bool caught=false;
            try { value.split("\r\n",2,[&](const char *,size_t)->bool{ value.offset=4; throw std::runtime_error("callback"); }); }
            catch(const std::runtime_error &){caught=true;}
            check(caught && value.offset==4,"throwing callback offset prefix");
        }
        {
            String value("one\r\n"); std::vector<std::string> packets;
            auto consumed=value.split("\r\n",2,[&](const char *p,size_t n){ packets.emplace_back(p,n); if(packets.size()==1)value.append("two\r\n",5); return true; });
            check(consumed==10 && value.offset==10,"reallocation continuation metadata");
            check(packets==std::vector<std::string>({"one\r\n","two\r\n"}),"reallocation fresh bytes");
        }
        {
            String value("a\r\nb\r\n"); std::vector<std::string> packets;
            auto consumed=value.split("\r\n",2,[&](const char *p,size_t n){packets.emplace_back(p,n); if(packets.size()==1)value.str[3]='c'; return true;});
            check(consumed==6 && value.offset==6,"mutated continuation metadata");
            check(packets==std::vector<std::string>({"a\r\n","c\r\n"}),"fresh future byte mutation");
        }
        {
            String value("a\r\nb\r\n"); unsigned callbacks=0;
            auto consumed=value.split("\r\n",2,[&](const char *,size_t){++callbacks;value.offset=3;return true;});
            check(consumed==6 && value.offset==6 && callbacks==1,"fresh offset plus previous advance");
        }
        {
            String value(std::string("a\0b\r\ntrail",10)); unsigned callbacks=0;
            auto consumed=value.split("\r\n",2,[&](const char *p,size_t n){++callbacks;check(std::string(p,n)==std::string("a\0b\r\n",5),"binary callback");return true;});
            check(consumed==5 && value.offset==5 && callbacks==1,"residual split metadata");
            value.reduce(consumed);check(value.to_std_string()=="trail","residual owner content");
        }
        std::cout<<"{\"positive_continuation_checks\":"<<checks<<",\"cases\":5,\"errors\":0}\n";
    }catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}
}
