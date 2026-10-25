#!/usr/bin/env python3
"""Prepare immutable optimized native-library consumers; measure only under a lease."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.harness import run_isolated,write_report


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepare',type=Path);p.add_argument('--core-root',type=Path);p.add_argument('--prepared',type=Path);p.add_argument('--output',type=Path,default=ROOT/'target/reports/locks-benchmark.json');a=p.parse_args()
    if a.prepare:
        if not a.core_root:p.error('--prepare requires --core-root')
        directory=a.prepare.resolve();directory.mkdir(parents=True,exist_ok=True)
        reference=a.core_root/'core-upstream';cmd=['c++','-std=c++17','-O2','-DHAVE_CONFIG_H','-I'+str(reference),'-I'+str(reference/'include'),str(Path(__file__).with_suffix('.cc')),'-L'+str(reference/'lib'),'-lswoole','-lpthread','-ldl','-o',str(directory/'benchmark')]
        subprocess.run(cmd,check=True)
        inputs={str(path.resolve()):digest(path) for path in [directory/'benchmark',reference/'lib/libswoole.so',a.core_root/'core-rust/lib/libswoole.so']}
        manifest={'inputs':inputs,'compile':cmd,'libraries':{name:str((a.core_root/('core-upstream' if name=='upstream' else 'core-rust')/'lib').resolve()) for name in ['upstream','rust']},'scope':'Actual public mutex/RW/spin APIs via separately loaded optimized native libraries; atomic32 direct intrinsic vs Rust FFI. Requires release Rust archive when building core-rust. No PHP/network/threaded-contention/global activation claim.'}
        (directory/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');return 0
    if not a.prepared:p.error('Require --prepare or --prepared')
    manifest=json.loads((a.prepared/'manifest.json').read_text())
    for path,sha in manifest['inputs'].items():
        if digest(path)!=sha:raise ValueError('Prepared artifact identity mismatch: '+path)
    report={'created_utc':datetime.now(timezone.utc).isoformat(),'manifest':manifest,'results':[],'passed':False}
    for trial in range(5):
        for workload in ['mutex','rw-read','spin','atomic32']:
            for name in (['upstream','rust'] if trial%2==0 else ['rust','upstream']):
                cmd=[str(a.prepared.resolve()/'benchmark'),workload,name,'1000000'];env={**os.environ,'LD_LIBRARY_PATH':manifest['libraries'][name]};r=run_isolated(cmd,env=env,timeout=15)
                row={'trial':trial,'engine':name,'workload':workload,'exit':r.returncode,'stderr':r.stderr};report['results'].append(row)
                if r.returncode:write_report(a.output,report);return 1
                row.update(json.loads(r.stdout))
    report['throughput_ratios']={w:statistics.median(r['nanoseconds'] for r in report['results'] if r['workload']==w and r['engine']=='upstream')/statistics.median(r['nanoseconds'] for r in report['results'] if r['workload']==w and r['engine']=='rust') for w in ['mutex','rw-read','spin','atomic32']}
    report['passed']=all(r['exit']==0 and r['checksum']==r['loops'] for r in report['results']);write_report(a.output,report);print(json.dumps(report['throughput_ratios']));return int(not report['passed'])


if __name__=='__main__':sys.exit(main())
