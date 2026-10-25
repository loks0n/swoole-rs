#!/usr/bin/env python3
"""Full patched native units: module flag read from config.h, never command line."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);a=p.parse_args();out=ROOT/'target/ossupport'/('activation-'+str(time.time_ns()));out.mkdir(parents=True)
 manifest=json.loads((ROOT/'migration/patches/ossupport/manifest.json').read_text());sources=[]
 for patch in manifest['patches']:
  patchfile=ROOT/'migration/patches/ossupport'/patch['path'];assert sha(patchfile)==patch['sha256']
  for name in patch['upstream_paths']:
   dest=out/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(a.source/name,dest);sources.append(dest)
  subprocess.run(['patch','--fuzz=0','-p1','-d',str(out),'-i',str(patchfile)],check=True,capture_output=True)
 reports=[]
 for mode in ['enabled','disabled']:
  config=out/mode;config.mkdir();(config/'config.h').write_text('#include "'+str((a.source/'config.h').resolve())+'"\n'+('#define SWOOLE_RS_OSSUPPORT 1\n'if mode=='enabled'else'#undef SWOOLE_RS_OSSUPPORT\n'))
  for source in sources:
   command=['c++','-std=c++14','-fsyntax-only','-DHAVE_CONFIG_H','-I'+str(config),'-I'+str(a.source),'-I'+str(a.source/'include'),'-I'+str(ROOT/'native/ossupport'),str(source)]
   if sys.platform=='darwin':command+=['-I/opt/homebrew/opt/openssl@3/include']
   r=subprocess.run(command,text=True,capture_output=True);passed=r.returncode==0 if mode=='enabled'else r.returncode!=0 and'OS support overlay requires --enable-swoole-rs-ossupport'in r.stderr
   reports.append(dict(command=command,mode=mode,exit=r.returncode,stdout=r.stdout,stderr=r.stderr,passed=passed))
 report=dict(gate=all(r['passed']for r in reports),platform=sys.platform,runs=reports,scope='Five full native units with exact overlay; enabled flag comes from config.h loaded by first project include. Missing module flag must reject overlay.')
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(out/'report.json');return 0 if report['gate']else 1
if __name__=='__main__':raise SystemExit(main())
