#!/usr/bin/env python3
"""Map every original collection facade function to its Rust exports and native remainder.

Fails when the facade function set or registration table changes without review,
or when the selected source calls an undeclared module-local export.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import tempfile

from gate import ROOT, PIN, stage
from tools.harness import write_report

# Explicit source-reviewed boundaries. Unknown/new functions must be reviewed.
BOUNDARIES = {
    'swoole_table.cc': {
        'table_row2array': 'Rust-owned ordered-column cursor selects transient descriptors; native locked dispatch/getters, array materialization and failure propagation remain',
        'table_get_field_value': 'Native lookup and row/Zend materialization dispatcher; Rust chooses complete read/type/error sequence',
        **dict.fromkeys(['table_fetch_object', 'table_get_ptr', 'table_set_ptr'], 'Native Zend layout and authoritative Table pointer'),
        **dict.fromkeys(['table_get_and_check_ptr', 'table_get_and_check_ptr2'], 'Native constructor/ready checks and fatal-error boundary'),
        **dict.fromkeys(['table_free_object', 'table_create_object'], 'Native Zend allocation/standard object lifecycle'),
        'php_swoole_table_minit': 'Native class/method/alias/property/constant/Iterator registration',
        'swoole_table::__construct': 'Native constructor-once check, parameter parse, Table allocation/hash callback and pointer publication',
        'swoole_table::column': 'Native parse/alignment/ready/warning effects; actual Rust record/name/index storage is M12',
        'swoole_table::create': 'Native shared-memory creation and size/memory property publication',
        'swoole_table::destroy': 'Native authoritative storage destruction and pointer clearing',
        'swoole_table::set': 'Rust ordered-column cursor supplies new-row descriptors; native parse/ready/key warning, row lock/allocation, input iteration, fresh Zend conversion/store/cleanup/unlock/error dispatch remain',
        **dict.fromkeys(['swoole_table::incr', 'swoole_table::decr'], 'Native parse, lock/row allocation/initialization, Zend conversion, warning/publication/cleanup/unlock; undefined arithmetic domain remains native'),
        'swoole_table::get': 'Native parse, row lookup/lock, field/full-row materialization and unlock',
        **dict.fromkeys(['swoole_table::exists', 'swoole_table::del'], 'Native parse and authoritative row storage operation'),
        'swoole_table::count': 'Rust ordered-column cursor supplies recursive declaration count; native pointer/parse/normal-mode guard, failure and Zend return remain',
        **dict.fromkeys(['swoole_table::getMemorySize', 'swoole_table::getSize', 'swoole_table::stats'], 'Native storage observations and Zend return/array construction'),
        **dict.fromkeys(['swoole_table::rewind', 'swoole_table::valid', 'swoole_table::current', 'swoole_table::key', 'swoole_table::next'], 'Native iterator/row identity and advancement; Zend materialization/return'),
    },
    'swoole_channel_coro.cc': {
        **dict.fromkeys(['channel_coro_fetch_object', 'channel_coro_get_ptr'], 'Native Zend object layout/pointer and constructor fatal-error boundary'),
        **dict.fromkeys(['channel_coro_dtor_object', 'channel_coro_free_object', 'channel_coro_create_object'], 'Native Zend lifecycle, authoritative queue draining, zval/resource destruction and Channel allocation/free'),
        'php_swoole_channel_coro_minit': 'Native class/handler/shortname/property/constant registration',
        'swoole_channel_coro::__construct': 'Native parse, authoritative Channel allocation and capacity publication',
        **dict.fromkeys(['swoole_channel_coro::push', 'swoole_channel_coro::pop'], 'Native parse, zval custody, queue operation/suspension, fresh result/error observation, property/return publication and reference/container cleanup'),
        **dict.fromkeys(['swoole_channel_coro::close', 'swoole_channel_coro::length', 'swoole_channel_coro::isEmpty', 'swoole_channel_coro::isFull', 'swoole_channel_coro::stats'], 'Native authoritative queue operation/observation and Zend return/array construction'),
    },
}
ADDED = {'table_read_field_value': 'Shared native row/Zend materialization effect dispatcher; Rust owns type/error/sequence selection',
         'table_set_field_value': 'Native Table conversion/store/release effect dispatcher; Rust chooses complete write sequence',
         'table_update': 'Shared native incr/decr effect bridge'}


def functions(text):
    # Mask comments/literals while retaining offsets/newlines. This deliberately
    # supports these pinned facades, not arbitrary C++ preprocessing or ASTs.
    token = r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''
    masked = re.sub(token, lambda match: re.sub(r'[^\n]', ' ', match.group()), text)
    result = {}
    depth = 0
    begin = None
    name = None
    for index, char in enumerate(masked):
        if char == '{':
            if depth == 0:
                begin = masked.rfind('\n', 0, index) + 1
                header = masked[begin:index].strip()
                method = re.fullmatch(r'(?:static\s+)?PHP_METHOD\((\w+),\s*(\w+)\)', header)
                function = re.search(r'(\w+)\([^;{}]*\)\s*$', header)
                name = '::'.join(method.groups()) if method else function[1] if function else None
                if name is None and ('(' in header or ')' in header):
                    raise ValueError('Unsupported top-level body requires parser review')
            depth += 1
        elif char == '}':
            depth -= 1
            if depth < 0:
                raise ValueError('Unbalanced source body')
            if depth == 0 and name:
                if name in result:
                    raise ValueError('Duplicate facade function: ' + name)
                body = text[begin:index + 1]
                result[name] = dict(lines=[text.count('\n', 0, begin) + 1, text.count('\n', 0, index) + 1],
                                    body=body, code=masked[begin:index + 1])
                name = None
    if depth:
        raise ValueError('Unbalanced source body')
    return result


def account(original, selected, boundaries, additions=None):
    additions = additions or {}
    before, after = functions(original), functions(selected)
    if set(before) != set(boundaries) or set(after) != set(before) | set(additions):
        raise ValueError('Facade function set changed; explicit boundary review required')
    direct = {name: sorted(set(re.findall(r'\b(swr_v1_phpcollections_\w+)\s*\(', row['code'])))
              for name, row in after.items()}
    calls = {name: {helper for helper in after if '::' not in helper and
                   re.search(r'\b' + re.escape(helper) + r'\s*\(', row['code']) and helper != name}
             for name, row in after.items()}
    def exports(name, seen):
        return set(direct[name]).union(*(exports(helper, seen | {name}) for helper in calls[name] - seen))
    rows = []
    for name in before:
        left, right = before[name], after[name]
        rows.append(dict(function=name, original={'lines': left['lines']},
                         selected={'lines': right['lines']},
                         body_changed=left['body'] != right['body'],
                         direct_rust_exports=direct[name], reachable_local_helper_exports=sorted(exports(name, set())),
                         remaining_native=boundaries[name], whole_function_replaced_by_rust=False))
    added = [dict(function=name, role=additions[name], lines=after[name]['lines'],
                  direct_rust_exports=direct[name]) for name in after if name not in before]
    registrations = re.compile(r'^static const zend_function_entry [\s\S]*?^};', re.M)
    original_tables, selected_tables = registrations.findall(original), registrations.findall(selected)
    if (original_tables or selected_tables) and (len(original_tables) != 1 or original_tables != selected_tables):
        raise ValueError('Native method/alias registration table changed; explicit review required')
    return dict(original_functions=len(before), functions=rows, added_native_bridges=added)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = dict(pin=PIN, files={})
    with tempfile.TemporaryDirectory(prefix='phpcollections-map-') as temporary:
        work = Path(temporary)
        identities = stage(args.source, work)
        for name, identity in identities.items():
            original = subprocess.check_output(['git', '-C', str(args.source), 'show', PIN + ':' + name], text=True)
            selected = (work / name).read_text()
            report['files'][name] = dict(**identity, **account(original, selected, BOUNDARIES[Path(name).name], ADDED if name.endswith('swoole_table.cc') else {}))
    declared = set(re.findall(r'\b(swr_v1_phpcollections_\w+)\s*\(',
                              (ROOT / 'native/phpcollections/swoole_rs_phpcollections.h').read_text()))
    called = set()
    for row in report['files'].values():
        for body in [*row['functions'], *row['added_native_bridges']]:
            called.update(body['direct_rust_exports'])
    report['declared_exports'] = sorted(declared)
    report['selected_facade_exports'] = sorted(called)
    report['compatibility_declarations_without_selected_facade_caller'] = sorted(declared - called)
    if called - declared:
        raise ValueError('Selected source calls undeclared module-local ABI')
    write_report(args.output, report)
    print(json.dumps({name: row['original_functions'] for name, row in report['files'].items()}))


if __name__ == '__main__':
    main()
