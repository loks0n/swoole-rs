#!/usr/bin/env python3
"""Core Request paired capability: real SDK/TU/header checks, never runtime parity."""
import argparse
import io
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
from gate import PIN, apply_http_patch
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, run_isolated, write_report
from tools.build_hybrid import apply_patch_verified

MODEL = r'''
#include "swoole_rs_http_request_view.h"
#include <type_traits>
using namespace swoole;
using namespace swoole::http_server;
#ifdef SWOOLE_RS_HTTP_REQUEST_V2
static_assert(std::is_same<SelectedRequest,RequestV2>::value,"paired object type");
static_assert(sizeof(RequestV2)==6*sizeof(void *),"Native resource slots only");
#else
static_assert(std::is_same<SelectedRequest,Request>::value,"legacy object type");
#endif
static_assert(sizeof(SelectedRequestView)==sizeof(SelectedRequest *),"pointer-only view");
static_assert(std::is_same<decltype(std::declval<SelectedRequestView>().method()),uint8_t>::value,"method width");
static_assert(std::is_same<decltype(std::declval<SelectedRequestView>().header_length()),uint32_t>::value,"header width");
static_assert(std::is_same<decltype(std::declval<SelectedRequestView>().content_length()),uint64_t>::value,"content width");
void all_actual_accessors(SelectedRequest *request,Server *server,Connection *connection,String *buffer) {
    SelectedRequestView view(request);
    (void)view.get(); (void)view.buffer(); view.set_buffer(buffer);
    (void)view.method(); (void)view.url_offset(); (void)view.url_length();
    (void)view.header_length(); (void)view.max_length(); (void)view.content_length();
    (void)view.has_form(); (void)view.excepted(); (void)view.too_large();
    (void)view.unavailable(); (void)view.header_parsed(); (void)view.tried_to_dispatch();
    (void)view.multipart_header_parsed(); (void)view.known_length(); (void)view.keep_alive();
    (void)view.chunked(); (void)view.nobody_chunked(); view.set_max_length(128);
    view.advance_header_length(5); view.mark_dispatched(); view.discard_form(); view.clean();
    (void)view.get_protocol(); (void)view.get_header_length(); (void)view.get_chunked_body_length();
    view.parse_header_info(); (void)view.parse_multipart_data(buffer);
    (void)view.init_multipart_parser(server); view.destroy_multipart_parser();
    (void)view.get_header("Host"); (void)view.has_expect_header();
    (void)view.select_static_handler(server,connection);
    delete request; // Compile-time selected type even after an HTTP2 flag update.
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--upstream-unused-parameter-policy', action='store_true', help='Explicit pinned config.m4 maintainer subset: suppress unused-parameter warnings; strict profile remains separate')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Refusing an existing receipt')
    report = {'pin': PIN, 'scope': 'Actual SDK whole-TU and all typed accessor instantiations in C++14/17; no native receive, parser, lifetime, producer or performance execution',
              'full_gate_passed': False, 'passed': False, 'checks': [], 'minimum_free_bytes': 4*1024**3, 'unrun_profiles': ['Native receive/dispatch/parser/resources/lifetimes', 'originals/full configuration/platform', 'performance/default activation']}
    with tempfile.TemporaryDirectory(prefix='swr-http-request-v2-compat-') as temporary:
        tree = Path(temporary)
        data = subprocess.check_output(['git', '-C', str(args.source), 'archive', PIN, 'include', 'src/protocol/http.cc', 'src/server/static_handler.cc', 'thirdparty/multipart_parser.h', 'config.m4'])
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for member in archive:
                if member.isfile():
                    path = tree/member.name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(archive.extractfile(member).read())
        original_protocol = tree/'src/protocol/http.cc'
        original_static = tree/'src/server/static_handler.cc'
        report['warning_policy'] = {'unused_parameter_suppression': args.upstream_unused_parameter_policy, 'scope': 'Explicit unused-parameter subset of pinned maintainer flags, not full configure/maintainer qualification'}
        for name in ['0001-http-helpers.patch', '0002-static-ranges.patch', '0003-static-inline.patch']:
            apply_http_patch(tree, ROOT/'migration/patches/http'/name, report)
        shared_manifest = ROOT/'migration/patches/integration/manifest.json'
        shared = json.loads(shared_manifest.read_text())
        entry = next(item for item in shared['patches'] if item['path']=='0002-request-v2-server-declaration.patch')
        report['server_declaration_patch'] = apply_patch_verified(tree, shared_manifest.parent/entry['path'], entry['upstream_paths'], entry['sha256'])
        model = tree/'view.cc'
        model.write_text(MODEL)
        common = ['-DNDEBUG', '-Wall', '-Wextra', '-Werror', '-fsyntax-only', '-I'+str(tree), '-I'+str(ROOT/'native/http')]
        if args.upstream_unused_parameter_policy:
            common.append('-Wno-unused-parameter')
        common += shlex.split(subprocess.check_output(['pkg-config', '--cflags', 'openssl'], text=True))
        # HTTP is graduated: every Rust build has its patched sources (#123).
        modes = [('http-only', []), ('paired', ['SWOOLE_RS_PORTS', 'SWOOLE_RS_HTTP_REQUEST_V2']),
                 ('old-flags-staged', ['SWOOLE_RS_PORTS'])]
        for mode, macros in modes:
            for standard in ['c++14', 'c++17']:
                for label, path in [('all-accessors', model), ('protocol', original_protocol), ('static', original_static)]:
                    free = shutil.disk_usage(tree).free
                    if free < report['minimum_free_bytes']:
                        report['blocked'] = {'reason': 'Unchanged4GiB guard', 'free_bytes': free, 'mode': mode, 'standard': standard, 'label': label}
                        write_report(args.output, report)
                        return 1
                    command = ['c++', '-std='+standard, *common, '-I'+str(tree/'include'), *['-D'+macro for macro in macros], str(path)]
                    result = run_isolated(command, timeout=60)
                    report['checks'].append({'mode': mode, 'standard': standard, 'label': label, 'command': command, 'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
                    write_report(args.output, report)
                    if result.returncode:
                        print(result.stderr, file=sys.stderr)
                        return 1
        report['passed'] = True
        write_report(args.output, report)
        print(json.dumps({'source_syntax_checks': len(report['checks']), 'passed': True, 'full_gate_passed': False}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
