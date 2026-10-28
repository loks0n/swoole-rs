#!/usr/bin/env python3
"""Static rewrite classification and real native regex/literal caller compatibility."""
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
    parser.add_argument('--output', default='target/reports/http-rewrites.json')
    args = parser.parse_args(); local = Path(__file__).resolve().parent
    report = {'pin': PIN, 'scope': 'Actual pinned/patched add_rewrite_rule/apply_rewrite_rules; native regex/std::string facade upstream, the Rust static context selected; not socket/PHP parity', 'native_sanitizers': True, 'rust_instrumented': args.rust_sanitize, 'rust_std_instrumented': False, 'passed': False}
    with tempfile.TemporaryDirectory(prefix='swr-http-rewrite-') as temp:
        tree = Path(temp); path = 'src/server/static_handler.cc'
        archive = prepare_archive(args, tree, report)
        if not archive: write_report(args.output, report); return 1
        sides = Sides(args.source, args.archive, tree, path)
        if not sides.native(report, path): write_report(args.output, report); return 1
        for namespace, text in [('upstream_rewrite', sides.original(path)), ('candidate_rewrite', sides.selected(path))]:
            extracted = tree/(namespace+'.cc'); parts = [body(text, 'void Server::add_rewrite_rule('),body(text, 'bool Server::apply_rewrite_rules(')]
            extracted.write_text('#include "rewrite_oracle.h"\nnamespace '+namespace+' {\n'+'\n'.join(parts)+'\n}\n')
        binary = tree/'gate'
        units = [('upstream', tree/'upstream_rewrite.cc'), ('candidate', tree/'candidate_rewrite.cc'), ('candidate', local/'rewrite_gate.cc')]
        if not sides.build(binary, units, archive, report): write_report(args.output, report); return 1
        return run(binary, ['swr_v1_http_rewrite_rule', 'swr_v2_http_context_rewrite_step'], args.output, report)
if __name__ == '__main__': sys.exit(main())
