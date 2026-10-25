#!/usr/bin/env python3
"""Actual whole-native-library worker consumers, without source interposition."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from archive_identity import sanitizer_outcome
ROOT=Path(__file__).resolve().parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def identity(p):return dict(path=str(p),resolved_path=str(p.resolve(strict=True)),sha256=sha(p))
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--engine',action='append',required=True);p.add_argument('--output',type=Path);p.add_argument('--idle',choices=['0','0.5'],default='0.5',help='Original fractional retirement case by default;0 is an explicitly separate no-retirement diagnostic');a=p.parse_args()
 if a.output and a.output.exists():p.error('Refusing existing report')
 out=ROOT/'target/ossupport'/('async-lifetime-'+str(time.time_ns()));out.mkdir(parents=True)
 report=dict(platform=sys.platform,idle_seconds=a.idle,results=[],scope='Full supplied native library executes async methods; fixture has no private class layout or source interposition. ASan/UBSan instrument harness only, not supplied native/Rust library internals. Reference library identity observed, original build provenance not reattested.',gaps=['No racing canceled mutation or native plain-running/thread-map proof','No queued shutdown payload ownership correction','Whole original/optional-platform/performance gates remain open'])
 for specification in a.engine:
  name,value=specification.split('=',1);lib=Path(value).resolve(strict=True);before=identity(lib);exe=out/(name+'-caller')
  command=['c++','-std=c++14','-O1','-g','-fsanitize=address,undefined','-DHAVE_CONFIG_H','-I'+str(a.source),'-I'+str(a.source/'include'),str(ROOT/'tests/modules/ossupport/async_lifetime.cpp'),str(lib),'-Wl,-rpath,'+str(lib.parent),'-o',str(exe)]
  if sys.platform=='darwin':command+=['-I/opt/homebrew/opt/openssl@3/include']
  else:command+=['-lpthread','-ldl','-lm']
  c=subprocess.run(command,text=True,capture_output=True);row=dict(engine=name,command=command,compile_exit=c.returncode,compile_stdout=c.stdout,compile_stderr=c.stderr,library_before=before,status='failed')
  if c.returncode==0:
   env=dict(os.environ)
   if sys.platform=='darwin':env['DYLD_PRINT_LIBRARIES']='1'
   probe=subprocess.run([str(exe),a.idle]if sys.platform=='darwin'else['ldd',str(exe)],text=True,capture_output=True,env=env,timeout=60);trace=probe.stdout+probe.stderr
   if sys.platform=='darwin':paths=re.findall(r'^dyld\[\d+\]: (?:<[^>]+> )?(/.*libswoole[^/]*\.dylib)\s*$',trace,re.M)
   else:paths=re.findall(r'^\s*libswoole[^ ]* => (/.*libswoole[^/ ]*) \(0x[0-9a-fA-F]+\)',trace,re.M)
   loaded={str(Path(v).resolve(strict=True))for v in paths};row.update(loader_trace=trace,loader_exit=probe.returncode,loaded_paths=sorted(loaded),loaded_expected=loaded=={before['resolved_path']})
   run=subprocess.run([str(exe),a.idle],text=True,capture_output=True,timeout=60);row.update(exit=run.returncode,stdout=run.stdout,stderr=run.stderr,sanitizer_outcome=sanitizer_outcome(run.stderr))
   if row['loaded_expected'] and probe.returncode==0 and run.returncode==0:row['status']=row['sanitizer_outcome']
  row['library_after']=identity(lib)
  if row['library_after']!=before:row['status']='failed'
  report['results'].append(row)
 report['gate']=all(r['status']=='passed'for r in report['results']);dest=a.output or out/'report.json';dest.write_text(json.dumps(report,indent=2)+'\n');print(dest);return int(not report['gate'])
if __name__=='__main__':raise SystemExit(main())
