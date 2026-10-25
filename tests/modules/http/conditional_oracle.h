#pragma once
#include "swoole_server.h"
#include "swoole_static_handler.h"
#include "swoole_rs_http.h"
#include <array>
#include <cassert>
#include <iostream>
#include <random>
#include <sstream>
extern std::vector<std::string> calendar_events;
char *calendar_strptime(const char *,const char *,tm *);
time_t calendar_mktime(tm *);
tm *calendar_gmtime(const time_t *);
#define CONDITIONAL_ORACLE(name) namespace name { \
struct Server { long timezone_ = 0; }; \
class StaticHandler { public: \
 Server *serv = nullptr; time_t file_mtime = 0; \
 time_t get_file_mtime() const { return file_mtime; } \
 bool is_modified(const std::string &) const; \
 bool is_modified_range(const std::string &) const; \
}; }
CONDITIONAL_ORACLE(upstream_conditional)
CONDITIONAL_ORACLE(candidate_conditional)
#undef CONDITIONAL_ORACLE
#define strptime calendar_strptime
#define mktime calendar_mktime
#define gmtime calendar_gmtime
