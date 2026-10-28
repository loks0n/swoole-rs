#pragma once
#include "swoole_server.h"
#include "swoole_static_handler.h"
#include "swoole_util.h"
#include "swoole_rs_http.h"
#include <regex>
#include <iostream>
#include <random>
// Upstream's handler publishes into native strings; the candidate's rewrites the Rust
// static context, read back through its text.
#define UPSTREAM_HANDLER \
struct StaticHandler {std::string url,original;unsigned publications=0;explicit StaticHandler(const std::string &value):url(value),original(value){}const std::string &get_request_url()const{return url;}void set_request_url(const std::string &value){++publications;url=value;} };
#define CANDIDATE_HANDLER \
struct StaticHandler {swr_v2_http_context *context_; \
 explicit StaticHandler(const std::string &value):context_(swr_v2_http_context_new(reinterpret_cast<const uint8_t *>(value.data()),value.size(),4096)){if(!context_)throw std::bad_alloc();} \
 ~StaticHandler(){swr_v2_http_context_drop(context_);} StaticHandler(const StaticHandler &)=delete; \
 std::string text(uint32_t kind)const{size_t n=0;if(swr_v2_http_context_text(context_,kind,nullptr,0,&n)<0)throw std::logic_error("text");std::string v(n,'\0');if(n&&swr_v2_http_context_text(context_,kind,reinterpret_cast<uint8_t *>(&v[0]),n,&n)<0)throw std::logic_error("text");return v;} };
#define REWRITE_ORACLE(ns, HANDLER) namespace ns { \
using swoole::starts_with; \
namespace http_server { \
struct RewriteRule{std::string pattern,replacement;bool is_regex=false;}; \
HANDLER \
} \
struct Server {std::shared_ptr<std::vector<http_server::RewriteRule>> rewrite_rules;void add_rewrite_rule(const std::string &,const std::string &);bool apply_rewrite_rules(http_server::StaticHandler *);}; \
}
REWRITE_ORACLE(upstream_rewrite, UPSTREAM_HANDLER)
REWRITE_ORACLE(candidate_rewrite, CANDIDATE_HANDLER)
#undef REWRITE_ORACLE
