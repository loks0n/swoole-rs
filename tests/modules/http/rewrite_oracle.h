#pragma once
#include "swoole_server.h"
#include "swoole_static_handler.h"
#include "swoole_util.h"
#include "swoole_rs_http.h"
#include <regex>
#include <iostream>
#include <random>
#define REWRITE_ORACLE(ns) namespace ns { \
using swoole::starts_with; \
namespace http_server { \
struct RewriteRule{std::string pattern,replacement;bool is_regex=false;}; \
struct StaticHandler {std::string url,original;unsigned publications=0;bool fail_publish=false;explicit StaticHandler(const std::string &value):url(value),original(value){}const std::string &get_request_url()const{return url;}void set_request_url(const std::string &value){++publications;if(fail_publish)throw std::bad_alloc();url=value;} }; \
} \
struct Server {std::shared_ptr<std::vector<http_server::RewriteRule>> rewrite_rules;void add_rewrite_rule(const std::string &,const std::string &);bool apply_rewrite_rules(http_server::StaticHandler *);}; \
}
REWRITE_ORACLE(upstream_rewrite)
REWRITE_ORACLE(candidate_rewrite)
#undef REWRITE_ORACLE
