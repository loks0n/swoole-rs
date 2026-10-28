#!/usr/bin/env python3
"""Multipart header filename policy through actual native callbacks and file-operation facades."""
import argparse
from pathlib import Path
import sys
import tempfile
from gate import PIN, body, add_archive_arguments, prepare_archive, Sides, engine_units, run
from tools.harness import write_report

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    add_archive_arguments(parser)
    parser.add_argument('--output', default='target/reports/http-multipart-headers.json')
    args = parser.parse_args(); local = Path(__file__).resolve().parent
    report = {'pin': PIN, 'scope': 'Actual pinned/patched multipart header field/value and cookie bodies; native append/file facades, not full parser/PHP parity', 'native_sanitizers': True, 'rust_instrumented': args.rust_sanitize, 'rust_std_instrumented': False, 'passed': False}
    with tempfile.TemporaryDirectory(prefix='swr-http-multipart-headers-') as temp:
        tree = Path(temp); path = 'src/protocol/http.cc'
        archive = prepare_archive(args, tree, report)
        if not archive: write_report(args.output, report); return 1
        sides = Sides(args.source, args.archive, tree, path, 'thirdparty/multipart_parser.h')
        if not sides.native(report, path): write_report(args.output, report); return 1
        namespaces = ['upstream_multipart_headers', 'candidate_multipart_headers']
        for namespace, text in zip(namespaces, [sides.original(path), sides.selected(path)]):
            parts = [body(text,'void parse_cookie('),body(text,'static int multipart_on_header_field('),body(text,'static int multipart_on_header_value(')]
            if 'static int http_multipart_emit(' in text: parts.insert(0,body(text,'static int http_multipart_emit('))
            if 'static auto http_cookie_scratch(' in text: parts.insert(0,body(text,'static auto http_cookie_scratch(const char *at, size_t length) -> String * {'))
            (tree/(namespace+'.inc')).write_text('namespace '+namespace+' {\n'+'\n'.join(parts)+'\n}\n')
        binary = tree/'gate'
        if not sides.build(binary, engine_units(tree, local/'multipart_headers_gate.cc', namespaces), archive, report): write_report(args.output, report); return 1
        return run(binary, ['swr_v1_http_multipart_filename', 'swr_v2_http_multipart_upload'], args.output, report)
if __name__ == '__main__': sys.exit(main())
