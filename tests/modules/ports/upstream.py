#!/usr/bin/env python3
"""Entire direct Server Port PHPT directory; official runner and unchanged original bytes."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import overlay
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from corpus.upstream.run import COMMIT,prepare,record_result,run_cases,save_report
from tools.harness import parse_engines


def inventory(source, group='direct'):
    paths=subprocess.check_output(['git','-C',str(source),'ls-tree','-r','--name-only',COMMIT,'tests/swoole_server_port'],text=True).splitlines() if group=='direct' else [
        'tests/swoole_server/length/'+name+'.phpt' for name in ['00','01','02','03','length_func']
    ]+['tests/swoole_server/eof_protocol.phpt','tests/swoole_server/eof_server.phpt']
    return [{'path':p,'module':'ports','sha256':hashlib.sha256(overlay.original(p).encode()).hexdigest(),'requires':['upstream_test_bootstrap']} for p in paths if p.endswith('.phpt')]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--engine',action='append',required=True);p.add_argument('--php',default='php');p.add_argument('--php-extension',action='append',default=[]);p.add_argument('--case',action='append',default=[]);p.add_argument('--inventory',choices=['direct','framing'],default='direct');p.add_argument('--output',type=Path,required=True);a=p.parse_args();overlay.SOURCE=a.source
    cases=inventory(a.source,a.inventory);unknown=set(a.case)-{c['path'] for c in cases}
    if unknown:p.error('Unknown cases: '+str(sorted(unknown)))
    selected=[c for c in cases if not a.case or c['path'] in a.case];excluded=[c['path'] for c in cases if c not in selected]
    report={'scope':__doc__ if a.inventory=='direct' else 'Seven reviewed ordinary Server length/EOF framing originals; official runner and unchanged assertions, not the full Server inventory','inventory_group':a.inventory,'pin':COMMIT,'inventory':cases,'inventory_count':len(cases),'unmeasured_cases':excluded,'engines':[],'results':[],'batches':[],'passed':False,'broader_server_inventory_complete':False,'execution_status':'running'}
    try:
        for engine in parse_engines(a.engine,a.php,a.php_extension):
            report['engines'].append(engine.metadata())
            with tempfile.TemporaryDirectory(prefix='swr-port-phpt-') as directory:
                sandbox=Path(directory);prepare(a.source,sandbox,selected);(sandbox/'home').mkdir();(sandbox/'tmp').mkdir()
                for case in selected:
                    artifacts=a.output.resolve().parent/(a.output.stem+'-artifacts')/engine.name/Path(case['path']).stem
                    rows,timing=run_cases(engine,[case],sandbox,artifacts,90,1)
                    record_result(report,engine,case,rows[case['path']]);report['batches'].append({'engine':engine.name,**timing});save_report(a.output,report)
        report['execution_status']='complete';report['passed']=not excluded and bool(report['results']) and all(r['status']=='passed' for r in report['results'])
    except Exception as e:report.update(error=str(e),execution_status='failed')
    report['summary']=dict(Counter(r['status'] for r in report['results']));save_report(a.output,report);print(json.dumps({k:report.get(k) for k in ['passed','summary','error']}));return int(not report['passed'])


if __name__=='__main__':sys.exit(main())
