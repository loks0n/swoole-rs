// Complete extracted PHP push/pop bodies over a tracing native effect fixture.
// This proves ordering under bounded scripted outcomes, not Zend/scheduler life.
#include <cassert>
#include <cstdlib>
#include <cstdint>
#include <cstdio>
#include <initializer_list>
#include <string>
#include <vector>
#include <utility>
#include "swoole_rs_phpcollections.h"
struct zval { int refs; int value; };
static zval input, duplicate;
static bool outcome;
static int error_code, published, returned;
static std::vector<std::string> trace;
struct Channel {
    enum { ERROR_OK=0 };
    bool push(zval *data, double timeout) {
        trace.push_back("push:"+std::to_string(data->value)+":"+std::to_string(timeout)); return outcome;
    }
    void *pop(double timeout) { trace.push_back("pop:"+std::to_string(timeout)); return outcome?&duplicate:nullptr; }
    int get_error() { trace.push_back("error"); return error_code; }
};
static Channel chan;
static Channel *channel_coro_get_ptr(zval *) { trace.push_back("get"); return &chan; }
static void *swoole_channel_coro_ce=nullptr;
static zval *sw_zval_dup(zval *data) { trace.push_back("dup"); duplicate=*data; return &duplicate; }
static void efree(zval *) { trace.push_back("free"); }
static void zend_update_property_long(void *, zval *, const char *, size_t, int value) {
    trace.push_back("publish:"+std::to_string(value));published=value;
}
#define PHP_METHOD(cls,name) void name(zval *ZEND_THIS)
#define ZEND_PARSE_PARAMS_THROW 0
#define ZEND_PARSE_PARAMETERS_START_EX(flags,min,max) trace.push_back("parse");
#define Z_PARAM_ZVAL(data) data=&input;
#define Z_PARAM_OPTIONAL
#define Z_PARAM_DOUBLE(timeout) timeout=-0.125;
#define ZEND_PARSE_PARAMETERS_END_EX(action)
#define Z_TRY_ADDREF_P(data) do { trace.push_back("retain"); ++(data)->refs; } while(0)
#define Z_TRY_DELREF_P(data) do { trace.push_back("release"); --(data)->refs; } while(0)
#define SW_Z8_OBJ_P(p) p
#define ZEND_STRL(s) s,sizeof(s)-1
#define RETURN_TRUE do { trace.push_back("true");returned=1; return; } while(0)
#define RETURN_FALSE do { trace.push_back("false");returned=0; return; } while(0)
#define RETVAL_ZVAL(data,copy,dtor) do { trace.push_back("result");returned=(data)->value; } while(0)
namespace original {
#include "native-effects.inc"
}
static size_t plan_calls=0;
static uint64_t counted_channel_plan(uint32_t operation, uint32_t phase, uint8_t success) {
    ++plan_calls;
    return swr_v1_phpcollections_channel_plan(operation, phase, success);
}
#define swr_v1_phpcollections_channel_plan counted_channel_plan
namespace selected {
#include "selected-effects.inc"
}
#undef swr_v1_phpcollections_channel_plan
struct Observation { std::vector<std::string> events; int ref, copied_ref, code, result; };
static Observation run(void (*function)(zval *),bool success,int error,int value) {
    trace.clear();input={7,value};duplicate={7,value};outcome=success;error_code=error;published=-99;returned=-99;
    function(&input);
    return {trace,input.refs,duplicate.refs,published,returned};
}
int main() {
    size_t checks=0;
    for(bool success:{false,true}) for(int error:{0,1,2,3,-1}) for(int value:{0,1,-1,123456}) {
        for(auto functions:{std::pair{original::push,selected::push},std::pair{original::pop,selected::pop}}) {
            plan_calls=0;
            auto a=run(functions.first,success,error,value);
            assert(plan_calls==0);
            auto b=run(functions.second,success,error,value);
            assert(plan_calls==2);
            assert(a.events==b.events && a.ref==b.ref && a.copied_ref==b.copied_ref && a.code==b.code && a.result==b.result);
            ++checks;
        }
    }
    std::printf("{\"actual_push_pop_effect_traces\":%zu,\"rust_calls_per_completed_operation\":2}\n",checks);
}
