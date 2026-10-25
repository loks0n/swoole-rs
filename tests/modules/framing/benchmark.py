#!/usr/bin/env python3
"""Prepare immutable actual framing/MIME consumers; timings require global lease."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import os
import statistics
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.harness import run_isolated,write_report

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepare',type=Path);p.add_argument('--core-root',type=Path);p.add_argument('--prepared',type=Path);p.add_argument('--output',type=Path,default=ROOT/'target/reports/framing-benchmark.json');a=p.parse_args()
    if a.prepare:
        if not a.core_root:p.error('--prepare requires --core-root')
        directory=a.prepare.resolve();directory.mkdir(parents=True,exist_ok=True);reference=a.core_root/'core-upstream';binary=directory/'benchmark';cmd=['c++','-std=c++14','-O2','-DHAVE_CONFIG_H','-I'+str(reference),'-I'+str(reference/'include'),str(Path(__file__).with_suffix('.cc')),'-L'+str(reference/'lib'),'-lswoole','-lpthread','-o',str(binary)];subprocess.run(cmd,check=True)
        for name in ['upstream','rust']:
            for kind in ['length','length-large','eof','eof-large','mime','unpack']:
                subprocess.run([str(binary),kind,'check'],env={**os.environ,'LD_LIBRARY_PATH':str(a.core_root/('core-'+name)/'lib')},check=True)
        inputs={str(path.resolve()):sha(path) for path in [binary,reference/'lib/libswoole.so',a.core_root/'core-rust/lib/libswoole.so']}
        manifest={'inputs':inputs,'compile':cmd,'libraries':{n:str((a.core_root/('core-'+n)/'lib').resolve()) for n in ['upstream','rust']},'scope':'Optimized real native length skip-recv batched dispatch, direct EOF split, MIME lookup and unpack consumers. Excludes IO, PHP and whole-server throughput.'};(directory/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');return 0
    if not a.prepared:p.error('Require --prepare or --prepared')
    manifest=json.loads((a.prepared/'manifest.json').read_text())
    for path,digest in manifest['inputs'].items():
        if sha(path)!=digest:raise ValueError('Prepared input identity changed: '+path)
    report={'created_utc':datetime.now(timezone.utc).isoformat(),'manifest':manifest,'results':[],'passed':False}
    for kind in ['length','length-large','eof','eof-large','mime','unpack']:
        for trial in range(5):
            for engine in (['upstream','rust'] if trial%2==0 else ['rust','upstream']):
                r=run_isolated([str(a.prepared.resolve()/'benchmark'),kind,'2000' if kind.endswith('large') else '100000'],timeout=30,env={**os.environ,'LD_LIBRARY_PATH':manifest['libraries'][engine]});row={'workload':kind,'trial':trial,'engine':engine,'exit':r.returncode,'stderr':r.stderr};report['results'].append(row)
                if r.returncode:write_report(a.output,report);return 1
                row.update(json.loads(r.stdout))
    report['throughput_ratios']={kind:statistics.median(r['nanoseconds'] for r in report['results'] if r['workload']==kind and r['engine']=='upstream')/statistics.median(r['nanoseconds'] for r in report['results'] if r['workload']==kind and r['engine']=='rust') for kind in ['length','length-large','eof','eof-large','mime','unpack']}
    report['passed']=all(r['errors']==0 and r['operations']==(1600000 if r['workload']=='unpack' else 16000 if r['workload'].endswith('large') else 800000) for r in report['results'])
    write_report(a.output,report);print(json.dumps({'passed':report['passed'],'ratios':report['throughput_ratios']}));return int(not report['passed'])

if __name__=='__main__':sys.exit(main())
