#!/usr/bin/env python3
"""Run the entire pinned lock/atomic PHPT inventory without changing assertions."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from corpus.upstream.run import COMMIT,prepare,record_result,run_cases,save_report
from tools.harness import parse_engines

NON_OWNER_UNLOCK = {'tests/swoole_thread/lock.phpt', 'tests/swoole_thread/atomic_ctor.phpt'}


def inventory(source):
    paths=subprocess.check_output(['git','-C',str(source),'ls-tree','-r','--name-only',COMMIT,'tests/swoole_lock','tests/swoole_atomic','tests/swoole_coroutine_lock','tests/swoole_thread'],text=True).splitlines()
    cases=[]
    for path in paths:
        if not path.endswith('.phpt') or '/swoole_thread/' in path and Path(path).stem not in {'lock','atomic_ctor','barrier'}:continue
        raw=subprocess.check_output(['git','-C',str(source),'show',f'{COMMIT}:{path}'])
        cases.append({'path':path,'module':'locks','sha256':hashlib.sha256(raw).hexdigest(),'requires':['upstream_test_bootstrap'],'boundary':'native retained scheduler' if '/swoole_coroutine_lock/' in path else 'ZTS' if '/swoole_thread/' in path else 'M16'})
    return sorted(cases,key=lambda c:c['path'])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--engine',action='append',default=[]);p.add_argument('--php',default='php');p.add_argument('--php-extension',action='append',default=[]);p.add_argument('--inventory-only',action='store_true');p.add_argument('--output',type=Path,default=ROOT/'target/reports/locks-upstream.json');p.add_argument('--case',action='append',default=[]);a=p.parse_args()
    cases=inventory(a.source)
    unknown=set(a.case)-{case['path'] for case in cases}
    if unknown:p.error('Unknown cases: '+str(sorted(unknown)))
    selected=[case for case in cases if not a.case or case['path'] in a.case];excluded=[case['path']for case in cases if case not in selected]
    report={'created_utc':datetime.now(timezone.utc).isoformat(),'upstream_commit':COMMIT,'inventory':cases,'inventory_count':len(cases),'unmeasured_cases':excluded,'scope':'Entire pinned lock/atomic/coroutine-lock and three thread lock/atomic/barrier originals; official PHP runner and shared documented bootstrap adapter, original bytes/assertions/SKIPIF/expectations intact. Retained native coroutine tests are regression evidence, not Rust scheduler migration. NTS/ZTS/platform skips are not passes.','engines':[],'results':[],'batches':[],'passed':False,'execution_status':'running'}
    try:
        if a.inventory_only:report['execution_status']='inventory_only';save_report(a.output,report);print(len(cases));return 0
        if not a.engine:raise ValueError('Require --engine')
        for engine in parse_engines(a.engine,a.php,a.php_extension):
            report['engines'].append(engine.metadata())
            with tempfile.TemporaryDirectory(prefix='swr-locks-phpt-') as directory:
                sandbox=Path(directory);prepare(a.source,sandbox,selected);(sandbox/'home').mkdir();(sandbox/'tmp').mkdir()
                for case in selected:
                    if report['engines'][-1].get('zts') is True and case['path'] in NON_OWNER_UNLOCK:
                        record_result(report,engine,case,{'status':'unsupported','upstream_status':'NOT_RUN_SOURCE_DOMAIN','detail':'Original default mutex acquired in parent and unlocked by child. Outside the portable ownership-correct pthread contract; source reviewed, original body/SKIPIF/expectations unchanged and not executed.'});save_report(a.output,report);continue
                    artifacts=a.output.resolve().parent/(a.output.stem+'-artifacts')/engine.name/Path(case['path']).parent.name/Path(case['path']).stem
                    rows,timing=run_cases(engine,[case],sandbox,artifacts,45,1)
                    record_result(report,engine,case,rows[case['path']]);report['batches'].append({'engine':engine.name,**timing});save_report(a.output,report)
        report['execution_status']='complete';report['passed']=not excluded and bool(report['results']) and all(r['status']=='passed' for r in report['results'])
    except Exception as e:report.update(error=str(e),execution_status='failed')
    report['summary']=dict(Counter(r['status'] for r in report['results']));save_report(a.output,report);print(json.dumps({k:report.get(k) for k in ['passed','summary','error']}));return int(not report['passed'])


if __name__=='__main__':sys.exit(main())
