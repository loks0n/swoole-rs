#!/usr/bin/env python3
"""Compile and run unchanged original async/File GTests with actual OS source.

Explicit group selection; file group on shared hosts needs fixture-name coordination.
"""
from archive_identity import identify,sanitizer_outcome
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--patched-source',type=Path,required=True);p.add_argument('--library',type=Path,required=True);p.add_argument('--rust-archive',type=Path,required=True);p.add_argument('--rust-asan',action='store_true');p.add_argument('--gtest-prefix',type=Path,default=Path('/usr'));p.add_argument('--group',choices=['async','file','msg_queue'],required=True);p.add_argument('--linked-only',action='store_true',help='Link original main/unit directly to whole supplied libraries without production source interposition');p.add_argument('--reference-library',type=Path);p.add_argument('--timeout',type=int,default=90);p.add_argument('--ipc-namespace',help='Explicit fixture lease or private container IPC identity for original fixed key');a=p.parse_args()
 if a.linked_only and not a.reference_library:p.error('--linked-only requires explicit --reference-library')
 if a.group=='msg_queue' and not a.ipc_namespace:p.error('msg_queue fixed original key requires explicit private IPC namespace/fixture lease')
 out=ROOT/'target/ossupport'/('original-'+a.group+'-'+time.strftime('%Y%m%dT%H%M%S')+'-'+str(time.time_ns()));out.mkdir(parents=True)
 lib=a.library.resolve();cases={'async':['dispatch','schedule','misc'],'file':['read_line','read_line_no_crlf','file_put_contents','file_get_contents','file_get_size','open_twice','error','tmp_file','empty_file'],'msg_queue':['rbac']}[a.group];unit=a.source/f'core-tests/src/os/{a.group}.cpp';results=[]
 candidates=[a.gtest_prefix/'lib/libgtest.a',*a.gtest_prefix.glob('lib/*/libgtest.a')];gtest=next(x for x in candidates if x.is_file())
 for mode in ['reference','rust']:
  lib=(a.reference_library if mode=='reference' and a.linked_only else a.library).resolve()
  source=a.source/({'async':'src/os/async_thread.cc','file':'src/os/file.cc','msg_queue':'src/os/msg_queue.cc'}[a.group])if mode=='reference'else a.patched_source;modeout=out/mode;modeout.mkdir();exe=modeout/'bin/core-tests';exe.parent.mkdir()
  cmd=['c++','-std=c++14','-O1','-g','-fsanitize=address,undefined','-DHAVE_CONFIG_H','-I'+str(a.source),'-I'+str(a.source/'include'),'-I'+str(a.source/'core-tests/include'),'-I'+str(a.gtest_prefix/'include'),'-I'+str(ROOT/'native/ossupport'),str(a.source/'core-tests/src/main.cpp'),str(unit),*([]if a.linked_only else[str(source)]),str(lib),str(gtest),'-Wl,-rpath,'+str(lib.parent),'-o',str(exe)]
  if sys.platform=='darwin':cmd+=['-I/opt/homebrew/opt/openssl@3/include']
  if mode=='rust' and not a.linked_only:cmd+=['-DSWOOLE_RS_OSSUPPORT',str(a.rust_archive)]
  if sys.platform=='linux':cmd+=['-lpthread','-ldl','-lm']
  c=subprocess.run(cmd,capture_output=True,text=True);entry=dict(mode=mode,command=cmd,compile_exit=c.returncode,compile_stdout=c.stdout,compile_stderr=c.stderr,library_path=str(lib),library_before=sha(lib))
  if c.returncode==0:
   fixtures=modeout/'tests/include';fixtures.mkdir(parents=True);shutil.copy2(a.source/'tests/include/bootstrap.php',fixtures/'bootstrap.php')
   env=dict(os.environ)
   if sys.platform=='darwin':env['DYLD_PRINT_LIBRARIES']='1';probe_cmd=[str(exe),'--gtest_list_tests']
   else:probe_cmd=['ldd',str(exe)]
   probe=subprocess.run(probe_cmd,capture_output=True,text=True,env=env);trace=probe.stdout+probe.stderr
   pattern=r'^dyld\[\d+\]: (?:<[^>]+> )?(/.*libswoole[^/]*\.dylib)\s*$'if sys.platform=='darwin'else r'^\s*libswoole[^ ]* => (/.*libswoole[^/ ]*) \(0x[0-9a-fA-F]+\)'
   loaded={str(Path(v).resolve(strict=True))for v in re.findall(pattern,trace,re.M)}
   entry.update(loader_trace=trace,loader_exit=probe.returncode,loaded_paths=sorted(loaded),loaded_expected=probe.returncode==0 and loaded=={str(lib)},cases=[])
   for name in cases:
    case=a.group+'.'+name;xml=modeout/(name+'.xml');command=[str(exe),'--gtest_filter='+case,'--gtest_output=xml:'+str(xml)]
    before=sha(lib)
    try:x=subprocess.run(command,capture_output=True,text=True,timeout=a.timeout);row=dict(case=case,command=command,exit=x.returncode,stdout=x.stdout,stderr=x.stderr)
    except subprocess.TimeoutExpired as e:row=dict(case=case,command=command,status='failed',error='timeout',stdout=str(e.stdout),stderr=str(e.stderr));entry['cases'].append(row);continue
    row.update(library_before=before,library_after=sha(lib),status='failed')
    if xml.exists():
     tree=ET.parse(xml);nodes=list(tree.iter('testcase'))
     if len(nodes)==1 and nodes[0].get('classname')+'.'+nodes[0].get('name')==case and x.returncode==0 and not list(tree.iter('failure')) and not list(tree.iter('error')):
      row['status']='skipped'if list(tree.iter('skipped'))else'passed'
    row['sanitizer_outcome']=sanitizer_outcome(row['stderr'])
    if row['status']=='passed' and row['sanitizer_outcome']!='passed':row['status']=row['sanitizer_outcome']
    entry['cases'].append(row);print(mode,case,row['status'],flush=True)
   entry['library_after']=sha(lib)
  else:print(mode,'compile failed',c.stderr[-500:],flush=True)
  results.append(entry)
  (out/'report.json').write_text(json.dumps(dict(platform=sys.platform,group=a.group,linked_only=a.linked_only,production_source_interposition=not a.linked_only,ipc_namespace=a.ipc_namespace,observed_linux_ipc_namespace=os.readlink('/proc/self/ns/ipc') if sys.platform=='linux'else None,results=results,archive_identity=identify(a.rust_archive,a.rust_asan),limitations=['Selected original unit only, not complete OS support parity','Native sanitizer coverage is separate from explicitly verified Rust-instruction instrumentation','Explicit supplied native library identity observed; historical build not reattested','With linked-only, supplied archive identifies producer dependency; harness links whole library, not archive directly']),indent=2)+'\n')
 gate=all(e.get('loaded_expected') and len(e.get('cases',[]))==len(cases) and all(r['status']=='passed'and r.get('library_before')==r.get('library_after')for r in e['cases']) and e['library_before']==e.get('library_after')for e in results)
 print(out/'report.json');return 0 if gate else 1
if __name__=='__main__':raise SystemExit(main())
