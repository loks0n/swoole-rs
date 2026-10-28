#!/usr/bin/env python3
"""Normal fully initialized native core Request multipart resource caller controls."""
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
    parser.add_argument('--output', default='target/reports/http-request-lifecycle.json')
    args = parser.parse_args(); local = Path(__file__).resolve().parent
    report = {'pin': PIN, 'scope': 'Actual pinned/patched Request init/destroy/destructor with normal fully initialized parser/buffer/stdio/virtual-unlink facades and empty request; not third-party parser/PHP/error/reentry/lifetime parity', 'native_sanitizers': True, 'rust_instrumented': args.rust_sanitize, 'rust_std_instrumented': False, 'passed': False, 'full_gate_passed': False, 'unrun_profiles': ['partial/failed initialization and original cleanup limitations', 'allocation/parser/stdio/unlink failures', 'callback/reentry/response/context/coroutine/process lifetimes', 'full third-party parser and original PHP/runtime', 'performance']}

    with tempfile.TemporaryDirectory(prefix='swr-http-request-lifecycle-') as temp:
        tree = Path(temp); path = 'src/protocol/http.cc'
        archive = prepare_archive(args, tree, report)
        if not archive: write_report(args.output, report); return 1
        sides = Sides(args.source, args.archive, tree, 'thirdparty/multipart_parser.h', path)
        if not sides.native(report, path): write_report(args.output, report); return 1
        for namespace, text in [('upstream_request_lifecycle', sides.original(path)), ('candidate_request_lifecycle', sides.selected(path))]:
            extracted = tree/(namespace+'.cc'); parts = [body(text, signature) for signature in ['bool Request::init_multipart_parser(', 'void Request::destroy_multipart_parser(', 'Request::~Request()']]
            extracted.write_text('#include "request_lifecycle_oracle.h"\nnamespace '+namespace+' {\n'+'\n'.join(parts)+'\n}\n')
        binary = tree/'gate'
        units = [('upstream', tree/'upstream_request_lifecycle.cc'), ('candidate', tree/'candidate_request_lifecycle.cc'), ('candidate', local/'request_lifecycle_gate.cc')]
        if not sides.build(binary, units, archive, report): write_report(args.output, report); return 1
        return run(binary, ['swr_v1_http_request_lifecycle'], args.output, report)
if __name__ == '__main__': sys.exit(main())
