// Loaded supported facade lifecycle consumers; no Buffer source or Rust archive.
extern "C" {
#include <php.h>
#include <Zend/zend_exceptions.h>
}
#include "swoole.h"
#include "swoole_buffer.h"
#include <array>
#include <dlfcn.h>
#include <exception>
#include <utility>
static std::array<uint64_t, 8> events{};
static size_t event_count = 0;
static bool callback_metadata = true;
static void close_destroy(swoole::BufferChunk *chunk) {
    // CLOSE objects have no DATA allocation/destruction. No owner reentry.
    callback_metadata &= chunk->type == swoole::BufferChunk::TYPE_CLOSE && chunk->size == 0;
    if (event_count < events.size()) events[event_count++] = chunk->value.u64;
    else callback_metadata = false;
}
static const char *origin(const char *name) {
    Dl_info image{}; void *method = dlsym(RTLD_DEFAULT, name);
    return method && dladdr(method, &image) ? image.dli_fname : nullptr;
}
static swoole::BufferChunk *close_token(swoole::Buffer &buffer, uint64_t value) {
    auto *token = buffer.alloc(swoole::BufferChunk::TYPE_CLOSE, 0);
    token->value.u64 = value; token->destroy = close_destroy; return token;
}
ZEND_BEGIN_ARG_WITH_RETURN_TYPE_INFO_EX(arginfo_swr_facade_production, 0, 0, IS_ARRAY, 0)
ZEND_END_ARG_INFO()
PHP_FUNCTION(swr_facade_production) {
    ZEND_PARSE_PARAMETERS_NONE(); array_init(return_value);
    event_count = 0; callback_metadata = true;
    const char *pop_image = origin("_ZN6swoole6Buffer3popEv");
    const char *destroy_image = origin("_ZN6swoole6BufferD1Ev");
    const char *front_image = origin("_ZNK6swoole6Buffer5frontEv");
    const char *plan_image = origin("swr_v1_buffer_front_plan");
    const char *advance_image = origin("swr_v1_buffer_advance");
    if (!pop_image || !destroy_image) {
        zend_throw_exception(zend_ce_exception, "Production facade methods unavailable", 0); return;
    }
#ifdef SWOOLE_RS_BUFFER
    if (!front_image || !plan_image || !advance_image) {
        zend_throw_exception(zend_ce_exception, "Selected facade planning exports unavailable", 0); return;
    }
#endif
    add_assoc_string(return_value,"method_image",const_cast<char *>(pop_image));
    add_assoc_string(return_value,"destroy_image",const_cast<char *>(destroy_image));
    for (auto entry : {std::pair<const char *,const char *>{"front_image",front_image},
                      {"plan_image",plan_image},{"advance_image",advance_image}}) {
        if (entry.second) add_assoc_string(return_value,entry.first,const_cast<char *>(entry.second));
        else add_assoc_null(return_value,entry.first);
    }
    try {
        {
            swoole::Buffer buffer(3); buffer.append("a\0bcdefg",8);
            auto *first = buffer.front(); first->offset = 1; first->value.str[0] = 'z';
            auto *native = close_token(buffer,17); buffer.append("xy",2);
            auto *cached = buffer.front();
            add_assoc_bool(return_value,"cached_identity",first == cached);
            add_assoc_long(return_value,"cached_offset",cached->offset);
            add_assoc_stringl(return_value,"cached_bytes",cached->value.str,cached->length);
            add_assoc_long(return_value,"initial_length",buffer.length());
            add_assoc_long(return_value,"initial_count",buffer.count());
            zval bytes, lengths; array_init(&bytes); array_init(&lengths);
            for (unsigned i=0;i<3;++i) {
                auto *front=buffer.front();
                add_next_index_stringl(&bytes,front->value.str,front->length);
                buffer.pop(); add_next_index_long(&lengths,buffer.length());
            }
            add_assoc_zval(return_value,"data_before_token",&bytes);
            add_assoc_zval(return_value,"lengths_after_data",&lengths);
            add_assoc_bool(return_value,"native_identity",buffer.front() == native);
            buffer.pop();
            add_assoc_long(return_value,"callbacks_after_pop",event_count);
            add_assoc_long(return_value,"length_after_token",buffer.length());
            add_assoc_stringl(return_value,"tail_bytes",buffer.front()->value.str,buffer.front()->length);
        }
        {
            swoole::Buffer buffer(2); buffer.append("abc",3);
            close_token(buffer,31); buffer.append("defgh",5);
            close_token(buffer,32); buffer.append("i",1);
            auto *front=buffer.front(); front->offset=1;
            add_assoc_long(return_value,"drain_initial_length",buffer.length());
            add_assoc_long(return_value,"drain_initial_count",buffer.count());
            add_assoc_bool(return_value,"drain_cached_identity",buffer.front()==front);
        }
        zval observed; array_init(&observed);
        for (size_t i=0;i<event_count;++i) add_next_index_long(&observed,events[i]);
        add_assoc_zval(return_value,"close_events",&observed);
        add_assoc_bool(return_value,"callback_metadata",callback_metadata);
    } catch (const std::exception &error) { zend_throw_exception(zend_ce_exception,error.what(),0); }
}
static const zend_function_entry facade_functions[] = { PHP_FE(swr_facade_production,arginfo_swr_facade_production) PHP_FE_END };
extern "C" {
zend_module_entry swr_facade_production_module_entry = {
    STANDARD_MODULE_HEADER,"swr_facade_production",facade_functions,
    nullptr,nullptr,nullptr,nullptr,nullptr,"1",STANDARD_MODULE_PROPERTIES
};
ZEND_GET_MODULE(swr_facade_production)
}
