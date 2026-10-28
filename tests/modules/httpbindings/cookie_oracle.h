#pragma once
#include "swoole_rs_httpbindings.h"
#include <algorithm>
#include <cstdarg>
#include <cmath>
#include <ctime>
#include <cstdint>
#include <cstdio>
#include <functional>
#include <limits>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
#include <cstring>
using zend_long = int64_t;
struct zend_string { std::string value; };
struct smart_str { std::string value; };
#define ZSTR_LEN(s) ((s)->value.size())
#define ZSTR_VAL(s) ((s)->value.c_str())
#define ZEND_STRL(s) s, sizeof(s)-1
#define E_WARNING 2
struct Bailout {};
struct Oracle {
    std::vector<std::string> trace;
    std::set<zend_string *> allocated;
    std::function<void()> warning;
    size_t fail = SIZE_MAX;
    ~Oracle() { for (auto *p : allocated) delete p; }
    void event(const std::string &value) {
        trace.push_back(value);
        if (trace.size() - 1 == fail) throw Bailout{};
    }
    zend_string *make(std::string value) {
        auto *p = new zend_string{std::move(value)}; allocated.insert(p); return p;
    }
};
extern thread_local Oracle *oracle;
inline void smart_str_appendl(smart_str *buffer, const char *s, size_t length) {
    std::string value(s, length); oracle->event("append:" + value); buffer->value += value;
}
inline void smart_str_append(smart_str *b, zend_string *s) { smart_str_appendl(b, ZSTR_VAL(s), ZSTR_LEN(s)); }
inline void smart_str_appends(smart_str *b, const char *s) { smart_str_appendl(b, s, strlen(s)); }
inline void smart_str_appendc(smart_str *b, char s) { smart_str_appendl(b, &s, 1); }
inline void smart_str_append_long(smart_str *b, zend_long value) { auto s = std::to_string(value); smart_str_appendl(b, s.data(), s.size()); }
inline zend_string *smart_str_extract(smart_str *b) {
    oracle->event("extract:" + b->value); auto *s = oracle->make(b->value); b->value.clear(); return s;
}
inline void zend_string_free(zend_string *s) {
    oracle->event("free:" + s->value); oracle->allocated.erase(s); delete s;
}
inline zend_string *php_format_date(const char *format, size_t length, int64_t timestamp, int) {
    oracle->event("date:" + std::string(format, length) + ":" + std::to_string(timestamp));
    return oracle->make("DATE-" + std::to_string(timestamp));
}
inline int64_t php_time() { oracle->event("time"); return 1700000000; }
inline zend_string *php_url_encode(const char *s, size_t length) {
    oracle->event("encode:" + std::string(s, length)); std::string out;
    const char *hex = "0123456789ABCDEF";
    for (size_t i=0; i<length; i++) {
        unsigned char c=s[i];
        if ((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='-'||c=='_'||c=='.') out+=c;
        else if(c==' ')out+='+';
        else {out+='%';out+=hex[c>>4];out+=hex[c&15];}
    }
    return oracle->make(out);
}
inline void php_swoole_error(int, const char *format, ...) {
    char buf[1024]; va_list args; va_start(args, format); vsnprintf(buf, sizeof(buf), format, args); va_end(args);
    oracle->event("warning:" + std::string(buf));
    if (oracle->warning) oracle->warning();
}
#define ILLEGAL_COOKIE_CHARACTER_PRINT "\",\", \";\", \" \", \"\\t\", \"\\r\", \"\\n\", \"\\013\", or \"\\014\""
#define ILLEGAL_COOKIE_CHARACTER ",; \t\r\n\013\014"
#define COOKIE_FACADE(namespace_name) namespace namespace_name { \
static constexpr zend_long maxValidSeconds = 253402300800; \
struct HttpCookie { \
    zend_string *name=nullptr, *value=nullptr, *path=nullptr, *domain=nullptr, *sameSite=nullptr, *priority=nullptr; \
    zend_long expires=0; bool encode_=true, secure=false, httpOnly=false, partitioned=false; \
    smart_str buffer_; zend_string *toString(); \
}; }
COOKIE_FACADE(upstream_cookie)
COOKIE_FACADE(candidate_cookie)
