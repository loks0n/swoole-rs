#!/usr/bin/env python3
"""Dependency-free Rust/native differential gate; private outputs, no ports or IPC."""
from archive_identity import identify,sanitizer_outcome
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    parser.add_argument('--archive', type=Path, help='Exact selected FFI static archive; never rebuild when supplied')
    parser.add_argument('--rust-asan', action='store_true', help='Require actual Rust load/store sanitizer imports in selected archive')
    args = parser.parse_args()
    if args.rust_asan and not args.archive:
        parser.error('--rust-asan requires --archive')
    stamp = time.strftime('%Y%m%dT%H%M%S') + '-' + str(time.time_ns())
    out = ROOT / 'target/ossupport' / stamp
    out.mkdir(parents=True)
    source = ROOT / 'crates/ossupport/src/lib.rs'
    archive = args.archive.resolve(strict=True) if args.archive else out / 'libswoole_rs_ossupport.a'
    commands = [
        ['rustc','--edition','2024','--test',str(source),'-o',str(out/'rust-tests')],
        [str(out/'rust-tests')],
        ['rustc','--edition','2024','--crate-type','staticlib','-C','opt-level=2',str(source),'-o',str(archive)],
        ['c++','-std=c++14','-O2','-fsanitize=address,undefined','-I'+str(ROOT/'native/ossupport'),str(ROOT/'tests/modules/ossupport/differential.cpp'),str(archive),'-o',str(out/'differential')],
        [str(out/'differential')],
    ]
    if args.archive:
        commands = commands[3:]
    if sys.platform == 'linux':
        commands[0 if args.archive else 3] += ['-lpthread','-ldl','-lm']
    queue_command = ['c++','-std=c++14','-O1','-g','-fsanitize=address,undefined','-I'+str(ROOT/'native/ossupport'),str(ROOT/'tests/modules/ossupport/queue.cpp'),str(archive),'-o',str(out/'queue')]
    if sys.platform == 'linux':
        queue_command += ['-lpthread','-ldl','-lm']
    commands += [queue_command, [str(out/'queue')]]
    runs=[]
    for cmd in commands:
        run=subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True)
        runs.append(dict(command=cmd,exit=run.returncode,stdout=run.stdout,stderr=run.stderr,sanitizer_outcome=sanitizer_outcome(run.stderr)))
        if run.returncode:break
    report=dict(schema_version=1,gate=all(r['exit']==0 and r['sanitizer_outcome']=='passed' for r in runs) and len(runs)==len(commands),platform=sys.platform,runs=runs,
                selected_archive=bool(args.archive),
                archive_identity=identify(archive,args.rust_asan) if archive.exists() else None,
                gaps=['Original native/PHP full inventories UNRUN by this policy gate','Native harness ASan/UBSan is separate from explicitly verified Rust-instruction instrumentation','No activation, performance or full-platform claim'])
    target=args.output or out/'report.json'
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():raise SystemExit('refusing to overwrite original report')
    target.write_text(json.dumps(report,indent=2)+'\n')
    print(target)
    return 0 if report['gate'] else 1

if __name__=='__main__':raise SystemExit(main())
