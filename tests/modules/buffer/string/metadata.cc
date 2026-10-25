// Loaded production ownership consumers; no local String implementation/archive.
extern "C" {
#include <php.h>
#include <Zend/zend_exceptions.h>
}
#include "swoole_string.h"
#include <dlfcn.h>
#include <exception>
static unsigned allocated = 0, freed = 0;
static void *allocate(size_t size) { void *p = std::malloc(size); if (p) ++allocated; return p; }
static void dispose(void *p) { ++freed; std::free(p); }
static const swoole::Allocator allocator{allocate, std::calloc, std::realloc, dispose};
static const char *origin(const char *name) {
    Dl_info image{};
    void *method = dlsym(RTLD_DEFAULT, name);
    return method && dladdr(method, &image) ? image.dli_fname : nullptr;
}
static void snapshot(zval *rows, const char *name, const swoole::String &value) {
    zval row; array_init(&row);
    add_assoc_stringl(&row, "bytes", value.str ? value.str : "", value.length);
    add_assoc_long(&row, "length", value.length);
    add_assoc_long(&row, "capacity", value.size);
    add_assoc_long(&row, "offset", value.offset);
    add_assoc_bool(&row, "owner_null", value.str == nullptr);
    add_assoc_bool(&row, "allocator_retained", value.allocator == &allocator);
    add_assoc_zval(rows, name, &row);
}
ZEND_BEGIN_ARG_WITH_RETURN_TYPE_INFO_EX(arginfo_swr_metadata_production, 0, 0, IS_ARRAY, 0)
ZEND_END_ARG_INFO()
PHP_FUNCTION(swr_metadata_production) {
    ZEND_PARSE_PARAMETERS_NONE();
    array_init(return_value);
    const char *release_image = origin("_ZN6swoole6String7releaseEv");
    const char *move_image = origin("_ZN6swoole6String4moveEOS0_");
    const char *transition_image = origin("swr_v1_string_transition");
    if (!release_image || !move_image) {
        zend_throw_exception(zend_ce_exception, "Production ownership methods unavailable", 0); return;
    }
    add_assoc_string(return_value, "method_image", const_cast<char *>(release_image));
    add_assoc_string(return_value, "move_image", const_cast<char *>(move_image));
    if (transition_image) add_assoc_string(return_value, "transition_image", const_cast<char *>(transition_image));
    else add_assoc_null(return_value, "transition_image");
    allocated = freed = 0;
    try {
        {
            swoole::String source(32, &allocator); source.append("a\0b", 3); source.offset = 2;
            char *owner = source.str;
            source.clear();
            snapshot(return_value, "clear", source);
            add_assoc_bool(return_value, "clear_owner_same", source.str == owner);
            add_assoc_long(return_value, "free_after_clear", freed);
            source.append("x\0y", 3); source.offset = 1;
            swoole::String moved(std::move(source));
            snapshot(return_value, "moved", moved);
            snapshot(return_value, "move_source", source);
            add_assoc_bool(return_value, "move_owner_same", moved.str == owner);
            add_assoc_long(return_value, "free_after_move", freed);
            char *detached = moved.release();
            snapshot(return_value, "released", moved);
            add_assoc_bool(return_value, "release_owner_same", detached == owner);
            add_assoc_stringl(return_value, "detached", detached, 3);
            add_assoc_long(return_value, "free_before_detached_disposal", freed);
            dispose(detached); // Provenance-aware native effect, after Rust returned.
        }
        {
            swoole::String source(16, &allocator), target(8, &allocator);
            source.append("new", 3); source.offset = 2; target.append("old", 3);
            char *owner = source.str;
            unsigned before = freed;
            target = std::move(source);
            snapshot(return_value, "assigned", target);
            snapshot(return_value, "assignment_source", source);
            add_assoc_bool(return_value, "assignment_owner_same", target.str == owner);
            add_assoc_long(return_value, "assignment_disposals", freed - before);
            auto *same = &target;
            target = std::move(*same);
            snapshot(return_value, "self_assigned", target);
            add_assoc_bool(return_value, "self_owner_same", target.str == owner);
            add_assoc_long(return_value, "assignment_disposals_after_self", freed - before);
        }
        {
            swoole::String value(64, &allocator); value.append("abc", 3);
            value.size = 33; // A readable prefix advertised by public mutable metadata.
            value.extend();
            snapshot(return_value, "extended", value);
        }
        add_assoc_long(return_value, "native_allocations", allocated);
        add_assoc_long(return_value, "native_frees", freed);
    } catch (const std::exception &error) { zend_throw_exception(zend_ce_exception, error.what(), 0); }
}
static const zend_function_entry metadata_functions[] = {
    PHP_FE(swr_metadata_production, arginfo_swr_metadata_production)
    PHP_FE_END
};
extern "C" {
zend_module_entry swr_metadata_production_module_entry = {
    STANDARD_MODULE_HEADER, "swr_metadata_production", metadata_functions,
    nullptr, nullptr, nullptr, nullptr, nullptr, "1", STANDARD_MODULE_PROPERTIES
};
ZEND_GET_MODULE(swr_metadata_production)
}
