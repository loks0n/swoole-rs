#!/usr/bin/env python3
"""Independent copied-policy differential, separate from native/PHP lifecycle gates."""
import argparse,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tests/modules/ossupport'))
from archive_identity import sanitizer_outcome
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archive',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
 if a.output and a.output.exists():p.error('Refusing existing report')
 out=ROOT/'target/process'/('policy-'+str(time.time_ns()));out.mkdir(parents=True);archive=a.archive.resolve()if a.archive else out/'libprocess.a';commands=[]
 if not a.archive:commands=[['rustc','--edition','2024','--test',str(ROOT/'crates/process/src/lib.rs'),'-o',str(out/'unit')],[str(out/'unit')],['rustc','--edition','2024','--crate-type','staticlib','-C','opt-level=2',str(ROOT/'crates/process/src/lib.rs'),'-o',str(archive)]]
 command=['c++','-std=c++14','-O1','-g','-fsanitize=address,undefined','-I'+str(ROOT/'native/process'),str(ROOT/'tests/modules/process/differential.cpp'),str(archive),'-o',str(out/'differential')]
 if sys.platform=='linux':command+=['-lpthread','-ldl','-lm']
 commands+=[command,[str(out/'differential')]];rows=[]
 for command in commands:
  r=subprocess.run(command,text=True,capture_output=True);row=dict(command=command,exit=r.returncode,stdout=r.stdout,stderr=r.stderr,sanitizer_outcome=sanitizer_outcome(r.stderr));rows.append(row)
  if r.returncode or sanitizer_outcome(r.stderr)!='passed':break
 report=dict(gate=len(rows)==len(commands)and all(r['exit']==0 and r['sanitizer_outcome']=='passed'for r in rows),platform=sys.platform,runs=rows,selected_archive=bool(a.archive),archive_path=str(archive))
 target=a.output or out/'report.json';target.write_text(json.dumps(report,indent=2)+'\n');print(target);return int(not report['gate'])
if __name__=='__main__':raise SystemExit(main())
