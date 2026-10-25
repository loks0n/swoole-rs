#!/usr/bin/env python3
"""Actual pinned sendfile body with deterministic native syscall fault injection."""
from archive_identity import identify,sanitizer_outcome
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--patched-source',type=Path,required=True);p.add_argument('--library',type=Path,required=True);p.add_argument('--rust-archive',type=Path,required=True);p.add_argument('--rust-asan',action='store_true');a=p.parse_args()
 out=ROOT/'target/ossupport'/('sendfile-'+str(time.time_ns()));out.mkdir(parents=True);lib=a.library.resolve(strict=True);before=sha(lib);rows=[]
 for mode in ['reference','rust']:
  source=a.source/'src/os/sendfile.cc'if mode=='reference'else a.patched_source;exe=out/mode
  cmd=['c++','-std=c++14','-O1','-g','-fsanitize=address,undefined','-DHAVE_CONFIG_H','-I'+str(a.source),'-I'+str(a.source/'include'),'-I'+str(ROOT/'native/ossupport'),str(ROOT/'tests/modules/ossupport/sendfile_caller.cpp'),str(source),str(lib),'-Wl,-rpath,'+str(lib.parent),'-o',str(exe)]
  if sys.platform=='darwin':cmd+=['-I/opt/homebrew/opt/openssl@3/include']
  if mode=='rust':cmd+=['-DSWOOLE_RS_OSSUPPORT',str(a.rust_archive)]
  if sys.platform=='linux':cmd+=['-lpthread','-ldl','-lm']
  c=subprocess.run(cmd,text=True,capture_output=True);row=dict(mode=mode,command=cmd,compile_exit=c.returncode,compile_stderr=c.stderr,library_before=sha(lib),status='failed')
  if c.returncode==0:
   env=dict(os.environ)
   if sys.platform=='darwin':env['DYLD_PRINT_LIBRARIES']='1'
   probe=subprocess.run([str(exe)]if sys.platform=='darwin'else['ldd',str(exe)],text=True,capture_output=True,env=env,timeout=30);trace=probe.stdout+probe.stderr
   pattern=r'^dyld\[\d+\]: (?:<[^>]+> )?(/.*libswoole[^/]*\.dylib)\s*$'if sys.platform=='darwin'else r'^\s*libswoole[^ ]* => (/.*libswoole[^/ ]*) \(0x[0-9a-fA-F]+\)'
   loaded={str(Path(v).resolve(strict=True))for v in re.findall(pattern,trace,re.M)};r=subprocess.run([str(exe)],text=True,capture_output=True,timeout=30);row.update(loader_trace=trace,loader_exit=probe.returncode,loaded_paths=sorted(loaded),loaded_expected=loaded=={str(lib)},exit=r.returncode,stdout=r.stdout,stderr=r.stderr,sanitizer_outcome=sanitizer_outcome(r.stderr))
   if probe.returncode==0 and row['loaded_expected'] and r.returncode==0:row['status']=row['sanitizer_outcome']
  row['library_after']=sha(lib)
  if row['library_before']!=before or row['library_after']!=before:row['status']='failed'
  rows.append(row)
 report=dict(platform=sys.platform,gate=all(r['status']=='passed'for r in rows),results=rows,library_path=str(a.library),resolved_library_path=str(lib),archive_identity=identify(a.rust_archive,a.rust_asan),scope='Actual original/patched sendfile body, deterministic native OS boundary stub; harness ASan/UBSan does not instrument ordinary Rust archives.',gaps=['No real kernel transfer or M15 caller claim','Linux direct native syscall has no added Rust policy','BSD/fallback variants UNRUN','No full platform/activation/performance claim'])
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(out/'report.json');return int(not report['gate'])
if __name__=='__main__':raise SystemExit(main())
