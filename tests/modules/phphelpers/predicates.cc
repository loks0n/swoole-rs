#include "swoole_rs_phphelpers.h"
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <limits>
#include <vector>
// Complete unchanged PHP bodies with modeled parsing/observation/publication.
struct zend_string { size_t len; };
struct zval { uint32_t count; };
static zend_string string_value;
static zval array_value;
static std::vector<int> events;
static bool parse_ok;
static uint32_t zend_array_count(zval *array) { events.push_back(3); return array->count; }
#define PHP_FUNCTION(name) static bool name()
#define ZEND_PARSE_PARAMETERS_START(a,b) events.push_back(1);
#define Z_PARAM_STR(value) value=&string_value;
#define Z_PARAM_ARRAY(value) value=&array_value;
#define ZEND_PARSE_PARAMETERS_END() events.push_back(2); if (!parse_ok) return false;
#define Z_ARRVAL_P(value) (value)
#define RETURN_BOOL(value) do { const bool result=(value); events.push_back(4); return result; } while (false)
namespace reference {
#include "reference-predicates.inc"
}
namespace candidate {
#include "candidate-predicates.inc"
}
int main() {
    size_t cases=0;
    const size_t lengths[]={0,1,2,255,65535,std::numeric_limits<size_t>::max()};
    for (bool valid : {false,true}) for (size_t length : lengths) {
        parse_ok=valid;string_value.len=length;array_value.count=static_cast<uint32_t>(length);
        for (bool array : {false,true}) {
            events.clear();const bool expected=array?reference::swoole_array_is_empty():reference::swoole_str_is_empty();const auto trace=events;
            events.clear();const bool actual=array?candidate::swoole_array_is_empty():candidate::swoole_str_is_empty();
            assert(actual==expected && events==trace);
            assert(events==(valid?(array?std::vector<int>{1,2,3,4}:std::vector<int>{1,2,4}):std::vector<int>{1,2}));
            ++cases;
        }
    }
    std::printf("{\"complete_bodies\":2,\"cases\":%zu,\"matched\":true}\n",cases);
}
