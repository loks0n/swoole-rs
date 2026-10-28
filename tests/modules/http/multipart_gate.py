#!/usr/bin/env python3
"""Multipart upload policy comparison through actual native callbacks and stdio boundaries."""
import argparse
from pathlib import Path
import sys
import tempfile
from gate import PIN, body, Sides, engine_units, run
from tools.harness import write_report

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', default='target/reports/http-multiparts.json')
    args = parser.parse_args(); local = Path(__file__).resolve().parent
    report = {'pin': PIN, 'scope': 'Actual pinned/patched multipart_on_data and parse_multipart_data; counted parser/storage/logging and actual stdio cases, not full PHP/parser parity', 'native_sanitizers': True, 'rust_instrumented': False}
    with tempfile.TemporaryDirectory(prefix='swr-http-multipart-') as temp:
        tree = Path(temp); path = 'src/protocol/http.cc'
        sides = Sides(args.source, args.archive, tree, path, 'thirdparty/multipart_parser.h')
        if not sides.native(report, path): write_report(args.output, report); return 1
        namespaces = ['upstream_multipart', 'candidate_multipart']
        for namespace, text in zip(namespaces, [sides.original(path), sides.selected(path)]):
            parts = [body(text,'static int multipart_on_data('),body(text,'bool Request::parse_multipart_data(')]
            (tree/(namespace+'.inc')).write_text('namespace '+namespace+' {\n'+'\n'.join(parts)+'\n}\n')
        binary = tree/'gate'
        if not sides.build(binary, engine_units(tree, local/'multipart_gate.cc', namespaces), args.archive.resolve(), report): write_report(args.output, report); return 1
        return run(binary, ['swr_v1_http_multipart_data'], args.output, report)
if __name__ == '__main__': sys.exit(main())
