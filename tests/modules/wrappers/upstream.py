#!/usr/bin/env python3
"""All pinned event/timer PHPTs; offline exclusions remain unmeasured, never passes."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import socket
import sys
import tempfile
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from corpus.upstream.run import COMMIT, prepare, record_result, run_cases, save_report
from tools.harness import parse_engines
EXTERNAL = {'tests/swoole_timer/' + n + '.phpt' for n in ['bug_4794_3', 'bug_4794_5', 'bug_4794_6', 'bug_4794_7']}

def inventory(source):
    paths = subprocess.check_output(['git','-C',str(source),'ls-tree','-r','--name-only',COMMIT,'tests/swoole_event','tests/swoole_timer'],text=True).splitlines()
    return [{'path': p, 'module': 'wrappers', 'sha256': hashlib.sha256(subprocess.check_output(['git','-C',str(source),'show',COMMIT+':'+p])).hexdigest(), 'requires': ['upstream_test_bootstrap']} for p in sorted(paths) if p.endswith('.phpt')]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--engine',action='append',default=[]);p.add_argument('--php',default='php');p.add_argument('--php-extension',action='append',default=[]);p.add_argument('--inventory-only',action='store_true');p.add_argument('--external-network',action='store_true');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    cases=inventory(a.source);excluded=[] if a.external_network else [c for c in cases if c['path'] in EXTERNAL];selected=[c for c in cases if c not in excluded]
    report={'created_utc':datetime.now(timezone.utc).isoformat(),'scope':__doc__,'upstream_commit':COMMIT,'inventory':cases,'inventory_count':len(cases),'unmeasured_cases':[c['path'] for c in excluded],'engines':[],'results':[],'batches':[],'passed':False,'execution_status':'running'}
    try:
        if a.inventory_only:report['execution_status']='inventory_only';save_report(a.output,report);return 0
        if not a.engine:raise ValueError('Require --engine')
        for engine in parse_engines(a.engine,a.php,a.php_extension):
            report['engines'].append(engine.metadata())
            with tempfile.TemporaryDirectory(prefix='swr-wrapper-phpt-') as directory:
                sandbox=Path(directory);prepare(a.source,sandbox,selected);(sandbox/'home').mkdir();(sandbox/'tmp').mkdir()
                for case in selected:
                    artifacts=a.output.resolve().parent/(a.output.stem+'-artifacts')/engine.name/Path(case['path']).parent.name/Path(case['path']).stem
                    if Path(case['path']).stem == 'bug_4794_8':
                        try:
                            with socket.socket() as guard:
                                guard.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);guard.bind(('127.0.0.1',9601))
                        except OSError as e:
                            record_result(report,engine,case,{'status':'failed','detail':'Fixed port unavailable: '+str(e)});save_report(a.output,report);continue
                    rows,timing=run_cases(engine,[case],sandbox,artifacts,45,1,offline=not a.external_network)
                    record_result(report,engine,case,rows[case['path']]);report['batches'].append({'engine':engine.name,**timing});save_report(a.output,report)
        report['execution_status']='complete';report['passed']=bool(report['results']) and not excluded and all(r['status']=='passed' for r in report['results'])
    except Exception as e:report.update(error=str(e),execution_status='failed')
    report['summary']=dict(Counter(r['status'] for r in report['results']));save_report(a.output,report);print(json.dumps({k:report.get(k) for k in ['passed','summary','error']}));return int(not report['passed'])
if __name__=='__main__':sys.exit(main())
