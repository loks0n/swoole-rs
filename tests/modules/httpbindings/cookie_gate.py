#!/usr/bin/env python3
"""Compare actual pinned/patched Cookie::toString with ordered native facades."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'http'))
from gate import PIN
from source import definition as body
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, run_isolated, write_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    archive = parser.add_mutually_exclusive_group(required=True)
    archive.add_argument('--archive', type=Path)
    archive.add_argument('--rust-sanitize', action='store_true', help='Instrument this Rust policy with ASan; precompiled std is uninstrumented')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    local = Path(__file__).resolve().parent
    patch = ROOT/'migration/patches/httpbindings/0001-cookie-policy.patch'
    header = ROOT/'native/httpbindings/swoole_rs_httpbindings.h'
    report = {'pin': PIN, 'scope': __doc__, 'limitations': 'Native PHP/Zend facades observe ordering, failures, reentry and self-deletion; fake date/encoding/allocation effects are not real Zend GC/bailout/PHP or complete binding parity.',
              'native_sanitizers': True, 'rust_instrumented': args.rust_sanitize, 'rust_std_instrumented': False,
              'passed': False}
    with tempfile.TemporaryDirectory(prefix='swr-httpbindings-cookie-') as temp:
        tree = Path(temp)
        if args.rust_sanitize:
            args.archive = tree/'libhttpbindings-asan.a'
            command = ['rustc', '--edition=2024', '-Zsanitizer=address', '--crate-type=staticlib', '-C', 'opt-level=3', '-C', 'panic=abort', str(ROOT/'crates/httpbindings/src/lib.rs'), '-o', str(args.archive)]
            compiled = run_isolated(command, timeout=60, env={**os.environ, 'RUSTC_BOOTSTRAP': '1'})
            report['rust_compile'] = {'command': command, 'returncode': compiled.returncode, 'stdout': compiled.stdout, 'stderr': compiled.stderr}
            if compiled.returncode:
                write_report(args.output, report)
                return 1
        source = tree/'ext-src/swoole_http_cookie.cc';source.parent.mkdir()
        source.write_bytes(subprocess.check_output(['git','-C',str(args.source),'show',PIN+':ext-src/swoole_http_cookie.cc']))
        original = source.read_text()
        subprocess.run(['git','apply','--check',str(patch)],cwd=tree,check=True)
        subprocess.run(['git','apply',str(patch)],cwd=tree,check=True)
        for namespace,text in [('upstream_cookie',original),('candidate_cookie',source.read_text())]:
            p=tree/(namespace+'.cc')
            p.write_text('#include "cookie_oracle.h"\nnamespace '+namespace+' {\n'+body(text,'zend_string *HttpCookie::toString(')+'\n}\n')
        binary=tree/'gate'
        command=['c++','-std=c++14','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(local),'-I'+str(header.parent),str(tree/'upstream_cookie.cc'),str(tree/'candidate_cookie.cc'),str(local/'cookie_gate.cc'),str(args.archive.resolve()),'-lm','-o',str(binary)]
        if sys.platform.startswith('linux'):command+=['-ldl','-lpthread','-lrt','-lutil']
        report['compile_command']=command
        compiled=run_isolated(command,timeout=60);report['compile']={'returncode':compiled.returncode,'stdout':compiled.stdout,'stderr':compiled.stderr}
        if not compiled.returncode:
            assert 'swr_v1_httpbindings_cookie' in subprocess.check_output(['nm','-g',str(binary)],text=True)
            result=run_isolated([str(binary)],timeout=60);report['run']={'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
            if not result.returncode:report['outcome']=json.loads(result.stdout.splitlines()[-1]);report['passed']=True
        write_report(args.output,report)
        if not report['passed']:print(json.dumps(report.get('run',report['compile'])),file=sys.stderr)
        return 0 if report['passed'] else 1


if __name__=='__main__':sys.exit(main())
