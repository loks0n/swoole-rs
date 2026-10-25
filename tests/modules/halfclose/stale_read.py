#!/usr/bin/env python3
"""Exercise the actual native read dispatcher after close queues and a read event is already cached."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--source',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
source=(a.source/'src/server/reactor_thread.cc').read_text()
start=source.index('static int ReactorThread_onRead(Reactor *reactor, Event *event) {')
body=source[start:source.index('static int ReactorThread_onWrite(Reactor *reactor, Event *ev) {',start)]
driver=Path(__file__).with_suffix('.cc').read_text()
r={'scope':'Actual extracted native onRead body, explicit minimal field/callback adapter, real socketpair/poll cached EOF; ASan/UBSan native instructions. No full object-layout, Rust/reactor backend or rare FIN cause proof. Existing TLS retry is a callback stub, not OpenSSL execution.', 'source':str(a.source.resolve())}
with tempfile.TemporaryDirectory(prefix='stale-read-') as d:
 d=Path(d);(d/'test.cc').write_text(driver.replace('// ACTUAL_ON_READ',body))
 cmd=['c++','-std=c++17','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(d/'test.cc'),'-o',str(d/'test')]
 c=subprocess.run(cmd,capture_output=True,text=True,timeout=60)
 r['compile']={'exit_code':c.returncode,'stdout':c.stdout,'stderr':c.stderr}
 if c.returncode==0:
  c=subprocess.run([str(d/'test')],capture_output=True,text=True,timeout=10)
  r['run']={'exit_code':c.returncode,'stdout':c.stdout,'stderr':c.stderr}
r['passed']=r['compile']['exit_code']==0 and r.get('run',{}).get('exit_code')==0
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps(r));raise SystemExit(not r['passed'])
