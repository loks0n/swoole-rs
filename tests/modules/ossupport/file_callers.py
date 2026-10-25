#!/usr/bin/env python3
"""Actual File object methods; requires an explicit pinned native library fixture."""
from archive_identity import identify,sanitizer_outcome
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--patched-file',type=Path,required=True);p.add_argument('--library',type=Path,required=True);p.add_argument('--rust-archive',type=Path,required=True);p.add_argument('--rust-asan',action='store_true');a=p.parse_args()
 out=ROOT/'target/ossupport'/('file-'+time.strftime('%Y%m%dT%H%M%S')+'-'+str(time.time_ns()));out.mkdir(parents=True)
 lib=a.library.resolve();results=[]
 for mode in ['reference','rust']:
  source=a.source/'src/os/file.cc'if mode=='reference'else a.patched_file;exe=out/mode
  cmd=['c++','-std=c++14','-O1','-g','-fsanitize=address,undefined','-DHAVE_CONFIG_H','-I'+str(a.source),'-I'+str(a.source/'include'),'-I'+str(ROOT/'native/ossupport'),str(ROOT/'tests/modules/ossupport/file_caller.cpp'),str(source),str(lib),'-Wl,-rpath,'+str(lib.parent),'-o',str(exe)]
  if sys.platform=='darwin':cmd+=['-I/opt/homebrew/opt/openssl@3/include']
  if mode=='rust':cmd+=['-DSWOOLE_RS_OSSUPPORT',str(a.rust_archive)]
  if sys.platform=='linux':cmd+=['-lpthread','-ldl','-lm']
  c=subprocess.run(cmd,capture_output=True,text=True);e=dict(mode=mode,command=cmd,compile_exit=c.returncode,compile_stdout=c.stdout,compile_stderr=c.stderr,library_path=str(lib),library_before=sha(lib))
  if c.returncode==0:
   env=dict(os.environ)
   if sys.platform=='darwin':env['DYLD_PRINT_LIBRARIES']='1'
   else:env.update(LD_DEBUG='libs',LD_DEBUG_OUTPUT=str(out/f'{mode}-loader'))
   x=subprocess.run([str(exe)],capture_output=True,text=True,env=env);trace=x.stderr if sys.platform=='darwin'else '\n'.join(z.read_text()for z in out.glob(f'{mode}-loader.*'));e.update(exit=x.returncode,stdout=x.stdout,stderr=x.stderr,sanitizer_outcome=sanitizer_outcome(x.stderr),loader_trace=trace,loaded_expected=str(lib)in trace,library_after=sha(lib));print(mode,x.returncode,x.stdout.strip())
  results.append(e)
 gate=all(e.get('exit')==0 and e.get('sanitizer_outcome')=='passed' and e.get('loaded_expected') and e['library_before']==e['library_after']for e in results)
 report=dict(gate=gate,platform=sys.platform,results=results,archive_identity=identify(a.rust_archive,a.rust_asan),limitations=['Actual File witness only, full original native/PHP inventories remain separate gates','Native sanitizer coverage is separate from explicitly verified Rust-instruction instrumentation','Explicit supplied native library is observed, not retroactively build-attested'])
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(out/'report.json');return 0 if gate else 1
if __name__=='__main__':raise SystemExit(main())
