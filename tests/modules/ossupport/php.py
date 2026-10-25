#!/usr/bin/env python3
"""Actual PHP async file/concurrent completion/reinit/fork consumers, no ports."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT,parse_engines,run_isolated
from tools.extension_identity import observe

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--engine',action='append',required=True);p.add_argument('--php',default='php');p.add_argument('--php-extension',action='append',default=[]);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--source',type=Path,default=ROOT/'target/upstream/src');p.add_argument('--output',type=Path);a=p.parse_args();
 if a.output and a.output.exists():p.error('refusing to overwrite existing report')
 out=ROOT/'target/ossupport'/('php-'+str(time.time_ns()));out.mkdir(parents=True)
 manifest=json.loads(a.manifest.read_text());fixture=ROOT/'tests/modules/ossupport/php_caller.php';reports=[];observed=[];candidate_seen=False
 for engine in parse_engines(a.engine,a.php,a.php_extension):
  before=sha(engine.extension);meta=engine.metadata()
  if meta['rust_feature_bits'] & 131072:
   candidate_seen=True
   if manifest['extension_sha256']!=before:raise ValueError('candidate differs from selected manifest')
  elif meta['rust_feature_bits']!=0:raise ValueError('candidate lacks actual OS support feature')
  else:observed.append(observe(engine,a.source))
  with tempfile.TemporaryDirectory(prefix='swr-os-php-')as directory:
   command=engine.command(fixture,directory);r=run_isolated(command,cwd=ROOT,timeout=60)
  try:value=json.loads(r.stdout.strip())
  except ValueError:value=None
  reports.append(dict(engine=meta,command=command,exit=r.returncode,stdout=r.stdout,stderr=r.stderr,value=value,extension_before=before,extension_after=sha(engine.extension)))
  print(engine.name,r.returncode,r.stdout[-300:],r.stderr[-300:],flush=True)
 gate=candidate_seen and all(r['exit']==0 and r['value'] is not None and r['extension_before']==r['extension_after']for r in reports)and all(r['value']==reports[0]['value']for r in reports)
 report=dict(created_utc=datetime.now(timezone.utc).isoformat(),gate=gate,selected_manifest=manifest,observed_native_references=observed,results=reports,limitations=['Selected async/file/reinit/fork consumer, not full original parity','Native storage/syscalls/callbacks remain, no Rust-instruction sanitizer or performance claim','Reference binary observed; original build provenance not established'])
 target=a.output or out/'report.json';target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(report,indent=2)+'\n');print(target);return 0 if gate else 1
if __name__=='__main__':raise SystemExit(main())
