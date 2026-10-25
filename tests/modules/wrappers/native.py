#!/usr/bin/env python3
"""Compare actual native HTTP wrapper API and file cleanup, one process per case."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.harness import run_isolated,write_report

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--openssl-root',type=Path);p.add_argument('--core-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    report={'scope':__doc__,'platform':sys.platform,'results':[],'engines':[],'passed':False}
    try:
        for name in ['upstream','rust']:
            tree=a.core_root/('core-'+name);binary=a.output.resolve().with_suffix('')/name/'wrapper-witness';cmd=['c++','-std=c++14','-O2','-UNDEBUG','-DHAVE_CONFIG_H','-I'+str(tree),'-I'+str(tree/'include'),str(Path(__file__).with_suffix('.cc')),'-L'+str(tree/'lib'),'-Wl,-rpath,'+str(tree/'lib'),'-lswoole','-lpthread','-o',str(binary)]
            if sys.platform=='linux':cmd.append('-ldl')
            if a.openssl_root:cmd[1:1]=['-I'+str(a.openssl_root/'include'),'-L'+str(a.openssl_root/'lib')]
            binary.parent.mkdir(parents=True,exist_ok=True)
            expected=(tree/('lib/libswoole.dylib' if sys.platform=='darwin' else 'lib/libswoole.so')).resolve()
            meta={'expected_library':str(expected),'engine':name,'compile':cmd,'library_sha256':digest(tree/('lib/libswoole.dylib' if sys.platform=='darwin' else 'lib/libswoole.so'))};report['engines'].append(meta)
            r=run_isolated(cmd,timeout=90);meta.update(compile_exit=r.returncode,compile_stderr=r.stderr)
            if r.returncode:raise RuntimeError('Native witness compile failed: '+r.stderr)
            for scenario in ['get','empty-query','form','multipart','file']:
                r=run_isolated([str(binary),scenario],timeout=30,env={**os.environ,'VERBOSE':'0'});row={'engine':name,'scenario':scenario,'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'status':'failed'};report['results'].append(row)
                loaded=[s.split('=',1)[1] for s in r.stderr.splitlines() if s.startswith('SWR_WRAPPER_LIBRARY=')]
                row['loaded_library_verified']=len(loaded)==1 and Path(loaded[0]).resolve()==expected
                if len(loaded)==1:
                    actual=Path(loaded[0]).resolve();row['loaded_library']=str(actual)
                    if actual.is_file():row['loaded_library_sha256']=digest(actual)
                row['loaded_library_verified']=row['loaded_library_verified'] and row.get('loaded_library_sha256')==meta['library_sha256']
                core=[s.split('=',1)[1] for s in r.stderr.splitlines() if s.startswith('SWR_CORE_LIBRARY=')]
                row['loaded_core_verified']=len(core)==1 and Path(core[0]).resolve()==expected and digest(Path(core[0]).resolve())==meta['library_sha256']
                if len(core)==1:row['loaded_core_library']=str(Path(core[0]).resolve())
                row['loaded_library_verified']=row['loaded_library_verified'] and row['loaded_core_verified']
                if r.returncode==0 and row['loaded_library_verified']:
                    row['observations']=json.loads(r.stdout.strip().splitlines()[-1]);row['status']='passed'
                write_report(a.output,report)
        rows=report['results'];report['loaded_libraries_verified']=len(rows)==10 and all(r.get('loaded_library_verified') for r in rows);report['observations_match']=all(rows[i].get('observations')==rows[i+5].get('observations') for i in range(5));report['passed']=report['observations_match'] and all(r['status']=='passed' for r in rows)
    except Exception as e:report['error']=str(e)
    write_report(a.output,report);print(json.dumps(report));return int(not report['passed'])
if __name__=='__main__':sys.exit(main())
