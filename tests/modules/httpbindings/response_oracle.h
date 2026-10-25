#pragma once
#include "swoole_rs_httpbindings.h"
#include <algorithm>
#include <clocale>
#include <climits>
#include <cstdio>
#include <cstring>
#include <strings.h>
#include <functional>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#define ZEND_STRL(s) s,sizeof(s)-1
#define SW_STRL(s) s,sizeof(s)-1
#define SW_STRCASEEQ(s,n,v) swoole_strcaseeq(s,n,SW_STRL(v))
#define SW_HTTP_SERVER_SOFTWARE "fixture-server"
#define SW_HTTP_DEFAULT_CONTENT_TYPE "text/html"
#ifndef RESPONSE_NO_COMPRESSION
#define SW_HAVE_COMPRESSION 1
#endif
struct Exit {};
struct Oracle {std::vector<std::string>trace;size_t fail=SIZE_MAX;std::function<void(const std::string&)>hook;
 void event(const std::string&s){trace.push_back(s);if(trace.size()-1==fail)throw Exit{};if(hook)hook(s);}};
extern thread_local Oracle *oracle;
#define SW_ASSERT(v) do{oracle->event(std::string("assert:")+((v)?"1":"0"));if(!(v))throw Exit{};}while(0)
struct String {std::string value;size_t length=0;
 void append(const char*p,size_t n){oracle->event("append:"+std::string(p,n));value.append(p,n);length=value.size();}};
struct zend_string {std::string value;};
#define ZSTR_VAL(p) ((p)->value.data())
#define ZSTR_LEN(p) ((p)->value.size())
inline zend_string*php_swoole_http_get_date(){oracle->event("date");static zend_string date{"Wed, 01 Jan 2020 00:00:00 GMT"};return &date;}
// Exact enum block is generated from pinned public header, not copied here.
struct Result {std::vector<std::string>trace;std::string output;bool exited=false;uint32_t facts=0;int published=0;
 bool operator==(const Result&r)const{return trace==r.trace&&output==r.output&&exited==r.exited&&facts==r.facts&&published==r.published;}};
#define RESPONSE_DECL(N) namespace N {Result tail(uint32_t,uint32_t,size_t,unsigned,size_t);int header(const std::string&);}
RESPONSE_DECL(upstream_response)
RESPONSE_DECL(candidate_response)
