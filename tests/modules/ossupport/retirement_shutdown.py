#!/usr/bin/env python3
"""Causal diagnostic for native pending-retirement ownership, with test-only barriers."""
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
 p=argparse.ArgumentParser(description=__doc__)
 for name in ['reference-source','reference-library','rust-source','rust-library','rust-archive']:p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--rust-asan',action='store_true');a=p.parse_args();out=ROOT/'target/ossupport'/('retirement-shutdown-'+str(time.time_ns()));out.mkdir(parents=True);target=out/'report.json'
 report=dict(platform=sys.platform,gate=False,results=[],archive_identity=identify(a.rust_archive,a.rust_asan),scope='Actual pinned/selected async_thread.cc copies with test-only scheduling/observation hooks, matching private-layout DSOs. No production source changes or cleanup suppression. Failure is retained even when reproducer successfully makes it deterministic.',gaps=['Controlled legal interleaving, not frequency/performance evidence','Other running/thread-map/canceled/OOM/queued-payload gaps remain','No production correction or activation claim'])
 def checkpoint():target.write_text(json.dumps(report,indent=2)+'\n')
 for mode,source,library in [('reference',a.reference_source,a.reference_library),('rust',a.rust_source,a.rust_library)]:
  row=dict(mode=mode,status='failed');report['results'].append(row)
  try:
   lib=library.resolve(strict=True);before=sha(lib);original=source/'src/os/async_thread.cc';text=original.read_text();row.update(library_path=str(lib),library_before=before)
   hooks='extern "C" void swr_test_retirement_wait();\nextern "C" void swr_test_shutdown_begin();\nextern "C" long swr_test_observe_send(long,bool);\nextern "C" void swr_test_retirement_callback();\n'
   for old,new in [('        _send_event:\n','        _send_event:\n            if (exit_flag) swr_test_retirement_wait();\n'),('AsyncThreads::~AsyncThreads() {\n','AsyncThreads::~AsyncThreads() {\n    swr_test_shutdown_begin();\n'),('event->pipe_socket->write_sync(&event, sizeof(event))','swr_test_observe_send(event->pipe_socket->write_sync(&event, sizeof(event)), exit_flag)'),('    static void release_callback(AsyncEvent *event) {\n','    static void release_callback(AsyncEvent *event) {\n        swr_test_retirement_callback();\n')]:
    if text.count(old)!=1:raise ValueError('Native scheduling adapter anchor changed: '+old)
    text=text.replace(old,new)
   adapted=out/(mode+'-async.cc');adapted.write_text(hooks+text);exe=out/(mode+'-caller');command=['c++','-std=c++14','-O1','-g','-fsanitize=address,undefined','-DHAVE_CONFIG_H','-I'+str(source),'-I'+str(source/'include'),'-I'+str(ROOT/'native/ossupport'),str(ROOT/'tests/modules/ossupport/retirement_shutdown.cpp'),str(adapted)]
   if mode=='rust':command+=['-DSWOOLE_RS_OSSUPPORT',str(a.rust_archive)]
   command+=[str(lib),'-Wl,-rpath,'+str(lib.parent),'-o',str(exe)]
   if sys.platform=='linux':command+=['-lpthread','-ldl','-lm']
   else:command+=['-I/opt/homebrew/opt/openssl@3/include']
   c=subprocess.run(command,text=True,capture_output=True,timeout=90);row.update(command=command,compile_exit=c.returncode,compile_stdout=c.stdout,compile_stderr=c.stderr);checkpoint()
   if c.returncode:raise RuntimeError('Caller compile failed')
   env=dict(os.environ)
   if sys.platform=='darwin':env['DYLD_PRINT_LIBRARIES']='1'
   probe=subprocess.run(['ldd',str(exe)]if sys.platform=='linux'else[str(exe)],text=True,capture_output=True,env=env,timeout=30);trace=probe.stdout+probe.stderr;pattern=r'^\s*libswoole[^ ]* => (/.*libswoole[^/ ]*) \(0x[0-9a-fA-F]+\)'if sys.platform=='linux'else r'^dyld\[\d+\]: (?:<[^>]+> )?(/.*libswoole[^/]*\.dylib)\s*$';loaded={str(Path(v).resolve(strict=True))for v in re.findall(pattern,trace,re.M)};row.update(loader_trace=trace,loaded_expected=loaded=={str(lib)},loaded_paths=sorted(loaded))
   result=subprocess.run([str(exe)],text=True,capture_output=True,timeout=30);row.update(exit=result.returncode,stdout=result.stdout,stderr=result.stderr,sanitizer_outcome=sanitizer_outcome(result.stderr),library_after=sha(lib),reproduced_unconsumed_notification='retirement_sent=1 retirement_callbacks=0'in result.stdout and'FAILED: idle-retirement notification'in result.stderr)
   if result.returncode==0 and row['sanitizer_outcome']=='passed'and row['loaded_expected']and before==row['library_after']:row['status']='passed'
  except Exception as error:row['error']=str(error)
  checkpoint()
 report['gate']=all(r['status']=='passed'for r in report['results']);checkpoint();print(target);return int(not report['gate'])
if __name__=='__main__':raise SystemExit(main())
