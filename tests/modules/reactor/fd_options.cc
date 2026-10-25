#include <cassert>
#include <cstdarg>
#include <cerrno>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <vector>
#include <fcntl.h>
#include "swoole_rs_reactor.h"
#define swoole_sys_warning(...) std::abort()
struct State {int status=0,descriptor=0;std::vector<int>operations;}state;
extern "C" int fcntl(int fd,int operation,...){assert(fd==17);state.operations.push_back(operation);if(operation==F_GETFL)return state.status;if(operation==F_GETFD)return state.descriptor;va_list args;va_start(args,operation);int value=va_arg(args,int);va_end(args);if(operation==F_SETFL)state.status=value;else{assert(operation==F_SETFD);state.descriptor=value;}return 0;}
namespace swoole {
struct Socket{int fd=17;bool nonblock=false,cloexec=false;bool set_fd_option(int,int);};
#include "fd_options.inc"
}
int main(){using namespace swoole;unsigned cases=0,checks=0,effects=0;auto check=[&](bool value){assert(value);++checks;};
for(int status:{0,O_APPEND,O_NONBLOCK,O_APPEND|O_NONBLOCK})for(int descriptor:{0,FD_CLOEXEC})for(int nonblock:{-1,0,1})for(int cloexec:{-1,0,1}){
 state=State();state.status=status;state.descriptor=descriptor;Socket socket;check(socket.set_fd_option(nonblock,cloexec));check(socket.nonblock==bool(nonblock)&&socket.cloexec==bool(cloexec));check(state.status==(nonblock<0?status:nonblock?status|O_NONBLOCK:status&~O_NONBLOCK));check(state.descriptor==(cloexec<0?descriptor:cloexec?descriptor|FD_CLOEXEC:descriptor&~FD_CLOEXEC));std::vector<int>expected;if(nonblock>=0){expected.push_back(F_GETFL);expected.push_back(F_SETFL);}if(cloexec>=0){expected.push_back(F_GETFD);expected.push_back(F_SETFD);}check(state.operations==expected);effects+=state.operations.size();++cases;
}
std::cout<<"{\"cases\":"<<cases<<",\"checks\":"<<checks<<",\"effects\":"<<effects<<",\"positive_only\":true}\n";
}
