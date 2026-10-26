#!/usr/bin/env python3
"""Pinned dedicated framing and static MIME PHPTs; original assertions unchanged."""
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
FIXTURES = ['examples/test.jpg', 'examples/http/moc.moc', 'examples/http/empty.txt', 'docs/swoole-logo.svg']

def blob(source, path):
    return subprocess.check_output(['git', '-C', str(source), 'show', COMMIT+':'+path])

# tests/swoole_server/wrong_eof_setting.phpt has an --EXPECTF_85-- section that PHP's official
# runner cannot select; the framing-versioned-expectation phase runs it with upstream's rules.
def inventory(source):
    paths = subprocess.check_output(['git','-C',str(source),'ls-tree','-r','--name-only',COMMIT,'tests'],text=True).splitlines()
    def selected(p):
        name = Path(p).stem
        return p.endswith('.phpt') and (
            p.startswith('tests/swoole_server/length/') or
            p.startswith('tests/swoole_socket_coro/protocol/') or
            p.startswith('tests/swoole_http_server/static_handler/') or
            (p.startswith(('tests/swoole_client_async/', 'tests/swoole_client_coro/', 'tests/swoole_client_sync/')) and (name.startswith(('eof', 'length', 'recv_with_open_eof')) or name in {'recv_bad_packet', 'fixed_package'})) or
            p in {'tests/swoole_server/eof_protocol.phpt', 'tests/swoole_server/eof_server.phpt', 'tests/swoole_server_coro/length_1.phpt', 'tests/swoole_server_port/tcp_eof.phpt', 'tests/swoole_http_server/static_handler.phpt', 'tests/swoole_http_server/If_Modified_Since.phpt', 'tests/swoole_http_server/range.phpt', 'tests/swoole_http_server/range2.phpt'}
        )
    return [{'path': p, 'module': 'framing', 'sha256': hashlib.sha256(blob(source,p)).hexdigest(), 'requires': ['upstream_test_bootstrap']} for p in sorted(paths) if selected(p)]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--tls',action='store_true',help='Include dedicated DTLS framing original as a supplemental gate');p.add_argument('--case',action='append',default=[]);p.add_argument('--source',type=Path,required=True);p.add_argument('--engine',action='append',default=[]);p.add_argument('--php',default='php');p.add_argument('--php-extension',action='append',default=[]);p.add_argument('--inventory-only',action='store_true');p.add_argument('--external-network',action='store_true');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    cases=inventory(a.source)
    if a.tls:
        path='tests/swoole_server/ssl/dtls_with_length_protocol.phpt'
        cases.append({'path':path,'module':'framing','sha256':hashlib.sha256(blob(a.source,path)).hexdigest(),'requires':['upstream_test_bootstrap']})
    unknown=set(a.case)-{c['path'] for c in cases}
    if unknown:p.error('Unknown cases: '+str(sorted(unknown)))
    selected=[c for c in cases if not a.case or c['path'] in a.case];excluded=[c for c in cases if c not in selected]
    support=[{'path':p, 'sha256':hashlib.sha256(blob(a.source,p)).hexdigest()} for p in FIXTURES]
    report={'created_utc':datetime.now(timezone.utc).isoformat(),'scope':__doc__,'upstream_commit':COMMIT,'inventory':cases,'inventory_count':len(cases),'unmeasured_cases':[c['path'] for c in excluded],'engines':[],'results':[],'batches':[],'passed':False,'execution_status':'running'}
    try:
        if a.inventory_only:report['execution_status']='inventory_only';save_report(a.output,report);return 0
        if not a.engine:raise ValueError('Require --engine')
        for engine in parse_engines(a.engine,a.php,a.php_extension):
            report['engines'].append(engine.metadata())
            with tempfile.TemporaryDirectory(prefix='swr-framing-phpt-') as directory:
                sandbox=Path(directory);prepare(a.source,sandbox,selected,support);(sandbox/'home').mkdir();(sandbox/'tmp').mkdir()
                for case in selected:
                    artifacts=a.output.resolve().parent/(a.output.stem+'-artifacts')/engine.name/Path(case['path']).parent.name/Path(case['path']).stem
                    rows,timing=run_cases(engine,[case],sandbox,artifacts,90,1,offline=not a.external_network)
                    record_result(report,engine,case,rows[case['path']]);report['batches'].append({'engine':engine.name,**timing});save_report(a.output,report)
        report['execution_status']='complete';report['passed']=bool(report['results']) and not excluded and all(r['status']=='passed' for r in report['results'])
    except Exception as e:report.update(error=str(e),execution_status='failed')
    report['summary']=dict(Counter(r['status'] for r in report['results']));save_report(a.output,report);print(json.dumps({k:report.get(k) for k in ['passed','summary','error']}));return int(not report['passed'])
if __name__=='__main__':sys.exit(main())
