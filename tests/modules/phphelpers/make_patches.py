"""Regenerate reserved overlays from exact pinned sources; no upstream edits."""
from pathlib import Path
import difflib, hashlib, json, subprocess, sys
ROOT=Path(__file__).resolve().parents[3]
PIN='8e8c49915ca5f9dcb9ee654f9e336a9c88dd375e'
source=Path(sys.argv[1])

def guard(selected, original):
    return '#ifdef SWOOLE_RS_PHPHELPERS\n'+selected+'\n#else\n'+original+'\n#endif'

def original(name):
    return subprocess.check_output(['git','-C',str(source),'show',PIN+':'+name],text=True)

cxx=original('ext-src/php_swoole_cxx.cc')
candidate=cxx.replace('#include "php_swoole_cxx.h"','#include "php_swoole_cxx.h"\n#ifdef SWOOLE_RS_PHPHELPERS\n#include "swoole_rs_phphelpers.h"\nstatic_assert(SUCCESS == 0, "Zend SUCCESS ABI");\n#endif')
a=candidate.index('static const char *sw_known_strings[]');b=candidate.index('SW_API zend_string **sw_zend_known_strings',a)
candidate=candidate[:a]+guard('',candidate[a:b].rstrip())+'\n\n'+candidate[b:]
a=candidate.index('void known_strings_init() {');start=candidate.index('{',a)+1;end=candidate.index('\n}',start);old=candidate[start:end]
new='''    sw_zend_known_strings = static_cast<zend_string **>(pemalloc(sizeof(zend_string *) * swr_v1_phphelpers_known_count(), 1));
    size_t cursor = 0, length = 0;
    const char *name;
    while ((name = swr_v1_phphelpers_known_next(&cursor, &length)) != nullptr) {
        zend_string *str = zend_string_init(name, length, true);
        sw_zend_known_strings[cursor - 1] = zend_new_interned_string(str);
    }'''
candidate=candidate[:start]+'\n'+guard(new,old.strip('\n'))+'\n'+candidate[end:]
a=candidate.index('Callable::~Callable() {');start=candidate.index('{',a)+1;end=candidate.index('\n}',start);old=candidate[start:end]
new='''    uint32_t phase = 0;
    bool observation = false;
    for (;;) {
        switch (swr_v1_phphelpers_release(&phase, observation)) {
        case SWR_PHP_RELEASE_OBSERVE_VALUE: observation = !ZVAL_IS_UNDEF(&zfn); break;
        case SWR_PHP_RELEASE_VALUE: zval_ptr_dtor(&zfn); break;
        case SWR_PHP_RELEASE_OBSERVE_NAME: observation = fn_name != nullptr; break;
        case SWR_PHP_RELEASE_NAME: efree(fn_name); break;
        default: return;
        }
    }'''
candidate=candidate[:start]+'\n'+guard(new,old.strip('\n'))+'\n'+candidate[end:]
a=candidate.index('static zend_always_inline zval *sw_zend_symtable_str_add(')
b=candidate.index('\nvoid array_add_or_merge(',a)
candidate=candidate[:a]+'#ifndef SWOOLE_RS_PHPHELPERS\n'+candidate[a:b]+'#endif\n'+candidate[b:]
a=candidate.index('    zval *zresult = sw_zend_symtable_str_add(');b=candidate.index('\n}\n\nnamespace function',a)
old=candidate[a:b]
new='''    uint32_t phase = 0;
    bool inserted = false, existing_array = false;
    zval *current_elements = nullptr;
    for (;;) {
        const auto action = swr_v1_phphelpers_merge_keyed(&phase, inserted, existing_array, numeric_key);
        switch (action) {
        case SWR_PHP_KEYED_ADD_INDEX:
            inserted = zend_hash_index_add(array, idx, new_element) != nullptr;
            break;
        case SWR_PHP_KEYED_ADD_STRING:
            inserted = zend_hash_str_add(array, key, key_len, new_element) != nullptr;
            break;
        case SWR_PHP_KEYED_FIND_INDEX:
            current_elements = zend_hash_index_find(array, idx);
            existing_array = ZVAL_IS_ARRAY(current_elements);
            break;
        case SWR_PHP_KEYED_FIND_STRING:
            current_elements = zend_hash_str_find(array, key, key_len);
            existing_array = ZVAL_IS_ARRAY(current_elements);
            break;
        case SWR_PHP_KEYED_APPEND:
            add_next_index_zval(current_elements, new_element);
            return;
        case SWR_PHP_KEYED_PROMOTE_INDEX:
        case SWR_PHP_KEYED_PROMOTE_STRING: {
            zval zvalue_array;
            array_init_size(&zvalue_array, 2);
            Z_ADDREF_P(current_elements);
            add_next_index_zval(&zvalue_array, current_elements);
            add_next_index_zval(&zvalue_array, new_element);
            if (action == SWR_PHP_KEYED_PROMOTE_INDEX) {
                zend_hash_index_update(array, idx, &zvalue_array);
            } else {
                zend_hash_str_update(array, key, key_len, &zvalue_array);
            }
            return;
        }
        default:
            return;
        }
    }'''
candidate=candidate[:a]+guard(new,old)+candidate[b:]
# An opaque Rust effect tag no longer proves numeric initialization to C++.
# Initialize the unpublished scratch; native key classification/read order stays.
a=candidate.index('    zend_ulong idx;',candidate.index('void array_add_or_merge('))
candidate=candidate[:a]+guard('    zend_ulong idx = 0;','    zend_ulong idx;')+candidate[a+len('    zend_ulong idx;'):]
a=candidate.index('    bool success;',candidate.index('bool call('));b=candidate.index('\n}',a);old=candidate[a:b]
new='''    uint32_t phase = 0;
    int64_t result = 0;
    bool pending_exception = false;
    const uint32_t mode = enable_coroutine ? 1 : 0;
    for (;;) {
        switch (swr_v1_phphelpers_call_plan(&phase, mode, retval != nullptr, result, pending_exception)) {
        case SWR_PHP_CALL_NULL:
            ZVAL_NULL(retval);
            break;
        case SWR_PHP_CALL_DIRECT:
            result = sw_zend_call_function_ex(nullptr, fci_cache, argc, argv, retval);
            break;
        case SWR_PHP_CALL_COROUTINE:
            result = swoole::PHPCoroutine::create(fci_cache, argc, argv, nullptr);
            break;
        case SWR_PHP_CALL_OBSERVE_EXCEPTION:
            pending_exception = EG(exception) != nullptr;
            break;
        case SWR_PHP_CALL_FATAL:
            zend_exception_error(EG(exception), E_ERROR);
            break;
        case SWR_PHP_CALL_TRUE:
            return true;
        default:
            return false;
        }
    }'''
candidate=candidate[:a]+guard(new,old)+candidate[b:]
a=candidate.index('    if (call_user_function(',candidate.index('Variable call('));b=candidate.index('\n}',a);old=candidate[a:b]
new='''    uint32_t phase = 0;
    int64_t result = 0;
    bool pending_exception = false;
    for (;;) {
        switch (swr_v1_phphelpers_call_plan(&phase, 2, 1, result, pending_exception)) {
        case SWR_PHP_CALL_NAMED:
            result = call_user_function(EG(function_table), nullptr, &function_name, &retval.value, argc, argv);
            break;
        case SWR_PHP_CALL_NULL:
            ZVAL_NULL(&retval.value);
            break;
        case SWR_PHP_CALL_RELEASE_NAME:
            zval_dtor(&function_name);
            break;
        case SWR_PHP_CALL_OBSERVE_EXCEPTION:
            pending_exception = EG(exception) != nullptr;
            break;
        case SWR_PHP_CALL_FATAL:
            zend_exception_error(EG(exception), E_ERROR);
            break;
        default:
            return retval;
        }
    }'''
candidate=candidate[:a]+guard(new,old)+candidate[b:]
a=candidate.index('    if (!zval_is_true(_zfn))');b=candidate.index('\n}\n\nCallable::~Callable',a);old=candidate[a:b]
new='''    uint32_t phase = 0;
    bool truthy = false, valid = false;
    for (;;) {
        switch (swr_v1_phphelpers_callable(&phase, truthy, valid)) {
        case SWR_PHP_CALLABLE_TRUTH:
            truthy = zval_is_true(_zfn);
            break;
        case SWR_PHP_CALLABLE_CHECK:
            valid = sw_zend_is_callable_ex(_zfn, nullptr, 0, &fn_name, nullptr, &fcc, nullptr);
            break;
        case SWR_PHP_CALLABLE_ILLEGAL:
            php_swoole_fatal_error(E_WARNING, "illegal callback function");
            return;
        case SWR_PHP_CALLABLE_INVALID:
            php_swoole_fatal_error(E_WARNING, "function '%s' is not callable", fn_name);
            return;
        case SWR_PHP_CALLABLE_RETAIN:
            zfn = *_zfn;
            zval_add_ref(&zfn);
            return;
        default:
            return;
        }
    }'''
candidate=candidate[:a]+guard(new,old)+candidate[b:]

std=original('ext-src/swoole_stdext.cc')
modified=std.replace('#include "php_variables.h"','#include "php_variables.h"\n#ifdef SWOOLE_RS_PHPHELPERS\n#include "swoole_rs_phphelpers.h"\n#include <type_traits>\nstatic_assert(std::is_trivially_copyable<zval>::value, "Zend argument copy requires trivial zval representation");\nstatic uint32_t phphelpers_kind(uint8_t type) {\n    switch (type) {\n    case IS_UNDEF: return SWR_PHP_UNDEF;\n    case IS_NULL: return SWR_PHP_NULL;\n    case IS_TRUE: case IS_FALSE: return SWR_PHP_BOOL;\n    case IS_LONG: return SWR_PHP_LONG;\n    case IS_DOUBLE: return SWR_PHP_DOUBLE;\n    case IS_STRING: return SWR_PHP_STRING;\n    case IS_ARRAY: return SWR_PHP_ARRAY;\n    case IS_OBJECT: return SWR_PHP_OBJECT;\n    case IS_RESOURCE: return SWR_PHP_RESOURCE;\n    default: return SWR_PHP_OTHER;\n    }\n}\n#endif')
old='''        return self.type_of_key == other->self.type_of_key && self.type_of_value == other->self.type_of_value &&
               len_of_type_str == other->len_of_type_str && memcmp(type_str, other->type_str, len_of_type_str) == 0;'''
new='''        return swr_v1_phphelpers_type_equal(self.type_of_key, self.type_of_value, other->self.type_of_key,
                                            other->self.type_of_value, reinterpret_cast<const uint8_t *>(type_str),
                                            len_of_type_str, reinterpret_cast<const uint8_t *>(other->type_str), other->len_of_type_str);'''
assert old in modified;modified=modified.replace(old,guard(new,old))
old='''        return element_array_type_info->get_type_of_key() == element.type_of_key &&
               element_array_type_info->get_type_of_value() == element.type_of_value &&
               element_array_type_info->len_of_type_str == get_len_of_value_type_str() &&
               memcmp(element_array_type_info->type_str, get_value_type_str(), get_len_of_value_type_str()) == 0;'''
new='''        return swr_v1_phphelpers_type_equal(element_array_type_info->get_type_of_key(), element_array_type_info->get_type_of_value(),
                                            element.type_of_key, element.type_of_value,
                                            reinterpret_cast<const uint8_t *>(element_array_type_info->type_str), element_array_type_info->len_of_type_str,
                                            reinterpret_cast<const uint8_t *>(get_value_type_str()), get_len_of_value_type_str());'''
assert old in modified;modified=modified.replace(old,guard(new,old))
a=modified.index('static std::unordered_map<std::string, std::string> array_methods');b=modified.index('\nstatic void move_first_element',a)
modified=modified[:a]+guard('static constexpr uint32_t array_methods = 0, string_methods = 1, stream_methods = 2;',modified[a:b].rstrip())+'\n'+modified[b:]
a=modified.index('    zval first = src[0];',modified.index('static void move_first_element'));b=modified.index('\n}',a);old=modified[a:b]
new='''    SwrPhpArgumentPlan plan;
    if (swr_v1_phphelpers_arguments(size, position, &plan)) {
        zval first = src[0];
        memcpy(dst, src + 1, static_cast<size_t>(plan.head) * sizeof(zval));
        dst[plan.head] = first;
        memcpy(dst + plan.tail_begin, src + plan.tail_begin, static_cast<size_t>(plan.tail_count) * sizeof(zval));
        return;
    }'''
# Retain the original code as the fallback for its existing out-of-contract domain.
modified=modified[:a]+'#ifdef SWOOLE_RS_PHPHELPERS\n'+new+'\n#endif\n'+old+modified[b:]
a=modified.index('static void call_func_move_first_arg(');b=modified.index('static void call_method(',a);old=modified[a:b].rstrip()
new='''static void call_func_move_first_arg(zend_function *fn, zend_execute_data *execute_data, zval *retval, int position) {
    uint32_t phase = 0;
    const zval *arg_ptr = nullptr;
    int arg_count = 0;
    zval *argv = nullptr;
    for (;;) {
        switch (swr_v1_phphelpers_invoke(&phase, 1, 0)) {
        case SWR_PHP_INVOKE_ARGUMENTS:
            arg_ptr = ZEND_CALL_ARG(execute_data, 1);
            arg_count = ZEND_CALL_NUM_ARGS(execute_data);
            break;
        case SWR_PHP_INVOKE_ALLOCATE:
            argv = static_cast<zval *>(ecalloc(arg_count, sizeof(zval)));
            break;
        case SWR_PHP_INVOKE_REORDER:
            move_first_element(arg_ptr, argv, arg_count, position);
            break;
        case SWR_PHP_INVOKE_CALL:
            zend_call_known_function(fn, nullptr, nullptr, retval, arg_count, argv, nullptr);
            break;
        case SWR_PHP_INVOKE_RELEASE_ARGUMENTS:
            efree(argv);
            break;
        default:
            return;
        }
    }
}'''
modified=modified[:a]+guard(new,old)+'\n\n'+modified[b:]
a=modified.index('static void call_method(');b=modified.index('static int opcode_handler_method_call(zend_execute_data *execute_data) {',a);old=modified[a:b].rstrip()
new='''static void call_method(const uint32_t method_map, zend_execute_data *execute_data, zval *retval) {
    const auto call_info = reinterpret_cast<CallInfo *>(execute_data->run_time_cache);
    const auto name = std::string(Z_STRVAL(call_info->func), Z_STRLEN(call_info->func));
    size_t alias_length = 0;
    const char *alias = swr_v1_phphelpers_alias(method_map, reinterpret_cast<const uint8_t *>(name.data()), name.size(), &alias_length);
    uint32_t phase = 0;

    ON_SCOPE_EXIT {
        efree(call_info);
        execute_data->run_time_cache = nullptr;
    };

    if (swr_v1_phphelpers_invoke(&phase, 0, alias != nullptr) == SWR_PHP_INVOKE_UNKNOWN_METHOD) {
        zend_throw_error(nullptr, "The method `%s` is undefined on %s", name.c_str(), zend_zval_type_name(&call_info->this_));
        return;
    }
    // Keep the original lexical string/guard lifetime; no optional/new heap owner.
    const auto real_fn = std::string(alias, alias_length);
    const auto fn = zend::get_function(real_fn.c_str(), real_fn.length());
    const zval *arg_ptr = nullptr;
    int arg_count = 0;
    zval *argv = nullptr;
    bool observation = fn != nullptr;
    for (;;) {
        switch (swr_v1_phphelpers_invoke(&phase, 0, observation)) {
        case SWR_PHP_INVOKE_UNKNOWN_FUNCTION:
            zend_throw_error(nullptr, "The function `%s` is undefined", real_fn.c_str());
            return;
        case SWR_PHP_INVOKE_ARGUMENTS:
            arg_ptr = ZEND_CALL_ARG(execute_data, 1);
            arg_count = ZEND_CALL_NUM_ARGS(execute_data);
            break;
        case SWR_PHP_INVOKE_ALLOCATE:
            argv = static_cast<zval *>(ecalloc(arg_count + 1, sizeof(zval)));
            break;
        case SWR_PHP_INVOKE_COPY:
            argv[0] = call_info->this_;
            memcpy(argv + 1, arg_ptr, static_cast<size_t>(arg_count) * sizeof(zval));
            break;
        case SWR_PHP_INVOKE_CALL:
            zend_call_known_function(fn, nullptr, nullptr, retval, arg_count + 1, argv, nullptr);
            break;
        case SWR_PHP_INVOKE_OBSERVE:
            observation = call_info->op1_type == IS_VAR;
            break;
        case SWR_PHP_INVOKE_RELEASE_THIS:
            zval_ptr_dtor(&call_info->this_);
            break;
        case SWR_PHP_INVOKE_RELEASE_ARGUMENTS:
            efree(argv);
            break;
        default:
            return;
        }
    }
}'''
modified=modified[:a]+guard(new,old)+'\n\n'+modified[b:]
# Native allocation remains first and native string publication remains last.
old='    char *p = result->val;'
new='''#ifdef SWOOLE_RS_PHPHELPERS
    size_t projected_length;
    if (swr_v1_phphelpers_definition(phphelpers_kind(info->get_type_of_key()),
                                    reinterpret_cast<const uint8_t *>(info->get_value_type_str()),
                                    info->get_len_of_value_type_str(), reinterpret_cast<uint8_t *>(result->val),
                                    static_cast<size_t>(info->get_len_of_value_type_str()) + 17, &projected_length)) {
        result->len = projected_length;
        return result;
    }
#endif
    char *p = result->val;'''
assert old in modified;modified=modified.replace(old,new)
a=modified.index('    if (get_type_of_key() > 0)',modified.index('bool ArrayTypeInfo::check'));b=modified.index('    ZVAL_DEREF(value);',a);old=modified[a:b].rstrip()
new='''    const uint32_t key_kind = phphelpers_kind(Z_TYPE_P(key));
    auto decision = swr_v1_phphelpers_key_route(phphelpers_kind(get_type_of_key()), key_kind);
    if (decision == SWR_PHP_KEY_OBSERVE_INDEX) {
        decision = swr_v1_phphelpers_key(SWR_PHP_UNDEF, SWR_PHP_LONG, Z_LVAL_P(key), zend_hash_num_elements(ht));
    }
    switch (decision) {
    case SWR_PHP_KEY_TYPE:
        zend_type_error("Array key type mismatch, expected `%s`, got `%s`",
                        zend_get_type_by_const(get_type_of_key()), zend_get_type_by_const(Z_TYPE_P(key)));
        return false;
    case SWR_PHP_KEY_RANGE:
        zend_throw_error(nullptr, "Incorrect array key `%ld`, out of the permitted range", (long) Z_LVAL_P(key));
        return false;
    case SWR_PHP_KEY_INVALID:
        zend_throw_error(nullptr, "Incorrect array key, must be undef or int");
        return false;
    default:
        break;
    }'''
modified=modified[:a]+guard(new,old)+'\n'+modified[b:]
# Additional bounded typed-definition and operation policy. Zend lowercasing,
# allocation/class lookup/error construction/opcode execution remain native.
marker='    default: return SWR_PHP_OTHER;\n    }\n}\n#endif'
replacement='    default: return SWR_PHP_OTHER;\n    }\n}\nstatic uint8_t phphelpers_zend_kind(uint32_t kind) {\n    switch (kind) {\n    case SWR_PHP_UNDEF: return IS_UNDEF;\n    case SWR_PHP_NULL: return IS_NULL;\n    case SWR_PHP_BOOL: return IS_TRUE;\n    case SWR_PHP_LONG: return IS_LONG;\n    case SWR_PHP_DOUBLE: return IS_DOUBLE;\n    case SWR_PHP_STRING: return IS_STRING;\n    case SWR_PHP_ARRAY: return IS_ARRAY;\n    case SWR_PHP_RESOURCE: return IS_RESOURCE;\n    default: return IS_OBJECT;\n    }\n}\n#endif'
assert marker in modified;modified=modified.replace(marker,replacement)
a=modified.index('    if (!*val || *len == 0)',modified.index('static void remove_all_spaces'));b=modified.index('\n}\n\nstatic int8_t get_type',a);old=modified[a:b]
new='    if (!*val || *len == 0) return;\n    *len = static_cast<uint16_t>(swr_v1_phphelpers_compact(reinterpret_cast<uint8_t *>(*val), *len));'
modified=modified[:a]+guard(new,old)+modified[b:]
a=modified.index('    auto pos = strchr(type_str',modified.index('bool ArrayTypeValue::parse'));b=modified.index('\n}',a);old=modified[a:b]
new='    SwrPhpTypeLayout layout;\n    const size_t prefix = strlen(type_str);\n    const size_t initialized = (prefix > len_of_type_str ? prefix : len_of_type_str) + 1;\n    const auto result = swr_v1_phphelpers_type_span(reinterpret_cast<const uint8_t *>(type_str),\n                                                     initialized, static_cast<uint16_t>(len_of_type_str), &layout);\n    if (result) {\n        type_of_key = phphelpers_zend_kind(layout.key);\n        if (result == 2) {\n            zend_throw_error(nullptr, "The key type of array must be string or int, but got %s", type_str + layout.offset);\n            return false;\n        }\n        offset_of_value_type_str = layout.offset;\n        len_of_value_type_str = layout.length;\n        type_of_value = phphelpers_zend_kind(layout.value);\n        return true;\n    }'
modified=modified[:a]+'#ifdef SWOOLE_RS_PHPHELPERS\n'+new+'\n#endif\n'+old+modified[b:]
a=modified.index('static int opcode_handler_method_call(zend_execute_data *execute_data) {')
b=modified.index('void php_swoole_stdext_minit(',a)
old=std[std.index('static int opcode_handler_method_call(zend_execute_data *execute_data) {'):std.index('void php_swoole_stdext_minit(')].rstrip()
new='''static int opcode_handler_method_call(zend_execute_data *execute_data) {
    const zend_op *opline = EX(opline);
    const uint32_t operand = opline->op1_type == IS_CONST ? 0 : opline->op1_type == IS_UNUSED ? 1 : 2;
    SwrPhpMethodState state{0, 0};
    uint32_t observation = 0;
    zval *object = nullptr;
    CallInfo *call_info = nullptr;
    zend_execute_data *call = nullptr;
    for (;;) {
        switch (swr_v1_phphelpers_method_frame(&state, operand, observation)) {
        case SWR_PHP_METHOD_CONSTANT:
            object = RT_CONSTANT(opline, opline->op1);
            break;
        case SWR_PHP_METHOD_VARIABLE:
            object = EX_VAR(opline->op1.var);
            break;
        case SWR_PHP_METHOD_OBSERVE: {
            const auto type = Z_TYPE_P(object);
            observation = type == IS_REFERENCE ? 10 : phphelpers_kind(type);
            break;
        }
        case SWR_PHP_METHOD_REFERENCE:
            observation = phphelpers_kind(Z_TYPE_P(Z_REFVAL_P(object)));
            break;
        case SWR_PHP_METHOD_ALLOCATE:
            call_info = static_cast<CallInfo *>(emalloc(sizeof(CallInfo)));
            break;
        case SWR_PHP_METHOD_FILL:
            call_info->func = *RT_CONSTANT(opline, opline->op2);
            call_info->this_ = *object;
            call_info->op1_type = opline->op1_type;
            break;
        case SWR_PHP_METHOD_ARRAY:
            call = zend_vm_stack_push_call_frame(ZEND_CALL_NESTED_FUNCTION, fn_swoole_call_array_method, opline->extended_value, object);
            break;
        case SWR_PHP_METHOD_STRING:
            call = zend_vm_stack_push_call_frame(ZEND_CALL_NESTED_FUNCTION, fn_swoole_call_string_method, opline->extended_value, object);
            break;
        case SWR_PHP_METHOD_STREAM:
            call = zend_vm_stack_push_call_frame(ZEND_CALL_NESTED_FUNCTION, fn_swoole_call_stream_method, opline->extended_value, object);
            break;
        case SWR_PHP_METHOD_PUBLISH:
            call->run_time_cache = reinterpret_cast<void **>(call_info);
            call->prev_execute_data = EX(call);
            EX(call) = call;
            EX(opline)++;
            break;
        case SWR_PHP_METHOD_CONTINUE:
            return ZEND_USER_OPCODE_CONTINUE;
        default:
            return ZEND_USER_OPCODE_DISPATCH;
        }
    }
}'''
modified=modified[:a]+guard(new,old)+'\n\n'+modified[b:]
# Whole typed VM facade replaces the old partial branch guards as one policy.
helper='''#ifdef SWOOLE_RS_PHPHELPERS
static int phphelpers_vm(zend_execute_data *execute_data, uint32_t operation, const ArrayFn *fn) {
    const zend_op *opline = EX(opline);
    const zend_op *op_data = nullptr;
    zval *array = nullptr, *key = nullptr, *value = nullptr;
    zend_array *ht = nullptr;
    uint32_t phase = 0;
    const uint32_t operand = opline->op1_type == IS_VAR || opline->op1_type == IS_CV ? 1 :
                             opline->op1_type == IS_CONST ? 2 : 0;
    uint32_t key_kind = 0;
    bool observation = false;
    for (;;) {
        switch (swr_v1_phphelpers_vm(&phase, operation, operand, key_kind, observation)) {
        case SWR_PHP_VM_ARRAY:
            array = get_array_on_opline(opline EXECUTE_DATA_CC);
            break;
        case SWR_PHP_VM_VARIABLE:
            array = _get_zval_ptr_ptr_var(opline->op1.var EXECUTE_DATA_CC);
            break;
        case SWR_PHP_VM_CONSTANT:
            array = RT_CONSTANT(opline, opline->op1);
            break;
        case SWR_PHP_VM_TEMPORARY:
            array = _get_zval_ptr_tmp(opline->op1.var EXECUTE_DATA_CC);
            break;
        case SWR_PHP_VM_DEREFERENCE:
            ZVAL_DEREF(array);
            break;
        case SWR_PHP_VM_OBSERVE_ARRAY:
            observation = array && ZVAL_IS_ARRAY(array);
            break;
        case SWR_PHP_VM_OBSERVE_TYPED:
            ht = Z_ARRVAL_P(array);
            observation = (HT_FLAGS(ht) & HASH_FLAG_TYPED_ARRAY) != 0;
            break;
        case SWR_PHP_VM_VALUE:
            op_data = opline + 1;
            value = get_op_data_zval_ptr_r(op_data->op1_type, op_data->op1);
            key_kind = opline->op2_type == IS_CONST ? 0 : opline->op2_type == IS_UNUSED ? 1 : 2;
            break;
        case SWR_PHP_VM_CONSTANT_KEY:
            key = RT_CONSTANT(opline, opline->op2);
            break;
        case SWR_PHP_VM_UNUSED_KEY:
            key = &EG(uninitialized_zval);
            break;
        case SWR_PHP_VM_VARIABLE_KEY:
            key = EX_VAR(opline->op2.var);
            break;
        case SWR_PHP_VM_CHECK:
            observation = get_type_info(ht)->check(ht, key, value);
            break;
        case SWR_PHP_VM_INVOKE:
            (*fn)(opline, array, key, value EXECUTE_DATA_CC);
            break;
        case SWR_PHP_VM_FREE:
            FREE_OP(op_data->op1_type, op_data->op1.var);
            break;
        case SWR_PHP_VM_ADVANCE:
            EX(opline) += 2;
            break;
        case SWR_PHP_VM_LIST:
            observation = get_type_info(ht)->is_list();
            break;
        case SWR_PHP_VM_REFERENCE_ERROR:
            zend_throw_error(nullptr, "The type array do not support using references for element value during iteration");
            ZVAL_UNDEF(EX_VAR(opline->result.var));
            Z_FE_ITER_P(EX_VAR(opline->result.var)) = static_cast<uint32_t>(-1);
            break;
        case SWR_PHP_VM_LIST_ERROR:
            zend_throw_error(nullptr, "The typed array list do not support random deletion of elements");
            break;
        case SWR_PHP_VM_CONTINUE:
            return ZEND_USER_OPCODE_CONTINUE;
        default:
            return ZEND_USER_OPCODE_DISPATCH;
        }
    }
}
#endif
'''
for signature,next_signature,operation in [
    ('static int opcode_handler_array(zend_execute_data *execute_data, const ArrayFn &fn)', 'static int opcode_handler_array_assign(',0),
    ('static int opcode_handler_foreach_begin(zend_execute_data *execute_data) {','static int opcode_handler_array_unset(zend_execute_data *execute_data) {',1),
    ('static int opcode_handler_array_unset(zend_execute_data *execute_data) {','static void remove_all_spaces(',2)]:
    a=modified.index(signature);b=modified.index(next_signature,a);old=modified[a:b].rstrip()
    head=old[:old.index('{')+1]
    new=head+'\n    return phphelpers_vm(execute_data, '+str(operation)+(', &fn);' if operation==0 else ', nullptr);')+'\n}'
    modified=modified[:a]+guard(new,old)+'\n\n'+modified[b:]
a=modified.index('static int opcode_handler_array(zend_execute_data *execute_data, const ArrayFn &fn)')
# Insert before its whole-body selected guard, preserving the original alias scope.
a=modified.rfind('#ifdef SWOOLE_RS_PHPHELPERS',0,a)
modified=modified[:a]+helper+'\n'+modified[a:]
a=modified.index('    if (assoc)',modified.index('static void php_do_json_decode'));b=modified.index('\n\n    zend::json_decode',a);old=modified[a:b]
new='    options = swr_v1_phphelpers_json_options(options, PHP_JSON_OBJECT_AS_ARRAY, assoc);'
modified=modified[:a]+guard(new,old)+modified[b:]

# Complete lazy scalar/object/nested-array validation policy. Every Zend effect
# runs after the Rust step returns, including diagnostic allocation/release.
a=modified.index('    ZVAL_DEREF(value);',modified.index('bool ArrayTypeInfo::check'))
b=modified.index('\n}\n\nstatic zval *get_array_on_opline',a)
old=std[std.index('    ZVAL_DEREF(value);',std.index('bool ArrayTypeInfo::check')):std.index('\n}\n\nstatic zval *get_array_on_opline')]
new='''    ZVAL_DEREF(value);
    uint32_t phase = 0;
    bool observation = false;
    const ArrayTypeInfo *element_info = nullptr;
    for (;;) {
        switch (swr_v1_phphelpers_validate_value(&phase, phphelpers_kind(get_type_of_value()),
                                                phphelpers_kind(Z_TYPE_P(value)), observation)) {
        case SWR_PHP_VALIDATE_DONE:
            return true;
        case SWR_PHP_VALIDATE_TYPE:
            zend_type_error("Array value type mismatch, expected `%s`, got `%s`",
                            zend_get_type_by_const(get_type_of_value()), zend_get_type_by_const(Z_TYPE_P(value)));
            return false;
        case SWR_PHP_VALIDATE_INSTANCE:
            observation = instance_of(value);
            break;
        case SWR_PHP_VALIDATE_OBJECT:
            zend_type_error("Array value type mismatch, expected `%s`, got `%s`",
                            value_ce->name->val, Z_OBJCE_P(value)->name->val);
            return false;
        case SWR_PHP_VALIDATE_ARRAY: {
            element_info = get_type_info(Z_ARRVAL_P(value));
            const auto element_ht = Z_ARRVAL_P(value);
            observation = (HT_FLAGS(element_ht) & HASH_FLAG_TYPED_ARRAY) != 0;
            break;
        }
        case SWR_PHP_VALIDATE_PLAIN_ARRAY:
            zend_type_error("Array value type mismatch, expected `%.*s`, got `array`",
                            get_len_of_value_type_str(), get_value_type_str());
            return false;
        case SWR_PHP_VALIDATE_COMPARE:
            observation = element_type_equals(element_info);
            break;
        case SWR_PHP_VALIDATE_ARRAY_TYPE: {
            const auto definition = get_array_type_def(element_info);
            zend_type_error("Array value type mismatch, expected `%.*s`, got `%.*s`",
                            get_len_of_value_type_str(), get_value_type_str(),
                            (int) ZSTR_LEN(definition), ZSTR_VAL(definition));
            zend_string_release(definition);
            return false;
        }
        }
    }'''
modified=modified[:a]+guard(new,old)+modified[b:]

# One lazy mutation plan owns both assignment/compound-op branch workflows.
# Native stack variables keep authoritative Zend storage and no native effect
# executes with a Rust frame or borrowed pointer alive.
helper='''static void phphelpers_mutate(const zend_op *opline, zval *container, const zval *key,
                              zval *value EXECUTE_DATA_DC, uint32_t operation) {
    HashTable *source = Z_ARRVAL_P(container);
    SEPARATE_ARRAY(container);
    uint32_t phase = 0, observation = source != Z_ARRVAL_P(container);
    HashTable *ht = nullptr;
    const ArrayTypeInfo *type_info = nullptr;
    const zend_op *op_data = nullptr;
    zval *var_ptr = nullptr, *variable_ptr = nullptr;
    zend_reference *reference = nullptr;
    for (;;) {
        switch (swr_v1_phphelpers_mutation(&phase, operation, observation)) {
        case SWR_PHP_MUTATION_DONE:
            return;
        case SWR_PHP_MUTATION_COPY_METADATA:
            copy_array_type_info(container, source);
            break;
        case SWR_PHP_MUTATION_ROUTE:
            if (operation == 0) {
                ht = Z_ARRVAL_P(container);
                op_data = opline + 1;
                observation = ZVAL_IS_NULL(key) ? 1 : (opline->op2_type == IS_CONST ? 2 : 3);
            } else {
                type_info = get_type_info(Z_ARRVAL_P(container));
                observation = (opline + 1)->op1_type == IS_CONST ? 2 : 3;
            }
            break;
        case SWR_PHP_MUTATION_INSERT:
            var_ptr = zend_hash_next_index_insert(ht, value);
            observation = var_ptr != nullptr;
            break;
        case SWR_PHP_MUTATION_FETCH_W_CONST:
            variable_ptr = zend_fetch_dimension_address_inner_W_CONST(Z_ARRVAL_P(container), key EXECUTE_DATA_CC);
            observation = variable_ptr != nullptr;
            break;
        case SWR_PHP_MUTATION_FETCH_W_VAR:
            variable_ptr = zend_fetch_dimension_address_inner_W(Z_ARRVAL_P(container), key EXECUTE_DATA_CC);
            observation = variable_ptr != nullptr;
            break;
        case SWR_PHP_MUTATION_FETCH_RW_CONST:
            variable_ptr = zend_fetch_dimension_address_inner_RW_CONST(Z_ARRVAL_P(container), key EXECUTE_DATA_CC);
            observation = variable_ptr != nullptr;
            break;
        case SWR_PHP_MUTATION_FETCH_RW_VAR:
            variable_ptr = zend_fetch_dimension_address_inner_RW(Z_ARRVAL_P(container), key EXECUTE_DATA_CC);
            observation = variable_ptr != nullptr;
            break;
        case SWR_PHP_MUTATION_ASSIGN:
            debug_val("1", op_data->op1_type, value);
            var_ptr = zend_assign_to_variable(variable_ptr, value, op_data->op1_type, EX_USES_STRICT_TYPES());
            debug_val("2", op_data->op1_type, value);
            observation = var_ptr != nullptr;
            break;
        case SWR_PHP_MUTATION_CANNOT_ADD:
            zend_cannot_add_element();
            break;
        case SWR_PHP_MUTATION_REFERENCE:
            observation = 0;
            if (Z_ISREF_P(variable_ptr)) {
                reference = Z_REF_P(variable_ptr);
                variable_ptr = Z_REFVAL_P(variable_ptr);
                observation = ZEND_REF_HAS_TYPE_SOURCES(reference) ? 2 : 1;
            }
            break;
        case SWR_PHP_MUTATION_OPERATION:
            observation = phphelpers_kind(type_info->get_type_of_value()) |
                          (opline->extended_value == ZEND_CONCAT ? 256u : 0u);
            break;
        case SWR_PHP_MUTATION_TYPED_REFERENCE:
            zend_binary_assign_op_typed_ref(reference, value OPLINE_CC EXECUTE_DATA_CC);
            break;
        case SWR_PHP_MUTATION_BINARY:
            zend_binary_op(variable_ptr, variable_ptr, value OPLINE_CC);
            break;
        case SWR_PHP_MUTATION_CONCAT_ERROR:
            zend_type_error("Only string support concat operation");
            break;
        case SWR_PHP_MUTATION_NUMERIC_ERROR:
            zend_type_error("Only int or float support arithmetic operation");
            break;
        case SWR_PHP_MUTATION_RETURN_USED:
            if (operation == 0 && phase == 9) debug_val("3", op_data->op1_type, value);
            observation = RETURN_VALUE_USED(opline);
            break;
        case SWR_PHP_MUTATION_COPY_RESULT:
            ZVAL_COPY(EX_VAR(opline->result.var), operation == 0 ? var_ptr : variable_ptr);
            break;
        case SWR_PHP_MUTATION_IS_VAR:
            observation = op_data->op1_type == IS_VAR;
            break;
        case SWR_PHP_MUTATION_ADDREF:
            Z_TRY_ADDREF_P(value);
            break;
        case SWR_PHP_MUTATION_FREE:
            FREE_OP((opline + 1)->op1_type, (opline + 1)->op1.var);
            if (operation == 0 && phase == 15) debug_val("4", op_data->op1_type, value);
            break;
        case SWR_PHP_MUTATION_NULL:
            ZVAL_NULL(EX_VAR(opline->result.var));
            break;
        }
    }
}
'''
for signature,operation in [('static void array_add_or_update(',0),('static void array_op(',1)]:
    a=modified.index(signature);start=modified.index('{',a)+1;end=start;depth=1
    while depth:
        depth+=(modified[end]=='{')-(modified[end]=='}');end+=1
    old_start=std.index(signature);old_start=std.index('{',old_start)+1;old_end=old_start;depth=1
    while depth:
        depth+=(std[old_end]=='{')-(std[old_end]=='}');old_end+=1
    original_body=std[old_start:old_end-1]
    selected_body=f'\n    phphelpers_mutate(opline, container, key, value EXECUTE_DATA_CC, {operation});\n'
    modified=modified[:start]+'\n'+guard(selected_body.strip('\n'),original_body.strip('\n'))+'\n'+modified[end-1:]
point=modified.index('static void array_add_or_update(')
modified=modified[:point]+'#ifdef SWOOLE_RS_PHPHELPERS\n'+helper+'#endif\n\n'+modified[point:]

builtin_helper='''static void phphelpers_builtin(INTERNAL_FUNCTION_PARAMETERS, uint32_t operation) {
    zval *arg_ptr = ZEND_CALL_ARG(execute_data, 1);
    const int arg_count = ZEND_CALL_NUM_ARGS(execute_data);
    zval *array = &arg_ptr[0];
    ZVAL_DEREF(array);
    SwrPhpBuiltinState state{0, 1};
    bool observation = Z_TYPE_P(array) == IS_ARRAY;
    HashTable *source = nullptr;
    const ArrayTypeInfo *type_info = nullptr;
    const zval *values = nullptr;
    for (;;) {
        switch (swr_v1_phphelpers_builtin(&state, operation, arg_count, observation)) {
        case SWR_PHP_BUILTIN_DONE:
            return;
        case SWR_PHP_BUILTIN_TYPED:
            observation = is_typed_array(array);
            break;
        case SWR_PHP_BUILTIN_CAPTURE_ARGUMENTS:
            source = Z_ARRVAL_P(array);
            type_info = get_type_info(source);
            break;
        case SWR_PHP_BUILTIN_ARGUMENT:
            observation = type_info->check(source, &EG(uninitialized_zval), &arg_ptr[state.index]);
            break;
        case SWR_PHP_BUILTIN_REPLACEMENT:
            type_info = get_type_info(Z_ARRVAL_P(array));
            values = &arg_ptr[3];
            ZVAL_DEREF(values);
            observation = Z_TYPE_P(values) == IS_ARRAY;
            break;
        case SWR_PHP_BUILTIN_REPLACEMENT_ARRAY: {
            zval *zv;
            HashTable *ht = Z_ARRVAL_P(values);
            observation = true;
            ZEND_HASH_FOREACH_VAL(ht, zv) {
                if (!type_info->check(Z_ARRVAL_P(array), &EG(uninitialized_zval), zv)) {
                    observation = false;
                    break;
                }
            }
            ZEND_HASH_FOREACH_END();
            break;
        }
        case SWR_PHP_BUILTIN_REPLACEMENT_SCALAR:
            observation = type_info->check(Z_ARRVAL_P(array), &EG(uninitialized_zval), values);
            break;
        case SWR_PHP_BUILTIN_SPLICE_SOURCE:
            source = Z_ARRVAL_P(array);
            break;
        case SWR_PHP_BUILTIN_PUSH:
            ori_handler_array_push(INTERNAL_FUNCTION_PARAM_PASSTHRU);
            break;
        case SWR_PHP_BUILTIN_UNSHIFT:
            ori_handler_array_unshift(INTERNAL_FUNCTION_PARAM_PASSTHRU);
            break;
        case SWR_PHP_BUILTIN_SPLICE:
            ori_handler_array_splice(execute_data, return_value);
            break;
        case SWR_PHP_BUILTIN_RESTORE:
            HT_FLAGS(source) |= HASH_FLAG_TYPED_ARRAY;
            break;
        }
    }
}
'''
for operation,name in enumerate(['swoole_array_push','swoole_array_unshift','swoole_array_splice']):
    signature='static PHP_FUNCTION('+name+') {'
    a=modified.index(signature);start=modified.index('{',a)+1;end=start;depth=1
    while depth:
        depth+=(modified[end]=='{')-(modified[end]=='}');end+=1
    original_body=modified[start:end-1]
    selected_body=f'    phphelpers_builtin(INTERNAL_FUNCTION_PARAM_PASSTHRU, {operation});'
    modified=modified[:start]+'\n'+guard(selected_body,original_body.strip('\n'))+'\n'+modified[end-1:]
point=modified.index('static PHP_FUNCTION(swoole_array_push) {')
modified=modified[:point]+'#ifdef SWOOLE_RS_PHPHELPERS\n'+builtin_helper+'#endif\n\n'+modified[point:]

a=modified.index('bool ArrayTypeInfo::parse(zend_string *type_def) {')
start=modified.index('{',a)+1;end=start;depth=1
while depth:
    depth+=(modified[end]=='{')-(modified[end]=='}');end+=1
old_start=std.index('bool ArrayTypeInfo::parse(zend_string *type_def) {')
old_start=std.index('{',old_start)+1;old_end=old_start;depth=1
while depth:
    depth+=(std[old_end]=='{')-(std[old_end]=='}');old_end+=1
original_body=std[old_start:old_end-1]
parse_body='''    uint32_t phase = 0, kind = SWR_PHP_UNDEF;
    bool observation = false;
    for (;;) {
        const size_t length = phase == 0 ? type_def->len : static_cast<size_t>(len_of_type_str);
        switch (swr_v1_phphelpers_parse_definition(&phase, reinterpret_cast<const uint8_t *>(type_str),
                                                   length, kind, observation)) {
        case SWR_PHP_DEFINITION_FALSE:
            return false;
        case SWR_PHP_DEFINITION_TRUE:
            return true;
        case SWR_PHP_DEFINITION_TOO_LONG:
            zend_throw_error(nullptr, "The type definition string is too long (must be less than 65535 characters)");
            return false;
        case SWR_PHP_DEFINITION_LOWERCASE: {
            zend_string *lc_type_def = zend_string_tolower(type_def);
            memcpy(type_str, lc_type_def->val, lc_type_def->len + 1);
            len_of_type_str = lc_type_def->len;
            zend_string_release(lc_type_def);
            break;
        }
        case SWR_PHP_DEFINITION_NORMALIZE: {
            char *normalized = type_str;
            remove_all_spaces(&normalized, &len_of_type_str);
            type_str[len_of_type_str] = '\\0';
            break;
        }
        case SWR_PHP_DEFINITION_ENVELOPE:
            zend_throw_error(nullptr, "The type definition of typed array must start with '<' and end with '>'");
            return false;
        case SWR_PHP_DEFINITION_SELF:
            observation = self.parse(type_str, len_of_type_str);
            if (observation) kind = phphelpers_kind(self.type_of_value);
            break;
        case SWR_PHP_DEFINITION_LOOKUP: {
            zend::String type_str_of_value(type_str + self.offset_of_value_type_str, self.len_of_value_type_str);
            value_ce = zend_lookup_class(type_str_of_value.get());
            const auto result = swr_v1_phphelpers_parse_definition(&phase,
                reinterpret_cast<const uint8_t *>(type_str), len_of_type_str, kind, value_ce != nullptr);
            if (result == SWR_PHP_DEFINITION_CLASS) {
                zend_throw_error(nullptr, "Class '%s' not found", type_str_of_value.val());
                return false;
            }
            return result == SWR_PHP_DEFINITION_TRUE;
        }
        default:
            return false;
        }
    }'''
modified=modified[:start]+'\n'+guard(parse_body,original_body.strip('\n'))+'\n'+modified[end-1:]

# Whole public construction/predicate workflow; native parameter/HashTable API custody.
a=modified.index('PHP_FUNCTION(swoole_typed_array) {');b=modified.index('PHP_FUNCTION(swoole_array_is_typed) {',a);old=modified[a:b].rstrip()
params=old[:old.index('    auto tmp_info =')]
new=params+'''    uint32_t phase = 0;
    bool observation = false;
    ArrayTypeInfo *tmp_info = nullptr, *info = nullptr;
    HashTable *array = nullptr;
    for (;;) {
        switch (swr_v1_phphelpers_typed(&phase, 0, observation, 0)) {
        case SWR_PHP_TYPED_ALLOCATE:
            tmp_info = static_cast<ArrayTypeInfo *>(emalloc(sizeof(ArrayTypeInfo) + ZSTR_LEN(type_def) + 1));
            break;
        case SWR_PHP_TYPED_PARSE:
            observation = tmp_info->parse(type_def);
            break;
        case SWR_PHP_TYPED_FREE:
            efree(tmp_info);
            break;
        case SWR_PHP_TYPED_NULL:
            RETURN_NULL();
        case SWR_PHP_TYPED_INITIAL_TYPED:
            observation = init_values && is_typed_array(init_values);
            break;
        case SWR_PHP_TYPED_COMPARE:
            observation = tmp_info->equals(get_type_info(Z_ARRVAL_P(init_values)));
            break;
        case SWR_PHP_TYPED_COPY_INITIAL:
            ZVAL_COPY(return_value, init_values);
            break;
        case SWR_PHP_TYPED_MISMATCH:
            zend_throw_error(nullptr, "The type definition of the typed array does not match the initial values");
            break;
        case SWR_PHP_TYPED_CREATE: {
            auto n = init_values ? zend_array_count(Z_ARRVAL_P(init_values)) : 0;
            array = make_typed_array(n, tmp_info->len_of_type_str);
            break;
        }
        case SWR_PHP_TYPED_PUBLISH:
            ZVAL_ARR(return_value, array);
            info = get_type_info(array);
            memcpy(info, tmp_info, sizeof(ArrayTypeInfo) + tmp_info->len_of_type_str + 1);
            efree(tmp_info);
            break;
        case SWR_PHP_TYPED_NESTED:
            observation = info->self.type_of_value == IS_ARRAY;
            break;
        case SWR_PHP_TYPED_ELEMENT:
            observation = info->element.parse(info->get_value_type_str(), info->get_len_of_value_type_str());
            break;
        case SWR_PHP_TYPED_DESTROY:
            zval_ptr_dtor(return_value);
            break;
        case SWR_PHP_TYPED_INITIAL:
            observation = init_values != nullptr;
            break;
        case SWR_PHP_TYPED_ITERATE: {
            zend_string *str_key;
            zend_ulong num_key;
            zval *zv;
            zval zk;
            HashTable *ht = Z_ARRVAL_P(init_values);
            ZEND_HASH_FOREACH_KEY_VAL(ht, num_key, str_key, zv) {
                uint32_t entry_phase = 0;
                bool entry_observation = false, entry_done = false;
                while (!entry_done) {
                    switch (swr_v1_phphelpers_typed(&entry_phase, 2, entry_observation, str_key != nullptr)) {
                    case SWR_PHP_TYPED_STRING_KEY: ZVAL_STR(&zk, str_key); break;
                    case SWR_PHP_TYPED_INDEX_KEY: ZVAL_LONG(&zk, num_key); break;
                    case SWR_PHP_TYPED_CHECK: entry_observation = info->check(array, &zk, zv); break;
                    case SWR_PHP_TYPED_DESTROY: zval_ptr_dtor(return_value); break;
                    case SWR_PHP_TYPED_NULL: RETURN_NULL();
                    case SWR_PHP_TYPED_ADDREF: Z_TRY_ADDREF_P(zv); break;
                    case SWR_PHP_TYPED_INSERT_STRING: zend_hash_add(array, str_key, zv); break;
                    case SWR_PHP_TYPED_INSERT_INDEX: zend_hash_index_add(array, num_key, zv); break;
                    default: entry_done = true;
                    }
                }
            } ZEND_HASH_FOREACH_END();
            break;
        }
        default:
            return;
        }
    }
}'''
modified=modified[:a]+guard(new,old)+'\n\n'+modified[b:]
a=modified.index('PHP_FUNCTION(swoole_array_is_typed) {');b=modified.index('{',a)+1;depth=1
while depth:
    depth+=(modified[b]=='{')-(modified[b]=='}');b+=1
old=modified[a:b]
params=old[:old.index('    HashTable *ht =')]
new=params+'''    HashTable *ht = Z_ARRVAL_P(array);
    ArrayTypeInfo *tmp_info = nullptr;
    uint32_t phase = 0;
    bool observation = false;
    for (;;) {
        switch (swr_v1_phphelpers_typed(&phase, 1, observation, 0)) {
        case SWR_PHP_TYPED_OBSERVE_TYPED:
            observation = (HT_FLAGS(ht) & HASH_FLAG_TYPED_ARRAY) != 0;
            break;
        case SWR_PHP_TYPED_DEFINITION:
            observation = type_def != nullptr;
            break;
        case SWR_PHP_TYPED_ALLOCATE:
            tmp_info = static_cast<ArrayTypeInfo *>(emalloc(sizeof(ArrayTypeInfo) + ZSTR_LEN(type_def) + 1));
            break;
        case SWR_PHP_TYPED_PARSE:
            observation = tmp_info->parse(type_def);
            break;
        case SWR_PHP_TYPED_COMPARE:
            observation = get_type_info(ht)->equals(tmp_info);
            break;
        case SWR_PHP_TYPED_SET_TRUE: RETVAL_BOOL(true); break;
        case SWR_PHP_TYPED_SET_FALSE: RETVAL_BOOL(false); break;
        case SWR_PHP_TYPED_FREE: efree(tmp_info); break;
        case SWR_PHP_TYPED_TRUE: RETURN_TRUE;
        case SWR_PHP_TYPED_FALSE: RETURN_FALSE;
        default: return;
        }
    }
}'''
modified=modified[:a]+guard(new,old)+'\n\n'+modified[b:]


a=modified.index('void php_swoole_stdext_minit(int module_number) {');b=modified.index('\n#define SW_CREATE_PHP_FUNCTION_WRAPPER',a);old=modified[a:b].rstrip()
new='void php_swoole_stdext_minit(int module_number) {\n    const uint8_t opcodes[] = {ZEND_INIT_METHOD_CALL, ZEND_ASSIGN_DIM, ZEND_ASSIGN_DIM_OP, ZEND_UNSET_DIM, ZEND_FE_RESET_RW};\n    const user_opcode_handler_t handlers[] = {opcode_handler_method_call, opcode_handler_array_assign,\n        opcode_handler_array_assign_op, opcode_handler_array_unset, opcode_handler_foreach_begin};\n    zend_function **const functions[] = {&fn_swoole_call_array_method, &fn_swoole_call_string_method,\n        &fn_swoole_call_stream_method, &fn_array_push, &fn_array_unshift, &fn_array_splice};\n    zif_handler *const previous[] = {&ori_handler_array_push, &ori_handler_array_unshift, &ori_handler_array_splice};\n    const zif_handler replacements[] = {ZEND_FN(swoole_array_push), ZEND_FN(swoole_array_unshift), ZEND_FN(swoole_array_splice)};\n    size_t cursor = 0;\n    SwrPhpInitStep step;\n    uint32_t action;\n    while ((action = swr_v1_phphelpers_init_next(&cursor, &step)) != SWR_PHP_INIT_DONE) {\n        switch (action) {\n        case SWR_PHP_INIT_OPCODE:\n            zend_set_user_opcode_handler(opcodes[step.index], handlers[step.index]);\n            break;\n        case SWR_PHP_INIT_LOOKUP:\n            *functions[step.index] = zend::get_function(CG(function_table), step.name, step.length);\n            break;\n        case SWR_PHP_INIT_REPLACE:\n            *previous[step.index] = (*functions[step.index + 3])->internal_function.handler;\n            (*functions[step.index + 3])->internal_function.handler = replacements[step.index];\n            break;\n        }\n    }\n}'
modified=modified[:a]+guard(new,old)+'\n'+modified[b:]


a=modified.index('    /* Compile regex or get it from cache. */',modified.index('static void php_do_pcre_match('));b=modified.index('\n}\n/* }}} */',a);old=modified[a:b]
new='    uint32_t phase = 0;\n    bool compiled = false;\n    pce = nullptr;\n    zval count = {};\n    for (;;) {\n        switch (swr_v1_phphelpers_regex(&phase, compiled)) {\n        case SWR_PHP_REGEX_COMPILE:\n            pce = pcre_get_compiled_regex_cache(regex);\n            compiled = pce != nullptr;\n            break;\n        case SWR_PHP_REGEX_INITIALIZE: count = {}; break;\n        case SWR_PHP_REGEX_INCREF: php_pcre_pce_incref(pce); break;\n        case SWR_PHP_REGEX_MATCH:\n#if PHP_VERSION_ID >= 80400\n            php_pcre_match_impl(pce, subject, &count, return_value, global == 1, flags, start_offset);\n#else\n            php_pcre_match_impl(pce, subject, &count, return_value, global, ZEND_NUM_ARGS() >= 3, flags, start_offset);\n#endif\n            break;\n        case SWR_PHP_REGEX_DECREF: php_pcre_pce_decref(pce); break;\n        case SWR_PHP_REGEX_FALSE: RETURN_FALSE;\n        default: return;\n        }\n    }'
modified=modified[:a]+guard(new,old)+modified[b:]


a=modified.index('#define SW_CREATE_PHP_FUNCTION_WRAPPER');b=modified.index('PHP_FUNCTION(swoole_parse_str)',a);old=modified[a:b].rstrip()
new='#define SW_CREATE_PHP_FUNCTION_WRAPPER(swoole_func_name, index) \\\n    PHP_FUNCTION(swoole_func_name) { \\\n        static zend_function *fn_##swoole_func_name = nullptr; \\\n        static SwrPhpWrapper binding; \\\n        if (!fn_##swoole_func_name) { \\\n            if (!swr_v1_phphelpers_wrapper(index, &binding)) { return; } \\\n            fn_##swoole_func_name = zend::get_function(CG(function_table), binding.name, binding.length); \\\n        } \\\n        call_func_move_first_arg(fn_##swoole_func_name, execute_data, return_value, binding.position); \\\n    }\nSW_CREATE_PHP_FUNCTION_WRAPPER(swoole_array_search, 0);\nSW_CREATE_PHP_FUNCTION_WRAPPER(swoole_array_contains, 1);\nSW_CREATE_PHP_FUNCTION_WRAPPER(swoole_array_join, 2);\nSW_CREATE_PHP_FUNCTION_WRAPPER(swoole_array_key_exists, 3);\nSW_CREATE_PHP_FUNCTION_WRAPPER(swoole_array_map, 4);\nSW_CREATE_PHP_FUNCTION_WRAPPER(swoole_array_replace_str, 5);\nSW_CREATE_PHP_FUNCTION_WRAPPER(swoole_array_ireplace_str, 6);\nSW_CREATE_PHP_FUNCTION_WRAPPER(swoole_str_split, 7);\nSW_CREATE_PHP_FUNCTION_WRAPPER(swoole_hash, 8);\nSW_CREATE_PHP_FUNCTION_WRAPPER(swoole_str_replace, 9);\nSW_CREATE_PHP_FUNCTION_WRAPPER(swoole_str_ireplace, 10);'
modified=modified[:a]+guard(new,old)+'\n\n'+modified[b:]


# The complete Rust validation/mutation plans replaced all callers of these
# private inline classifiers. Keep exact controls only in the native fallback.
a=modified.index('    bool value_is_bool() const {');b=modified.index('    bool instance_of(',a)
modified=modified[:a]+'#ifndef SWOOLE_RS_PHPHELPERS\n'+modified[a:b]+'#endif\n'+modified[b:]
a=modified.index('    ArrayTypeInfo *dup() const {');b=modified.index('\n    }',a)+len('\n    }')
modified=modified[:a]+'#ifndef SWOOLE_RS_PHPHELPERS\n'+modified[a:b]+'\n#endif'+modified[b:]

# Predicate policy consumes copied counts only; native parsing/count observation
# and Zend result publication retain their exact original order.
for expression in ['str->len', 'zend_array_count(Z_ARRVAL_P(array))']:
    old='    RETURN_BOOL('+expression+' == 0);'
    assert modified.count(old)==1
    modified=modified.replace(old,guard('    RETURN_BOOL(swr_v1_phphelpers_empty('+expression+'));',old))

header=original('ext-src/php_swoole_cxx.h')
selected_header=header.replace('#include "php_swoole_private.h"','#include "php_swoole_private.h"\n#ifdef SWOOLE_RS_PHPHELPERS\n#include "swoole_rs_phphelpers.h"\n#endif',1)
# Complete accepted common admission body; all external effects stay Native.
async_signature = 'static inline bool php_swoole_async(bool blocking, const std::function<void(void)> &fn) {'
start = selected_header.index(async_signature)
begin = selected_header.index('{', start) + 1
end, depth = begin, 1
while depth:
    depth += (selected_header[end] == '{') - (selected_header[end] == '}')
    end += 1
old_async = selected_header[begin:end - 1]
new_async = r'''    uint32_t phase = 0;
    bool observation = false;
    for (;;) {
        switch (swr_v1_phphelpers_async(&phase, blocking, observation)) {
        case SWR_PHP_ASYNC_OBSERVE_COROUTINE: observation = swoole_coroutine_is_in(); break;
        case SWR_PHP_ASYNC_DISPATCH: return swoole::coroutine::async(fn);
        case SWR_PHP_ASYNC_DIRECT: fn(); return true;
        default: return false;
        }
    }'''
selected_header = selected_header[:begin] + '\n' + guard(new_async, old_async.strip('\n')) + '\n' + selected_header[end - 1:]
def replace_method(class_name, signature, selected):
    global selected_header
    start=selected_header.index(signature,selected_header.index('class '+class_name+' {'))
    begin=selected_header.index('{',start)+1;end=begin;depth=1
    while depth:
        depth+=(selected_header[end]=='{')-(selected_header[end]=='}');end+=1
    old=selected_header[begin:end-1]
    selected_header=selected_header[:begin]+'\n'+guard(selected,old.strip('\n'))+'\n    '+selected_header[end-1:]
def plan(operation, actions, observation='false'):
    return '        uint32_t phase = 0;\n        bool observation = '+observation+';\n        for (;;) {\n            switch (swr_v1_phphelpers_string_plan(&phase, '+str(operation)+', observation)) {\n'+actions+'\n            default: return;\n            }\n        }'
for cls,field,release in [('String','str','zend_string_release(str);'),('CharPtr','str_','efree(str_);')]:
    # Presence is the only policy observation. Native destruction/reset are a
    # fixed ordered effect group; no facts need refreshing between Rust calls.
    replace_method(cls,'    void release() {',
        '        if (!swr_v1_phphelpers_empty('+field+' != nullptr)) {\n'
        '            '+release+'\n'
        '            '+field+' = nullptr;\n'
        '        }')
# Assignment methods return *this, unlike the void release plans.
def assignment(operation, actions):
    return plan(operation,actions).replace('default: return;','default: return *this;')
replace_method('String','    String &operator=(zval *v) {',assignment(3,
    '            case SWR_PHP_STRING_RELEASE: release(); break;\n            case SWR_PHP_STRING_COPY: str = zval_get_string(v); break;'))
replace_method('String','    String &operator=(String &&o) noexcept {',assignment(2,
    '            case SWR_PHP_STRING_RELEASE: release(); break;\n            case SWR_PHP_STRING_MOVE: str = o.str; break;\n            case SWR_PHP_STRING_RESET_SOURCE: o.str = nullptr; break;'))
replace_method('String','    String &operator=(const String &o) {',assignment(1,
    '            case SWR_PHP_STRING_OBSERVE: observation = &o == this; break;\n            case SWR_PHP_STRING_RELEASE: release(); break;\n            case SWR_PHP_STRING_COPY: str = zend_string_copy(o.str); break;'))
replace_method('String','    String(zend_string *v, bool copy) {','        str = nullptr;\n'+plan(4,
    '            case SWR_PHP_STRING_COPY: str = zend_string_copy(v); break;\n            case SWR_PHP_STRING_ALIAS: str = v; break;', 'copy'))
# Copy only the count into Rust; both native allocation families and their
# original lazy val()/second len() observations remain native.
for name,allocator in [('dup','sw_strndup'),('edup','estrndup')]:
    replace_method('String','    char *'+name+'() const {',
        '        return sw_likely(!swr_v1_phphelpers_empty(len())) ? '+allocator+'(val(), len()) : nullptr;')
for signature,effect in [('    void assign(const char *str, size_t len) {','str_ = estrndup(str, len);'),
                         ('    void assign_tolower(const char *str, size_t len) {','str_ = zend_str_tolower_dup(str, len);')]:
    replace_method('CharPtr',signature,plan(3,
        '            case SWR_PHP_STRING_RELEASE: release(); break;\n            case SWR_PHP_STRING_COPY: '+effect+' break;'))

def value_plan(operation,actions,returns_self=False):
    return '        uint32_t phase = 0;\n        bool key_present = false;\n        for (;;) {\n            switch (swr_v1_phphelpers_value_plan(&phase, '+str(operation)+', key_present)) {\n'+actions+'\n            default: return'+(' *this' if returns_self else '')+';\n            }\n        }'
replace_method('KeyValue','    KeyValue(zend_ulong _index, zend_string *_key, zval *_zvalue) {',
    '        index = _index;\n        key = nullptr;\n        ZVAL_UNDEF(&zvalue);\n'+value_plan(0,
    '            case SWR_PHP_FACADE_OBSERVE_KEY: key_present = _key != nullptr; break;\n'
    '            case SWR_PHP_FACADE_RETAIN_KEY: key = zend_string_copy(_key); break;\n'
    '            case SWR_PHP_FACADE_NULL_KEY: key = nullptr; break;\n'
    '            case SWR_PHP_FACADE_DEREFERENCE: ZVAL_DEREF(_zvalue); break;\n'
    '            case SWR_PHP_FACADE_COPY: zvalue = *_zvalue; break;\n'
    '            case SWR_PHP_FACADE_RETAIN: Z_TRY_ADDREF(zvalue); break;'))
replace_method('KeyValue','    void add_to(zval *zarray) {',
    '        HashTable *ht = Z_ARRVAL_P(zarray);\n        zval *dest_elem = nullptr;\n'+value_plan(1,
    '            case SWR_PHP_FACADE_OBSERVE_KEY: key_present = key != nullptr; break;\n'
    '            case SWR_PHP_FACADE_INSERT_STRING: dest_elem = zend_hash_update(ht, key, &zvalue); break;\n'
    '            case SWR_PHP_FACADE_INSERT_INDEX: dest_elem = zend_hash_index_update(ht, index, &zvalue); break;\n'
    '            case SWR_PHP_FACADE_RETAIN_INSERTED: Z_TRY_ADDREF_P(dest_elem); break;'))
replace_method('KeyValue','    ~KeyValue() {',value_plan(2,
    '            case SWR_PHP_FACADE_OBSERVE_KEY: key_present = key != nullptr; break;\n'
    '            case SWR_PHP_FACADE_RELEASE_KEY: zend_string_release(key); break;\n'
    '            case SWR_PHP_FACADE_DESTROY: zval_ptr_dtor(&zvalue); break;'))
for signature,source_value,move,returns_self in [
    ('    Variable(const Variable &&src) noexcept {','src.value',False,False),
    ('    Variable(Variable &&src) noexcept {','src.value',True,False),
    ('    Variable &operator=(const Variable &src) {','src.value',False,True),
    ('    void assign(zval *zvalue) {','*zvalue',False,False)]:
    actions='            case SWR_PHP_FACADE_COPY: value = '+source_value+'; break;\n'
    actions+=('            case SWR_PHP_FACADE_RESET_SOURCE: src.reset(); break;' if move else '            case SWR_PHP_FACADE_RETAIN: add_ref(); break;')
    replace_method('Variable',signature,('        value = {};\n' if 'Variable(' in signature else '')+value_plan(4 if move else 3,actions,returns_self))

replace_method('Callable','    Callable *dup() const {',
    '        auto copy = new Callable();\n        copy->fcc = {};\n        ZVAL_UNDEF(&copy->zfn);\n        uint32_t phase = 0;\n        bool name_present = false;\n        for (;;) {\n            switch (swr_v1_phphelpers_duplicate_plan(&phase, name_present)) {\n'
    '            case SWR_PHP_DUPLICATE_CACHE: copy->fcc = fcc; break;\n'
    '            case SWR_PHP_DUPLICATE_VALUE: copy->zfn = zfn; break;\n'
    '            case SWR_PHP_DUPLICATE_RETAIN: zval_add_ref(&copy->zfn); break;\n'
    '            case SWR_PHP_DUPLICATE_OBSERVE_NAME: name_present = fn_name != nullptr; break;\n'
    '            case SWR_PHP_DUPLICATE_NAME: copy->fn_name = estrdup(fn_name); break;\n'
    '            default: return copy;\n            }\n        }')
replace_method('Callable','    bool call(uint32_t argc, zval *argv, zval *retval) {',
    '        return swr_v1_phphelpers_call_success(sw_zend_call_function_ex(&zfn, &fcc, argc, argv, retval), 0) != 0;')
def replace_factory(signature,selected):
    global selected_header
    start=selected_header.index(signature);begin=selected_header.index('{',start)+1;end=begin;depth=1
    while depth:
        depth+=(selected_header[end]=='{')-(selected_header[end]=='}');end+=1
    old=selected_header[begin:end-1]
    selected_header=selected_header[:begin]+'\n'+guard(selected,old.strip('\n'))+'\n'+selected_header[end-1:]
replace_factory('static inline zend::Callable *sw_callable_create(zval *zfn) {',
    '    auto fn = new zend::Callable(zfn);\n    uint32_t phase = 0;\n    bool observation = false;\n    for (;;) {\n        switch (swr_v1_phphelpers_factory_plan(&phase, 0, observation, 0)) {\n'
    '        case SWR_PHP_FACTORY_OBSERVE_READY: observation = fn->ready(); break;\n'
    '        case SWR_PHP_FACTORY_DELETE: delete fn; break;\n'
    '        case SWR_PHP_FACTORY_RETURN: return fn;\n'
    '        default: return nullptr;\n        }\n    }')
replace_factory('static inline zend::Callable *sw_callable_create_ex(zval *zfn, const char *fname, bool allow_null = true) {',
    '    uint32_t phase = 0;\n    bool observation = false;\n    zend::Callable *cb = nullptr;\n    for (;;) {\n        switch (swr_v1_phphelpers_factory_plan(&phase, 1, observation, allow_null)) {\n'
    '        case SWR_PHP_FACTORY_OBSERVE_POINTER: observation = zfn != nullptr; break;\n'
    '        case SWR_PHP_FACTORY_OBSERVE_NULL: observation = ZVAL_IS_NULL(zfn); break;\n'
    '        case SWR_PHP_FACTORY_CREATE: cb = sw_callable_create(zfn); break;\n'
    '        case SWR_PHP_FACTORY_OBSERVE_CREATED: observation = cb != nullptr; break;\n'
    '        case SWR_PHP_FACTORY_RETURN: return cb;\n'
    '        case SWR_PHP_FACTORY_NULL_ERROR:\n'
    '            zend_throw_exception_ex(swoole_exception_ce, SW_ERROR_INVALID_PARAMS, "%s must be of type callable, null given", fname);\n'
    '            break;\n'
    '        case SWR_PHP_FACTORY_INVALID_ERROR:\n'
    '            zend_throw_exception_ex(swoole_exception_ce, SW_ERROR_INVALID_PARAMS, "%s must be of type callable, %s given", fname, zend_zval_type_name(zfn));\n'
    '            break;\n'
    '        default: return nullptr;\n        }\n    }')

replace_method('ArrayIterator','    void skipUndefBucket() {',
    '        uint32_t phase = 0;\n        bool observation = false;\n        for (;;) {\n            switch (swr_v1_phphelpers_iterator_plan(&phase, observation)) {\n'
    '            case SWR_PHP_ITERATOR_OBSERVE_END: observation = _ptr == pe; break;\n'
    '            case SWR_PHP_ITERATOR_READ_VALUE: _val = &_ptr->val; break;\n'
    '            case SWR_PHP_ITERATOR_OBSERVE_POINTER: observation = _val != nullptr; break;\n'
    '            case SWR_PHP_ITERATOR_OBSERVE_INDIRECT: observation = Z_TYPE_P(_val) == IS_INDIRECT; break;\n'
    '            case SWR_PHP_ITERATOR_DEREFERENCE: _val = Z_INDIRECT_P(_val); break;\n'
    '            case SWR_PHP_ITERATOR_OBSERVE_UNDEFINED: observation = UNEXPECTED(Z_TYPE_P(_val) == IS_UNDEF); break;\n'
    '            case SWR_PHP_ITERATOR_ADVANCE: ++_ptr; break;\n'
    '            case SWR_PHP_ITERATOR_OBSERVE_KEY: observation = _ptr->key != nullptr; break;\n'
    '            case SWR_PHP_ITERATOR_PUBLISH_STRING: _key = _ptr->key; _index = 0; break;\n'
    '            case SWR_PHP_ITERATOR_PUBLISH_INDEX: _index = _ptr->h; _key = nullptr; break;\n'
    '            default: return;\n            }\n        }')
replace_method('Array','    bool set(zend_ulong index, zval *value) const {',
    '        return swr_v1_phphelpers_call_success(add_index_zval(arr, index, value), 0) != 0;')
replace_method('Array','    bool append(zval *value) const {',
    '        return swr_v1_phphelpers_call_success(add_next_index_zval(arr, value), 0) != 0;')

patches=[]
for index,(name,before,after) in enumerate([('ext-src/php_swoole_cxx.cc',cxx,candidate),('ext-src/swoole_stdext.cc',std,modified),('ext-src/php_swoole_cxx.h',header,selected_header)],1):
    filename=f'{index:04d}-'+Path(name).stem+'.patch'
    content='diff --git a/'+name+' b/'+name+'\n'+''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/'+name,tofile='b/'+name))
    if name == 'ext-src/php_swoole_cxx.h':
        # Empty blank-context lines are accepted by Git without trailing spaces.
        content=''.join('\n' if line == ' \n' else line for line in content.splitlines(True))
    path=ROOT/'migration/patches/phphelpers'/filename;path.write_text(content)
    patches.append({'path':filename,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'upstream_paths':[name]})
(ROOT/'migration/patches/phphelpers/manifest.json').write_text(json.dumps({'upstream_commit':PIN,'patches':patches},indent=2)+'\n')
