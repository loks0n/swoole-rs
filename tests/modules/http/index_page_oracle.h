#pragma once
#include "swoole_server.h"
#include "swoole_static_handler.h"
#include "swoole_rs_http.h"
#include "swoole_rs_http_context.h"
#include <cassert>
#include <iostream>
#include <random>
#include <sstream>
#include "index_buffer.h"
#define INDEX_ORACLE(name) namespace name { \
using String = IndexBuffer; \
class StaticHandler { public: \
 std::string dir_path; std::set<std::string> dir_files; unsigned reads=0; bool read_ok=true; \
 bool get_dir_files(){++reads;return read_ok;} \
 size_t make_index_page(String *); \
}; }
INDEX_ORACLE(upstream_index)
INDEX_ORACLE(candidate_index)
#undef INDEX_ORACLE
