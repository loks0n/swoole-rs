#!/usr/bin/env python3
"""Compare real native and Rust-backed Cookie public API consumers."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from tools.harness import parse_engines,run_isolated,write_report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine',action='append',required=True)
    parser.add_argument('--php',default='php')
    parser.add_argument('--php-extension',action='append',default=[])
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();engines=parse_engines(args.engine,args.php,args.php_extension)
    if len(engines)<2 or engines[0].name!='upstream':parser.error('First engine upstream=PATH plus candidate engine(s) required')
    fixture=Path(__file__).with_suffix('.php');report={'scope':__doc__,'limitations':'Actual PHP public Cookie API, not allocator fault/GC ownership/exhaustive bailout or all binding methods. drop-holder retains the active method variable; no self-deletion claim.', 'engines':[],'results':[],'passed':False};baseline=None
    for index,engine in enumerate(engines):
        row={'engine':engine.name,'passed':False};report['results'].append(row)
        try:
            report['engines'].append(engine.metadata());command=engine.command(fixture);r=run_isolated(command,timeout=60)
            row.update(command=command,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)
            if r.returncode:continue
            data=json.loads(r.stdout);row.pop('stdout');row['observed']=data
            if index==0:baseline=data
            row['passed']=baseline is not None and data==baseline and data['cases']==3114
        except Exception as error:row['error']=str(error)
    report['passed']=all(r['passed']for r in report['results']);write_report(args.output,report)
    print(json.dumps({'passed':report['passed'],'engines':len(engines),'cases_per_engine':baseline['cases']if baseline else None}));return 0 if report['passed']else 1


if __name__=='__main__':sys.exit(main())
