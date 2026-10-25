#!/usr/bin/env python3
"""Prepare immutable actual event-wrapper consumers; timings require global lease."""
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

def environment(manifest, engine):
    key = 'DYLD_LIBRARY_PATH' if sys.platform == 'darwin' else 'LD_LIBRARY_PATH'
    return {**os.environ, key: manifest['libraries'][engine]}

def identity_matches(observation, manifest, engine):
    expected = Path(manifest['images'][engine])
    return all(Path(observation[key]).resolve() == expected and sha(expected) == manifest['inputs'][str(expected)]
               for key in ['facade_library', 'core_library'])

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepare',type=Path);p.add_argument('--core-root',type=Path);p.add_argument('--openssl-root',type=Path);p.add_argument('--prepared',type=Path);p.add_argument('--output',type=Path,default=ROOT/'target/reports/wrappers-benchmark.json');a=p.parse_args()
    if a.prepare:
        if not a.core_root:p.error('--prepare requires --core-root')
        directory=a.prepare.resolve();directory.mkdir(parents=True,exist_ok=True);reference=a.core_root.resolve()/'core-upstream';binary=directory/'benchmark';cmd=['c++','-std=c++14','-O2','-DHAVE_CONFIG_H','-I'+str(reference),'-I'+str(reference/'include'),str(Path(__file__).with_suffix('.cc')),'-L'+str(reference/'lib'),'-Wl,-rpath,'+str(reference/'lib'),'-lswoole','-lpthread','-o',str(binary)]
        if a.openssl_root:cmd[1:1]=['-I'+str(a.openssl_root/'include'),'-L'+str(a.openssl_root/'lib')]
        if sys.platform == 'linux':cmd.append('-ldl')
        subprocess.run(cmd,check=True)
        extension = 'dylib' if sys.platform == 'darwin' else 'so'
        images={n:str((a.core_root/('core-'+n)/('lib/libswoole.'+extension)).resolve()) for n in ['upstream','rust']}
        inputs={str(path.resolve()):sha(path) for path in [binary,*map(Path,images.values())]}
        manifest={'version':2,'inputs':inputs,'images':images,'platform':sys.platform,'compile':cmd,'libraries':{n:str((a.core_root/('core-'+n)/'lib').resolve()) for n in ['upstream','rust']},'scope':'Public event add-or-update/read/write wrapper calls, mainly idempotent admission on an existing real reactor/socket registration. Does not measure HTTP state, PHP, timers or complete activation readiness. Preparation checks do not read the clock. Library hashes do not establish optimized build-profile provenance.'}
        manifest['preflight']=[]
        for name in ['upstream','rust']:
            r=run_isolated([str(binary),'check'],env=environment(manifest,name),timeout=15)
            row={'engine':name,'exit':r.returncode,'stderr':r.stderr};manifest['preflight'].append(row)
            if r.returncode:raise ValueError('Clock-free preparation failed: '+str(row))
            row.update(json.loads(r.stdout))
            row['identity_verified']=identity_matches(row,manifest,name)
            row['wrong_engine_rejected']=not identity_matches(row,manifest,'rust' if name=='upstream' else 'upstream')
            if not row['identity_verified'] or not row['wrong_engine_rejected'] or row['nanoseconds']!=0 or row['operations']!=2 or row['errors']!=0:raise ValueError('Invalid clock-free preparation: '+str(row))
        (directory/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps({'prepared':str(directory),'preflight':manifest['preflight'],'timings_run':False}));return 0
    if not a.prepared:p.error('Require --prepare or --prepared')
    manifest=json.loads((a.prepared/'manifest.json').read_text())
    if manifest.get('version')!=2 or manifest.get('platform')!=sys.platform:raise ValueError('Reprepare on this platform with library identity verification')
    for path,digest in manifest['inputs'].items():
        if sha(path)!=digest:raise ValueError('Prepared input identity changed: '+path)
    report={'created_utc':datetime.now(timezone.utc).isoformat(),'manifest':manifest,'results':[],'passed':False}
    for trial in range(5):
        for engine in (['upstream','rust'] if trial%2==0 else ['rust','upstream']):
            r=run_isolated([str(a.prepared.resolve()/'benchmark'),'100000'],timeout=15,env=environment(manifest,engine));row={'trial':trial,'engine':engine,'exit':r.returncode,'stderr':r.stderr};report['results'].append(row)
            if r.returncode:write_report(a.output,report);return 1
            row.update(json.loads(r.stdout))
            row['identity_verified']=identity_matches(row,manifest,engine)
            if not row['identity_verified']:write_report(a.output,report);return 1
    report['throughput_ratio']=statistics.median(r['nanoseconds'] for r in report['results'] if r['engine']=='upstream')/statistics.median(r['nanoseconds'] for r in report['results'] if r['engine']=='rust');report['passed']=all(r['errors']==0 and r['operations']==200000 for r in report['results']);write_report(a.output,report);print(json.dumps({'passed':report['passed'],'ratio':report['throughput_ratio']}));return int(not report['passed'])
if __name__=='__main__':sys.exit(main())
