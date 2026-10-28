#!/usr/bin/env python3
"""Differential HTTP header metadata/cookie callback checks with deterministic native facades."""
import argparse
from pathlib import Path
import sys
import tempfile
from gate import PIN, body, Sides, run
from tools.harness import write_report

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', default='target/reports/http-headers.json')
    args = parser.parse_args(); local = Path(__file__).resolve().parent
    report = {'pin': PIN, 'scope': 'Actual pinned/patched header-info/cookie bodies with native allocation/callback facades; not full server/PHP parity', 'native_sanitizers': True, 'rust_instrumented': False}
    with tempfile.TemporaryDirectory(prefix='swr-http-headers-') as temp:
        tree = Path(temp); path = 'src/protocol/http.cc'
        sides = Sides(args.source, args.archive, tree, 'thirdparty/multipart_parser.h', path)
        if not sides.native(report, path): write_report(args.output, report); return 1
        for namespace, text in [('upstream_headers', sides.original(path)), ('candidate_headers', sides.selected(path))]:
            methods = body(text, 'void Request::parse_header_info(')+'\n'+body(text, 'void parse_cookie(')
            if 'static auto http_cookie_scratch(' in text: methods = body(text, 'static auto http_cookie_scratch(const char *at, size_t length) -> String * {')+'\n'+methods
            if 'int http_no_digits_errno(' in text: methods = body(text, 'int http_no_digits_errno(')+'\n'+methods
            extracted = tree/(namespace+'.cc'); extracted.write_text('#include "headers_oracle.h"\nnamespace '+namespace+' {\n'+methods+'\n}\n')
        binary = tree/'gate'
        units = [('upstream', tree/'upstream_headers.cc'), ('candidate', tree/'candidate_headers.cc'), ('candidate', local/'headers_gate.cc')]
        if not sides.build(binary, units, args.archive.resolve(), report): write_report(args.output, report); return 1
        return run(binary, ['swr_v1_http_cookie_next'], args.output, report)
if __name__ == '__main__': sys.exit(main())
