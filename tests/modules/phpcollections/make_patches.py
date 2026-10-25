#!/usr/bin/env python3
"""Regenerate the two owned pinned-source overlays without touching upstream."""
import argparse
import difflib
import hashlib
import json
import re
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
PIN = '8e8c49915ca5f9dcb9ee654f9e336a9c88dd375e'
PATCHES = ROOT / 'migration/patches/phpcollections'


def replace(text, old, new, count=1):
    if text.count(old) != count:
        raise ValueError(f'Unexpected pinned source occurrence count for {old!r}')
    return text.replace(old,new)


def selected(path, original):
    include = '#include "php_swoole_cxx.h"'
    result = replace(original, include, include + '\n\n#ifndef SWOOLE_RS_PHPCOLLECTIONS\n#error "PHP collections overlay requires --enable-swoole-rs-phpcollections"\n#endif\n#include "swoole_rs_phpcollections.h"')
    if path.endswith('swoole_channel_coro.cc'):
        result = replace(result, '    if (capacity <= 0) {\n        capacity = 1;\n    }',
                         '    capacity = swr_v1_phpcollections_capacity(capacity);')
        begin = result.index('    Z_TRY_ADDREF_P(zdata);')
        end = result.index('\n}\n\nstatic PHP_METHOD(swoole_channel_coro, pop)',begin)
        result = result[:begin] + '''    uint64_t plan = swr_v1_phpcollections_channel_plan(1, 0, 0);
    for (;;) {
        const uint8_t action = plan & 0xff;
        plan >>= 8;
        switch (action) {
        case SWR_COLLECTION_RETAIN: Z_TRY_ADDREF_P(zdata); break;
        case SWR_COLLECTION_DUP: zdata = sw_zval_dup(zdata); break;
        case SWR_COLLECTION_PUSH: {
            const bool success = chan->push(zdata, timeout);
            plan = swr_v1_phpcollections_channel_plan(1, 1, success);
            break;
        }
        case SWR_COLLECTION_OK:
            zend_update_property_long(
                swoole_channel_coro_ce, SW_Z8_OBJ_P(ZEND_THIS), ZEND_STRL("errCode"), Channel::ERROR_OK);
            break;
        case SWR_COLLECTION_ERROR:
            zend_update_property_long(
                swoole_channel_coro_ce, SW_Z8_OBJ_P(ZEND_THIS), ZEND_STRL("errCode"), chan->get_error());
            break;
        case SWR_COLLECTION_TRUE: RETURN_TRUE;
        case SWR_COLLECTION_RELEASE: Z_TRY_DELREF_P(zdata); break;
        case SWR_COLLECTION_FREE: efree(zdata); break;
        case SWR_COLLECTION_FALSE: RETURN_FALSE;
        default: abort();
        }
    }''' + result[end:]
        begin = result.index('    zval *zdata = (zval *) chan->pop(timeout);')
        end = result.index('\n}\n\nstatic PHP_METHOD(swoole_channel_coro, close)',begin)
        result = result[:begin] + '''    zval *zdata = nullptr;
    uint64_t plan = swr_v1_phpcollections_channel_plan(2, 0, 0);
    for (;;) {
        const uint8_t action = plan & 0xff;
        plan >>= 8;
        switch (action) {
        case SWR_COLLECTION_POP:
            zdata = (zval *) chan->pop(timeout);
            plan = swr_v1_phpcollections_channel_plan(2, 1, zdata != nullptr);
            break;
        case SWR_COLLECTION_RESULT: RETVAL_ZVAL(zdata, 0, 0); break;
        case SWR_COLLECTION_FREE: efree(zdata); break;
        case SWR_COLLECTION_OK:
            zend_update_property_long(
                swoole_channel_coro_ce, SW_Z8_OBJ_P(ZEND_THIS), ZEND_STRL("errCode"), Channel::ERROR_OK);
            break;
        case SWR_COLLECTION_ERROR:
            zend_update_property_long(
                swoole_channel_coro_ce, SW_Z8_OBJ_P(ZEND_THIS), ZEND_STRL("errCode"), chan->get_error());
            break;
        case SWR_COLLECTION_FALSE: RETURN_FALSE;
        case SWR_COLLECTION_DONE: return;
        default: abort();
        }
    }''' + result[end:]
    else:
        result = replace(result, 'using namespace swoole;', 'using namespace swoole;\nstatic_assert(TableColumn::TYPE_INT == 1 && TableColumn::TYPE_FLOAT == 2 &&\n              TableColumn::TYPE_STRING == 3, "pinned TableColumn tags");\nstatic_assert(sizeof(zend_long) == sizeof(intptr_t), "PHP integer width");\nstatic_assert(sizeof(long) == sizeof(zend_long), "signed-long arithmetic profile");')
        result = replace(result, '''            if (col == nullptr) {
                continue;
            } else if (col->type == TableColumn::TYPE_STRING) {''', '''            if (col == nullptr) {
                continue;
            }
            if (col->type == TableColumn::TYPE_STRING) {''')
        for name, count in [('col', 4), ('column', 2)]:
            pattern = r'(?m)^([ \t]*)if \(' + name + r'->type == TableColumn::TYPE_STRING\) \{'
            def classify(match):
                indent = match[1]
                return (indent + 'const auto kind = swr_v1_phpcollections_kind(' + name + '->type);\n' +
                        indent + 'if (kind == TableColumn::TYPE_STRING) {')
            result, observed = re.subn(pattern, classify, result)
            if observed != count:
                raise ValueError('Unexpected pinned type-dispatch count')
            for kind in ('FLOAT', 'INT'):
                result = result.replace(f'{name}->type == TableColumn::TYPE_{kind}', f'kind == TableColumn::TYPE_{kind}')
        result = replace(result, 'if (size < 1)', 'if (swr_v1_phpcollections_string_invalid(type, size))')
        result = replace(result, 'if (keylen >= SW_TABLE_KEY_SIZE)', 'if (swr_v1_phpcollections_key_warning(keylen, SW_TABLE_KEY_SIZE))')
        result = replace(result, 'if (zv == nullptr || ZVAL_IS_NULL(zv))',
                         'if (swr_v1_phpcollections_clear_cell(zv != nullptr, zv != nullptr && ZVAL_IS_NULL(zv)))')
        for operation, argument, subtract in [('+', 'incrby', 0), ('-', 'decrby', 1)]:
            old = f'''        if ({argument}) {{
            set_value {operation}= zval_get_double({argument});
        }} else {{
            set_value {operation}= 1;
        }}'''
            new = f'''        const double amount = {argument} ? zval_get_double({argument}) : 1;
        set_value = swr_v1_phpcollections_float_update(set_value, amount, {subtract});'''
            result = replace(result, old, new)
        for operation, argument, subtract in [('+', 'incrby', 0), ('-', 'decrby', 1)]:
            old = f'''        if ({argument}) {{
            set_value {operation}= zval_get_long({argument});
        }} else {{
            set_value {operation}= 1;
        }}'''
            new = f'''        const long amount = {argument} ? zval_get_long({argument}) : 1;
        if (!swr_v1_phpcollections_integer_update(set_value, amount, {subtract}, &set_value)) {{
            // Preserve the original native undefined overflow domain; no parity claim.
            set_value {operation}= amount;
        }}'''
            result = replace(result, old, new)
        result = replace(result, '''    if (mode == COUNT_NORMAL) {
        RETURN_LONG(table->count());
    } else {
        RETURN_LONG(table->count() * table->column_list->size());
    }''', '''    RETURN_LONG(swr_v1_phpcollections_count(
        mode, table->count(), mode == COUNT_NORMAL ? 0 : table->column_list->size()));''')
        result = replace(result, '''    if (!row) {
        RETVAL_FALSE;
    } else if (field) {''', '''    const auto action = swr_v1_phpcollections_get_action(row != nullptr, field != nullptr);
    if (action == 0) {
        RETVAL_FALSE;
    } else if (action == 1) {''')
        first = result.index('static PHP_METHOD(swoole_table, incr) {')
        middle = result.index('static PHP_METHOD(swoole_table, decr) {', first)
        end = result.index('static PHP_METHOD(swoole_table, get) {', middle)
        def normalize(body, name, flag, operation):
            body = body.replace(f'static PHP_METHOD(swoole_table, {name})', 'static void table_update(INTERNAL_FUNCTION_PARAMETERS, bool subtract)')
            body = body.replace(name + 'by', 'changeby')
            body = body.replace(f'"can\'t execute \'{name}\' on a string type column"', 'OPERATION_WARNING')
            body = body.replace(f'swr_v1_phpcollections_float_update(set_value, amount, {flag})', 'swr_v1_phpcollections_float_update(set_value, amount, subtract)')
            body = body.replace(f'swr_v1_phpcollections_integer_update(set_value, amount, {flag},', 'swr_v1_phpcollections_integer_update(set_value, amount, subtract,')
            body = body.replace(f'set_value {operation}= amount;', 'NATIVE_UNDEFINED_ARITHMETIC;')
            return body
        common = normalize(result[first:middle], 'incr', 0, '+')
        if common != normalize(result[middle:end], 'decr', 1, '-'):
            raise ValueError('Pinned increment/decrement effect prefixes differ')
        common = common.replace('OPERATION_WARNING', 'subtract ? "can\'t execute \'decr\' on a string type column" : "can\'t execute \'incr\' on a string type column"')
        common = common.replace('NATIVE_UNDEFINED_ARITHMETIC;', 'if (subtract) { set_value -= amount; } else { set_value += amount; }')
        wrappers = '''static PHP_METHOD(swoole_table, incr) {
    table_update(INTERNAL_FUNCTION_PARAM_PASSTHRU, false);
}

static PHP_METHOD(swoole_table, decr) {
    table_update(INTERNAL_FUNCTION_PARAM_PASSTHRU, true);
}

'''
        result = result[:first] + common + wrappers + result[end:]

        helper = """static inline void table_set_field_value(TableRow *row, TableColumn *col, zval *zv, bool initialize) {
    switch (swr_v1_phpcollections_write_action(col->type, initialize, zv != nullptr, zv != nullptr && ZVAL_IS_NULL(zv))) {
    case 0: col->clear(row); break;
    case 3: {
        zend_string *str = zval_get_string(zv);
        row->set_value(col, ZSTR_VAL(str), ZSTR_LEN(str));
        zend_string_release(str);
        break;
    }
    case 2: {
        double value = zval_get_double(zv);
        row->set_value(col, &value, 0);
        break;
    }
    case 1: {
        long value = zval_get_long(zv);
        row->set_value(col, &value, 0);
        break;
    }
    default: abort();
    }
}

"""
        begin = result.index('            if (swr_v1_phpcollections_clear_cell(')
        end = result.index('\n        }\n    } else {', begin)
        result = result[:begin] + '            table_set_field_value(row, col, zv, true);' + result[end:]
        begin = result.index('            const auto kind = swr_v1_phpcollections_kind(col->type);', result.index('SW_HASHTABLE_FOREACH_START2'))
        end = result.index('\n        }\n        (void) ktype;', begin)
        result = result[:begin] + '            table_set_field_value(row, col, zv, false);' + result[end:]
        at = result.index('static PHP_METHOD(swoole_table, set) {')
        result = result[:at] + helper + result[at:]
    return select_table_facade(result) if path == 'ext-src/swoole_table.cc' else result


def select_table_facade(result):
    from body_map import functions
    result = replace(result, '#include "swoole_table.h"', '#include "swoole_table.h"\n#include "swoole_rs_memory_table_v2.h"', 1)
    result, count = re.subn(r'\bTable \*', 'TableV2 *', result)
    if count != 27:
        raise ValueError('Unexpected Table pointer inventory')
    result = replace(result, 'Table::make(', 'TableV2::make(')
    original = functions(result)
    template = functions(Path(__file__).with_name('table_facade.inc').read_text())
    expected = {'table_read_field_value', 'table_row2array', 'table_get_field_value',
                'table_set_field_value', 'swoole_table::set', 'table_update',
                'swoole_table::get', 'swoole_table::count', 'swoole_table::current'}
    if set(template) != expected or set(template) - {'table_read_field_value'} - set(original):
        raise ValueError('Typed Table facade body inventory differs')
    for name, row in template.items():
        if name == 'table_read_field_value':
            continue
        replacement = row['body']
        if name == 'table_row2array':
            replacement = template['table_read_field_value']['body'] + '\n\n' + replacement
        result = replace(result, original[name]['body'], replacement)
    if 'column_list' in result or 'const TableColumn *' in result or 'column->' in result or 'col->' in result:
        raise ValueError('Selected PHP Table still consumes native column storage/metadata')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    source = parser.parse_args().source
    manifest = {'upstream_commit': PIN, 'patches': []}
    PATCHES.mkdir(parents=True, exist_ok=True)
    for i, path in enumerate(('ext-src/swoole_table.cc', 'ext-src/swoole_channel_coro.cc'),1):
        original = subprocess.check_output(['git','-C',str(source),'show',f'{PIN}:{path}'],text=True)
        modified = selected(path,original)
        patch = f'diff --git a/{path} b/{path}\n' + ''.join(difflib.unified_diff(original.splitlines(True),modified.splitlines(True),fromfile='a/'+path,tofile='b/'+path))
        name = f'{i:04d}-{Path(path).stem}.patch'
        (PATCHES/name).write_text(patch)
        manifest['patches'].append({'path':name,'sha256':hashlib.sha256(patch.encode()).hexdigest(),'upstream_paths':[path]})
    (PATCHES/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')

if __name__ == '__main__':
    main()
