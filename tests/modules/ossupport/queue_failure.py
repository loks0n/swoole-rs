#!/usr/bin/env python3
"""Actual native queue facade with identified test-only Rust allocator failure."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from archive_identity import identify,sanitizer_outcome
ROOT=Path(__file__).resolve().parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True,help='Coherent selected native SDK, including actual patched async_thread.cc');p.add_argument('--library',type=Path,required=True);p.add_argument('--rust-asan',action='store_true');a=p.parse_args();out=ROOT/'target/ossupport'/('queue-failure-'+str(time.time_ns()));out.mkdir(parents=True)
 report=dict(platform=sys.platform,gate=False,runs=[],scope='Exact selected TU/facade and coherent supplied private-layout native DSO; private source adapter exposes existing cfg(test) FaultAllocator switch, production FFI unchanged.',gaps=['Held-lock dispatch OOM/publication remains untested and uncorrected','Native DSO internals not sanitizer-instrumented by this runner','No fullplatform/default/performance claim']);target=out/'report.json'
 def checkpoint():target.write_text(json.dumps(report,indent=2)+'\n')
 def run(command,env=None):
  r=subprocess.run(command,text=True,capture_output=True,env=env,timeout=90);report['runs'].append(dict(command=command,exit=r.returncode,stdout=r.stdout,stderr=r.stderr,sanitizer_outcome=sanitizer_outcome(r.stderr)));checkpoint()
  if r.returncode or sanitizer_outcome(r.stderr)!='passed':raise RuntimeError('Compiler/caller or sanitizer failed; raw output retained')
  return r
 try:
  source=ROOT/'crates/ossupport/src/lib.rs';text=source.read_text();marker='    struct FaultAllocator;'
  if text.count(marker)!=1:raise ValueError('Test allocator source changed')
  adapter=out/'instrumented.rs';adapter.write_text(text.replace(marker,marker+'\n    #[unsafe(no_mangle)]\n    pub extern "C" fn swr_test_os_queue_allocation_failure(enabled: bool) { FAIL_NEXT.with(|flag| flag.set(enabled)); }'))
  archive=out/'fault-queue.a';lib=a.library.resolve(strict=True);before=sha(lib);native=a.source/'src/os/async_thread.cc';report.update(library_path=str(a.library),resolved_library_path=str(lib),library_before=before)
  env=dict(os.environ);env['RUSTC_BOOTSTRAP']='1';command=['rustc','--edition','2024','--cfg','test','--crate-type','staticlib','-C','opt-level=1','-C','debuginfo=1',str(adapter),'-o',str(archive)]
  if a.rust_asan:command+=['-Z','sanitizer=address']
  run(command,env);report['archive_identity']=identify(archive,a.rust_asan);exe=out/'native-failure';command=['c++','-std=c++14','-O1','-g','-fsanitize=address,undefined','-DHAVE_CONFIG_H','-DSWOOLE_RS_OSSUPPORT','-DSWRO_ASYNC_SOURCE="'+str(native)+'"','-I'+str(a.source),'-I'+str(a.source/'include'),'-I'+str(ROOT/'native/ossupport'),str(ROOT/'tests/modules/ossupport/queue_failure.cpp'),str(archive),str(lib),'-Wl,-rpath,'+str(lib.parent),'-o',str(exe)]
  if sys.platform=='linux':command+=['-lpthread','-ldl','-lm']
  else:command+=['-I/opt/homebrew/opt/openssl@3/include']
  run(command);env=dict(os.environ)
  if sys.platform=='darwin':env['DYLD_PRINT_LIBRARIES']='1'
  probe=run(['ldd',str(exe)]if sys.platform=='linux'else[str(exe)],env);trace=probe.stdout+probe.stderr;pattern=r'^\s*libswoole[^ ]* => (/.*libswoole[^/ ]*) \(0x[0-9a-fA-F]+\)'if sys.platform=='linux'else r'^dyld\[\d+\]: (?:<[^>]+> )?(/.*libswoole[^/]*\.dylib)\s*$';loaded={str(Path(v).resolve(strict=True))for v in re.findall(pattern,trace,re.M)};report.update(loaded_paths=sorted(loaded),loaded_expected=loaded=={str(lib)})
  run([str(exe)]);report['library_after']=sha(lib);report['gate']=report['loaded_expected']and before==report['library_after']
 except Exception as error:report['error']=str(error)
 checkpoint();print(target);return int(not report['gate'])
if __name__=='__main__':raise SystemExit(main())
