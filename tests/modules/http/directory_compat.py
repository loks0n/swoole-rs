#!/usr/bin/env python3
"""Check unchanged legacy StaticHandler data declaration/layout/copy/reference ABI."""
import argparse
import io
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import tempfile
from gate import PIN, apply_http_patch
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, run_isolated, write_report


def legacy_fields(header):
    return header.split('class StaticHandler {',1)[1].split('  public:',1)[0].replace('    friend class StaticHandlerV2;\n','')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', default='target/reports/http-directory-compat.json')
    args = parser.parse_args()
    # C++20 is left out: the pinned swoole_process_pool.h fails -Werror=volatile there.
    standards = ['c++14', 'c++17']
    patches = [ROOT/'migration/patches/http'/name for name in ['0002-static-ranges.patch', '0003-static-inline.patch']]
    report = {'pin': PIN, 'passed': False, 'scope': 'Unconfigured pinned/selected legacy StaticHandler data declarations, C++14/17, copy/reference traits and actual V2 composition; not all configured SDK modes or runtime parity', 'checks': [], 'standards': standards, 'full_gate_passed': False}
    with tempfile.TemporaryDirectory(prefix='swr-http-directory-compat-') as temporary:
        tree = Path(temporary)
        data = subprocess.check_output(['git', '-C', str(args.source), 'archive', PIN, 'include', 'src/server/static_handler.cc'])
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for member in archive:
                if member.isfile():
                    path = tree/member.name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(archive.extractfile(member).read())
        original = (tree/'include/swoole_static_handler.h').read_text()
        reference = tree/'legacy-original.h'; reference.write_text(original)
        for patch in patches:
            apply_http_patch(tree, patch, report)
        selected = (tree/'include/swoole_static_handler.h').read_text()
        report['data_declarations_equal'] = legacy_fields(original) == legacy_fields(selected)
        if not report['data_declarations_equal']:
            write_report(args.output, report); return 1
        code = '''#include HEADER
#include <type_traits>
#include <cstdio>
#include <utility>
using T=swoole::http_server::StaticHandler;
static_assert(std::is_copy_constructible<T>::value && std::is_copy_assignable<T>::value,"legacy copy source ABI");
static_assert(std::is_lvalue_reference<decltype(std::declval<T&>().get_tasks())>::value,"task vector reference");
static_assert(std::is_same<decltype(std::declval<const T&>().get_mimetype()),const std::string&>::value,"MIME reference");
static_assert(std::is_same<decltype(std::declval<T&>().get_content_type()),const std::string&>::value,"content reference");
int main(){std::printf("{\\"size\\":%zu,\\"align\\":%zu}\\n",sizeof(T),alignof(T));}
'''
        source = tree/'legacy.cc'; source.write_text(code)
        v2 = tree/'typed.cc'; v2.write_text('''#include "swoole_rs_http_static_v2.h"
#include <type_traits>
using T=swoole::http_server::StaticHandler;
using V=swoole::http_server::StaticHandlerV2;
static_assert(!std::is_base_of<T,V>::value,"typed composition");
static_assert(sizeof(V)==3*sizeof(void*),"selected facade has only two native views and one context handle");
static_assert(std::is_same<decltype(std::declval<V&>().get_content_type(std::declval<std::string&>())),const std::string&>::value,"scoped native IO/global MIME reference");
static_assert(std::is_same<decltype(std::declval<const V&>().copy_tasks()),std::vector<swr_v2_http_static_task>>::value,"owned typed send snapshot by value");
static_assert(!std::is_copy_constructible<V>::value && !std::is_copy_assignable<V>::value,"sole directory owner");
''')
        flags = ['-DSWOOLE_RS_HTTP', '-DNDEBUG', '-Wall', '-Wextra', '-Werror', '-I'+str(tree/'include'), '-I'+str(ROOT/'native/http')]
        flags += shlex.split(subprocess.check_output(['pkg-config', '--cflags', 'openssl'], text=True))
        for standard in standards:
            layouts = []
            for name, header in [('original', reference), ('selected', tree/'include/swoole_static_handler.h')]:
                binary = tree/(name+'-'+standard)
                command = ['c++', '-std='+standard, *flags, '-DHEADER="'+str(header)+'"', str(source), '-o', str(binary)]
                result = run_isolated(command, timeout=60)
                row = {'name': name, 'standard': standard, 'command': command, 'compile_returncode': result.returncode, 'stderr': result.stderr}
                report['checks'].append(row)
                if result.returncode: write_report(args.output, report); print(result.stderr, file=sys.stderr); return 1
                result = run_isolated([str(binary)], timeout=10)
                row.update(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
                if result.returncode: write_report(args.output, report); return 1
                layouts.append(json.loads(result.stdout))
            if layouts[0] != layouts[1]: write_report(args.output, report); return 1
            for name, path in [('typed', v2), ('whole-static-tu', tree/'src/server/static_handler.cc')]:
                command = ['c++', '-std='+standard, *flags, '-fsyntax-only', str(path)]
                result = run_isolated(command, timeout=60)
                report['checks'].append({'name': name, 'standard': standard, 'command': command, 'returncode': result.returncode, 'stderr': result.stderr})
                if result.returncode: write_report(args.output, report); print(result.stderr, file=sys.stderr); return 1
        report['passed'] = True
        write_report(args.output, report)
        print(json.dumps({'checks': len(report['checks']), 'passed': True}))
    return 0

if __name__ == '__main__': sys.exit(main())
