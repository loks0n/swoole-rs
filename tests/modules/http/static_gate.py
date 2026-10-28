#!/usr/bin/env python3
"""Actual static response method comparison with counted native IO/date/MIME facades."""
import argparse
from pathlib import Path
import sys
import tempfile
from gate import PIN, body, add_archive_arguments, prepare_archive, Sides, run
from tools.harness import write_report

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    add_archive_arguments(parser)
    parser.add_argument('--output', default='target/reports/http-static.json')
    args = parser.parse_args(); local = Path(__file__).resolve().parent
    report = {'pin': PIN, 'scope': 'Actual pinned/patched static response method with counted native facades; not filesystem/socket/PHP parity', 'native_sanitizers': True, 'rust_instrumented': args.rust_sanitize, 'rust_std_instrumented': False, 'passed': False}
    with tempfile.TemporaryDirectory(prefix='swr-http-static-') as temp:
        tree = Path(temp); path = 'src/server/static_handler.cc'
        archive = prepare_archive(args, tree, report)
        if not archive: write_report(args.output, report); return 1
        sides = Sides(args.source, args.archive, tree, path, 'src/core/base.cc')
        if not sides.native(report, path): write_report(args.output, report); return 1
        dependencies = tree/'dependencies.cc'; dependencies.write_text('#include "static_oracle.h"\n' + body(sides.original('src/core/base.cc'), 'size_t sw_snprintf('))
        for namespace, text in [('upstream_static', sides.original(path)), ('candidate_static', sides.selected(path))]:
            parts = []
            if 'static swr_v1_http_proxy_text static_header_text(' in text:
                parts += [body(text, 'static swr_v1_http_proxy_text static_header_text('), body(text, 'static size_t encode_static_headers(')]
            if 'static bool select_static_handler_impl(' in text:
                view = sides.abi/'swoole_rs_http_request_view.h'
                parts.append('namespace http_server {\ntemplate<class T>\n' + body(view.read_text(), 'class LegacyRequestView {') + '; }')
                parts.append('template<class RequestView>\n' + body(text, 'static bool select_static_handler_impl('))
            parts.append(body(text, 'bool Server::select_static_handler('))
            extracted = tree/(namespace+'.cc'); extracted.write_text('#include "static_oracle.h"\nnamespace '+namespace+' {\n'+'\n'.join(parts)+'\n}\n')
        binary = tree/'gate'
        units = [('upstream', tree/'upstream_static.cc'), ('candidate', tree/'candidate_static.cc'), ('upstream', dependencies), ('candidate', local/'static_gate.cc')]
        if not sides.build(binary, units, archive, report): write_report(args.output, report); return 1
        return run(binary, ['swr_v1_http_static_headers', 'swr_v1_http_static_body', 'swr_v1_http_static_select'], args.output, report)
if __name__ == '__main__': sys.exit(main())
