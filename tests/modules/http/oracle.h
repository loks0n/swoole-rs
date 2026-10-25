// Only foreign allocator/formatting dependencies are adapted. Extracted pinned
// first-party function bodies are unchanged; real native headers supply helpers.
#pragma once
#include "swoole_http.h"
#include "swoole_rs_http.h"
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <stdexcept>
#define HTTP_FUNCTIONS \
const char *get_status_message(int); \
int get_method(const char *, size_t); \
const char *get_method_string(int); \
size_t url_decode(char *, size_t); \
char *url_encode(const char *, size_t); \
bool parse_multipart_boundary(const char *, size_t, size_t, char **, int *);
namespace upstream { HTTP_FUNCTIONS }
namespace candidate { HTTP_FUNCTIONS }
#undef HTTP_FUNCTIONS
