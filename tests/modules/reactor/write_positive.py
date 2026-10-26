#!/usr/bin/env python3
"""Pinned/selected complete write_func, ordinary successful existing-buffer controls.

No Native allocation path, error/fault, callback reentry/lifetime or network probe.
Does not replace historical write_gate or establish broad write/Socket parity.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from ordered_gate import ROOT,PIN,block, apply_patch_verified
from poll_snapshot import digest
from tools.build_upstream import require_build_space
from tools.harness import run_compiler


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--sanitize',action='store_true')
    parser.add_argument('--workflow',action='store_true',help='Separate full positive setup/observation trace and additive ABI profile')
    args=parser.parse_args()
    if args.report.exists():raise ValueError('Choose a unique new receipt path')
    fixture=ROOT/'tests/modules/reactor'/('write_workflow.cc' if args.workflow else 'write_positive.cc')
    manifest=ROOT/'migration/patches/reactor/manifest.json';entries=json.loads(manifest.read_text())['patches']
    original=subprocess.check_output(['git','-C',str(args.source),'show',PIN+':src/reactor/base.cc'],text=True)
    with tempfile.TemporaryDirectory(prefix='swr-write-positive-') as temporary:
        tree=Path(temporary)
        for entry in entries:
            for name in entry['upstream_paths']:
                path=tree/name
                if not path.exists():
                    path.parent.mkdir(parents=True,exist_ok=True)
                    path.write_bytes(subprocess.check_output(['git','-C',str(args.source),'show',PIN+':'+name]))
        patches=[]
        for entry in entries:
            patch=manifest.parent/entry['path']
            if digest(patch)!=entry['sha256']:raise ValueError('Overlay checksum mismatch')
            application = apply_patch_verified(tree, patch, entry['upstream_paths'], entry['sha256'])
            patches.append(dict(path=entry['path'],application=application))
        selected=(tree/'src/reactor/base.cc').read_text();fragments=[]
        for label,text in [('Original',original),('Selected',selected)]:
            name='Write'+label;body,_=block(text,text.index('ssize_t Reactor::write_func('));body=body.replace('Reactor::','').replace('const Reactor *','const '+name+' *')
            fragments.append('struct '+name+' { int add_write_event(Socket *socket) const { effects.emplace_back("add-write"); socket->writable=true; return SW_OK; } static '+body+' };')
        (tree/'write-positive.inc').write_text('\n'.join(fragments))
        binary=tree/'write-positive'
        command=['c++','-std=c++14','-O1','-g','-I'+str(tree),'-I'+str(ROOT/'native/reactor'),str(fixture),str(args.archive.resolve()),'-lpthread','-o',str(binary)]
        if args.sanitize:command+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
        if sys.platform.startswith('linux'):command+=['-ldl','-lm']
        require_build_space(ROOT);require_build_space(tree)
        compiled=run_compiler(command, timeout=60)
        result=subprocess.CompletedProcess(command,compiled['returncode'],compiled['stdout'],compiled['stderr'])
        report=dict(workflow_profile=args.workflow,pin=PIN,scope=__doc__,patches=patches,command=command,compile_returncode=result.returncode,compile_stdout=result.stdout,compile_stderr=result.stderr)
        if result.returncode==0:
            require_build_space(ROOT);require_build_space(tree)
            result=subprocess.run([str(binary)],capture_output=True,text=True);report.update(returncode=result.returncode,stdout=result.stdout,stderr=result.stderr)
            if result.returncode==0:report['observations']=json.loads(result.stdout)
        args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({key:report[key] for key in ['compile_returncode','observations'] if key in report}));return result.returncode


if __name__=='__main__':raise SystemExit(main())
