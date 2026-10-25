#!/usr/bin/env python3
"""Compile ordinary typed Buffer callers in exact native repair compositions.
Pinned header mirror, not a configured production SDK or runtime execution.
"""
import shutil
import argparse,  io, json, subprocess, sys, tarfile, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.build_hybrid import apply_patch_verified
from tools.build_upstream import COMMIT as PIN
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--report',type=Path,required=True);p.add_argument('--master-patch',type=Path,required=True);a=p.parse_args()
 if min(shutil.disk_usage(ROOT).free,shutil.disk_usage(tempfile.gettempdir()).free)<4*1024**3:p.error("4GiB disk guard refused compilation")
 if a.report.exists():p.error('Refusing to replace receipt')
 report=dict(pin=PIN,scope=__doc__,rows=[],compositions=[])
 files=['src/core/buffer.cc','src/network/socket.cc','src/reactor/base.cc','src/server/base.cc','src/server/reactor_thread.cc','src/server/master.cc']
 for repaired in [False,True]:
  with tempfile.TemporaryDirectory(prefix='swr-buffer-callers-') as tmp:
   tree=Path(tmp);data=subprocess.check_output(['git','-C',str(a.source),'archive',PIN,'include','thirdparty',*files,'src/reactor/poll.cc','src/reactor/epoll.cc','src/reactor/kqueue.cc','src/network/stream.cc','ext-src/swoole_admin_server.cc'])
   with tarfile.open(fileobj=io.BytesIO(data)) as ar:
    for m in ar:
     if m.isfile():
      dest=tree/m.name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(ar.extractfile(m).read())
   proofs=[]
   if repaired:
    manifest=ROOT/'migration/patches/halfclose/manifest.json'
    for e in json.loads(manifest.read_text())['patches']:
     proofs.append(apply_patch_verified(tree,manifest.parent/e['path'],e['upstream_paths'],e['sha256']))
   for module in ['buffer','reactor']:
    manifest=ROOT/'migration/patches'/module/'manifest.json'
    for e in json.loads(manifest.read_text())['patches']:
     if module=='buffer' and e['path']=='0003-string-storage.patch':continue
     proofs.append(apply_patch_verified(tree,manifest.parent/e['path'],e['upstream_paths'],e['sha256']))
   proofs.append(apply_patch_verified(tree,a.master_patch,['src/server/master.cc']))
   report['compositions'].append(dict(repaired=repaired,patches=proofs))
   for typed in [None,0,1]:
    for name in files:
     command=['c++','-std=c++14','-fsyntax-only','-DHAVE_KQUEUE=1','-DSWOOLE_RS_REACTOR=1','-DSWOOLE_RS_BUFFER=1','-I'+str(tree/'include'),'-I'+str(tree),'-I'+str(ROOT/'native/include'),'-I'+str(ROOT/'native/buffer'),'-I'+str(ROOT/'native/reactor')]
     command += subprocess.check_output(['pkg-config','--cflags','openssl'],text=True).split()
     if typed is not None:command+=['-DSWOOLE_RS_BUFFER_TYPED='+str(typed)]
     command += [str(tree/name)]
     result=subprocess.run(command,capture_output=True,text=True)
     row=dict(repaired=repaired,typed=typed,source=name,command=command,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr,passed=result.returncode==0)
     report['rows'].append(row);print(repaired,typed,name,result.returncode,result.stderr[:300],flush=True)
     a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n')
 report['passed']=all(r['passed'] for r in report['rows']);a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n');return int(not report['passed'])
if __name__=='__main__':raise SystemExit(main())
