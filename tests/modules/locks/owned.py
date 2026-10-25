#!/usr/bin/env python3
"""Normal 64-bit NTS single-owner locks and valid atomic values; no old coroutine/fault/IPC/thread/lifetime profiles."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.harness import parse_engines,run_isolated,write_report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--engine',action='append',required=True);p.add_argument('--php',default='php');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    fixture=Path(__file__).with_suffix('.php');engines=parse_engines(a.engine,a.php,[]);report={'scope':__doc__,'engines':[],'results':[],'passed':False,'full_module_gate_passed':False,'thread_or_coroutine_qualified':False,'performance_qualified':False}
    for engine in engines:
        report['engines'].append(engine.metadata());command=engine.command(fixture);r=run_isolated(command,timeout=30);row={'engine':engine.name,'command':command,'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'passed':False}
        if r.returncode==0 and not r.stderr:
            try:
                values=json.loads(r.stdout);row['observations']=values;row['passed']=values['atomic_checks']=={'Swoole\\Atomic':1792,'Swoole\\Atomic\\Long':1792}and values['owned_lock_roundtrips'].get('MUTEX')==128 and all(n==128 for n in values['owned_lock_roundtrips'].values())
            except (ValueError,KeyError,TypeError):pass
        report['results'].append(row);write_report(a.output,report)
    report['backend_comparison_present']={bool(e['rust_feature_bits']&1024)for e in report['engines']}=={False,True}
    report['observations_match']=len(report['results'])==2 and report['results'][0].get('observations')==report['results'][1].get('observations')
    report['passed']=report['backend_comparison_present']and report['observations_match']and all(r['passed']for r in report['results']);write_report(a.output,report);print(json.dumps({'passed':report['passed'],'results':report['results']}));return int(not report['passed'])


if __name__=='__main__':sys.exit(main())
