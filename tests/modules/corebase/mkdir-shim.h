// SPDX-License-Identifier: Apache-2.0
// Deterministic original-trace fixture independently prepared by M01.
#include <unistd.h>
#include <sys/stat.h>
#include <limits.h>
#include <string>
#include <cstring>
#include <algorithm>
#include <cerrno>
#include <iostream>
#include <sstream>
#include <vector>
#include <cstdlib>
static std::string scenario;
static int access_calls,mkdir_calls,last_error;
struct Event {std::string operation,path;int argument,result,before,after;};
static std::vector<Event> events;
static void record(const char*op,const char*p,int arg,int result,int before,int after){events.push_back({op,p,arg,result,before,after});errno=after;}
static int test_access(const char*p,int mode){int before=errno;if(scenario=="real"){int v=::access(p,mode);int e=errno;record("access",p,mode,v,before,e);return v;}int n=++access_calls;int result=scenario=="existing"||(scenario=="alternating"&&n%2==0)?0:-1;int after=result==0?before:(scenario=="denied"?EACCES:scenario=="eperm-success"?EPERM:ENOENT);record("access",p,mode,result,before,after);return result;}
static int test_mkdir(const char*p,mode_t mode){int before=errno;if(scenario=="real"){int v=::mkdir(p,mode);int e=errno;record("mkdir",p,mode,v,before,e);return v;}int n=++mkdir_calls;int result=0,after=before;if(scenario=="denied"){result=-1;after=EACCES;}else if(scenario=="race"){result=-1;after=EEXIST;}else if(scenario=="fail2"&&n==2){result=-1;after=ENOTDIR;}else if(scenario=="missing-parent"){result=-1;after=ENOENT;}else if(scenario=="mkdir-too-long"){result=-1;after=ENAMETOOLONG;}record("mkdir",p,mode,result,before,after);return result;}
static void test_warning(const char*,const char*p){int e=errno;last_error=e;record("warning",p,0,0,e,e);}
static void test_errorlog(int level,int code,const char*,int limit){int e=errno;last_error=code;record("errorlog","",limit,code,e,e);}
#ifdef swoole_sys_warning
#undef swoole_sys_warning
#endif
#ifdef swoole_error_log
#undef swoole_error_log
#endif
#define swoole_sys_warning(...) test_warning(__VA_ARGS__)
#define swoole_error_log(...) test_errorlog(__VA_ARGS__)
#define access test_access
#define mkdir test_mkdir
