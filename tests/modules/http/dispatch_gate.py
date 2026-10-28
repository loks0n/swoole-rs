#!/usr/bin/env python3
"""Actual HTTP dispatch/index/proxy creation/status boundary checks."""
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
    parser.add_argument('--output', default='target/reports/http-dispatch.json')
    args = parser.parse_args()
    local = Path(__file__).resolve().parent
    report = {'pin': PIN, 'scope': 'Actual pinned/patched HTTP route/index/proxy-init/status bodies with deterministic native execution facades; not socket/PHP/full class allocation parity', 'native_sanitizers': True, 'rust_instrumented': args.rust_sanitize, 'rust_std_instrumented': False, 'passed': False}
    with tempfile.TemporaryDirectory(prefix='swr-http-dispatch-') as temp:
        tree = Path(temp)
        archive = prepare_archive(args, tree, report)
        if not archive: write_report(args.output, report); return 1
        paths = ['src/protocol/http.cc', 'src/server/static_handler.cc']
        sides = Sides(args.source, args.archive, tree, 'thirdparty/multipart_parser.h', *paths, 'src/core/base.cc')
        if not sides.native(report, *paths): write_report(args.output, report); return 1
        protocol_signatures = ['HttpProxy *HttpProxy::create(', 'const char *get_status_message(', 'ssize_t get_package_length(', 'uint8_t get_package_length_size(', 'int dispatch_frame(']
        dependencies = tree/'dependencies.cc'; dependencies.write_text('#include "dispatch_oracle.h"\n' + body(sides.original('src/core/base.cc'), 'size_t sw_snprintf('))
        for namespace, text in [('upstream_dispatch', sides.original(paths[0])), ('candidate_dispatch', sides.selected(paths[0]))]:
            parts = ['static thread_local char http_status_message[128];']
            parts += [body(text, signature) for signature in protocol_signatures]
            extracted = tree/(namespace+'.cc'); extracted.write_text('#include "dispatch_oracle.h"\nnamespace '+namespace+' {\n'+'\n'.join(parts)+'\n}\n')
        binary = tree/'gate'
        units = [('upstream', tree/'upstream_dispatch.cc'), ('candidate', tree/'candidate_dispatch.cc'), ('candidate', local/'dispatch_gate.cc'), ('upstream', dependencies)]
        if not sides.build(binary, units, archive, report): write_report(args.output, report); return 1
        return run(binary, ['swr_v1_http_transport_route', 'swr_v1_http_unknown_status', 'swr_v1_http_proxy_auth_enabled'], args.output, report)
if __name__ == '__main__': sys.exit(main())
