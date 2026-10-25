#!/usr/bin/env python3
"""Genuine target C kernel-array cursor/decode and POD layout, positive records only."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from ordered_gate import ROOT

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--archive',type=Path,required=True)
p.add_argument('--report',type=Path,required=True)
p.add_argument('--sanitize',action='store_true')
a=p.parse_args()
with tempfile.TemporaryDirectory(prefix='swr-batch-') as temporary:
    binary=Path(temporary)/'batch'
    fixture=ROOT/'tests/modules/reactor/batch.cc'
    command=['c++','-std=c++14','-O1','-g','-I'+str(ROOT/'native/reactor'),str(fixture),str(a.archive.resolve()),'-lpthread','-o',str(binary)]
    if a.sanitize:command+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    if sys.platform.startswith('linux'):command+=['-ldl','-lm']
    r=subprocess.run(command,text=True,capture_output=True)
    report=dict(scope=__doc__,platform=sys.platform,command=command,compile_returncode=r.returncode,compile_stdout=r.stdout,compile_stderr=r.stderr)
    if r.returncode==0:
        r=subprocess.run([str(binary)],text=True,capture_output=True)
        report.update(returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)
        if r.returncode==0:report['observations']=json.loads(r.stdout)
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['compile_returncode','observations'] if k in report}))
    raise SystemExit(r.returncode)
