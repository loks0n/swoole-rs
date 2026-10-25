// Normal bounded storage callers; actual noninline methods resolve from Swoole.
extern "C" {
#include <php.h>
#include <Zend/zend_exceptions.h>
}
#include "swoole_string.h"
#include "swoole_buffer.h"
#include <dlfcn.h>
#include <exception>
#include <vector>

static const char *origin(const char *name) {
    Dl_info image{};
    void *method = dlsym(RTLD_DEFAULT, name);
    return method && dladdr(method, &image) ? image.dli_fname : nullptr;
}
static void snapshot(zval *rows, const char *name, const swoole::String &value) {
    zval row;
    array_init(&row);
    add_assoc_stringl(&row, "bytes", value.str ? value.str : "", value.length);
    add_assoc_long(&row, "length", value.length);
    add_assoc_long(&row, "capacity", value.size);
    add_assoc_long(&row, "offset", value.offset);
    add_assoc_bool(&row, "owner_null", value.str == nullptr);
    add_assoc_zval(rows, name, &row);
}
ZEND_BEGIN_ARG_WITH_RETURN_TYPE_INFO_EX(arginfo_swr_storage_production, 0, 0, IS_ARRAY, 0)
ZEND_END_ARG_INFO()
PHP_FUNCTION(swr_storage_production) {
    ZEND_PARSE_PARAMETERS_NONE();
    array_init(return_value);
    const char *buffer_image = origin("_ZN6swoole6Buffer6appendEPKcj");
    const char *string_image = origin("_ZN6swoole6String6appendEPKcm");
    if (!buffer_image || !string_image) {
        zend_throw_exception(zend_ce_exception, "Production storage methods unavailable", 0);
        return;
    }
    add_assoc_string(return_value, "method_image", const_cast<char *>(buffer_image));
    add_assoc_string(return_value, "string_image", const_cast<char *>(string_image));
    try {
        zval strings;
        array_init(&strings);
        swoole::String value(64);
        value.append("a\0b", 3);
        value.append(-42);
        snapshot(&strings, "append", value);
        value.write(1, "xy", 2);
        value.repeat("Q!", 2, 3);
        snapshot(&strings, "write_repeat", value);
        value.offset = 2;
        value.reduce(2);
        snapshot(&strings, "reduce", value);
        const size_t old_length = value.length;
        value.offset = 2;
        char *detached = value.pop(32);
        if (!detached) throw std::bad_alloc();
        add_assoc_stringl(&strings, "detached", detached, old_length);
        value.allocator->free(detached);
        snapshot(&strings, "pop", value);
        swoole::String copied(value);
        copied.append('Z');
        snapshot(&strings, "copied", copied);
        snapshot(&strings, "copy_source", value);
        swoole::String moved(std::move(copied));
        snapshot(&strings, "moved", moved);
        snapshot(&strings, "move_source", copied);
        moved.format("n=%d/%s", 7, "x");
        moved.append_format("|%02d", 3);
        snapshot(&strings, "format", moved);
        swoole::String frames("aa|bb|", 6);
        std::vector<std::string> pieces;
        const ssize_t consumed = frames.split("|", 1, [&](const char *data, size_t size) {
            pieces.emplace_back(data, size);
            return true;
        });
        zval split;
        array_init(&split);
        for (const auto &piece : pieces) add_next_index_stringl(&split, piece.data(), piece.size());
        add_assoc_zval(&strings, "split", &split);
        add_assoc_long(&strings, "split_consumed", consumed);
        add_assoc_long(&strings, "split_offset", frames.offset);
        add_assoc_zval(return_value, "strings", &strings);

        zval buffers;
        array_init(&buffers);
        swoole::Buffer buffer(4);
        buffer.append("0123\0abcd", 9);
        swoole::BufferChunk *first = buffer.front();
        first->offset = 2;
        buffer.append("XY", 2);
        add_assoc_bool(&buffers, "front_stable", first == buffer.front());
        add_assoc_long(&buffers, "front_offset", buffer.front()->offset);
        add_assoc_long(&buffers, "before_length", buffer.length());
        add_assoc_long(&buffers, "before_count", buffer.count());
        std::string joined;
        zval lengths;
        array_init(&lengths);
        while (!buffer.empty()) {
            const auto *front = buffer.front();
            joined.append(front->value.str + front->offset, front->length - front->offset);
            buffer.pop();
            add_next_index_long(&lengths, buffer.length());
        }
        add_assoc_stringl(&buffers, "drained", joined.data(), joined.size());
        add_assoc_zval(&buffers, "lengths_after_pop", &lengths);
        add_assoc_long(&buffers, "final_count", buffer.count());
        char left[] = {'a', '\0', 'b'};
        char right[] = {'c', 'd', 'e', 'f', 'g'};
        const iovec parts[] = {{left, sizeof(left)}, {right, sizeof(right)}};
        buffer.append(parts, 2, 0); // Positive descriptors, offset0; no corrected edge.
        add_assoc_long(&buffers, "vector_length", buffer.length());
        add_assoc_long(&buffers, "vector_count", buffer.count());
        joined.clear();
        while (!buffer.empty()) {
            const auto *front = buffer.front();
            joined.append(front->value.str, front->length);
            buffer.pop();
        }
        add_assoc_stringl(&buffers, "vector_bytes", joined.data(), joined.size());
        add_assoc_long(&buffers, "vector_final_length", buffer.length());
        add_assoc_zval(return_value, "buffers", &buffers);
    } catch (const std::exception &error) {
        zend_throw_exception(zend_ce_exception, error.what(), 0);
    }
}
static const zend_function_entry storage_functions[] = {
    PHP_FE(swr_storage_production, arginfo_swr_storage_production)
    PHP_FE_END
};
extern "C" {
zend_module_entry swr_storage_production_module_entry = {
    STANDARD_MODULE_HEADER, "swr_storage_production", storage_functions,
    nullptr, nullptr, nullptr, nullptr, nullptr, "1", STANDARD_MODULE_PROPERTIES
};
ZEND_GET_MODULE(swr_storage_production)
}
