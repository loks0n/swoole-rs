#!/usr/bin/env python3
"""One deterministic sweep of the pinned request PHPT's random split domain.

This diagnostic never changes/reruns the original PHPT. Original expectation
failures remain failures even when identical across engines.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import parse_engines, run_isolated, write_report
from gate import PIN
TEST = 'tests/swoole_http_server/create_request.phpt'
DIGEST = 'ae0ac0bfe0b55c5ccc982d8fae4bfe22430d7084be047d3bf51b812614ed4c99'
SWEEP = r'''
$rows=[];
for ($split=100; $split<=600; ++$split) {
    $req=\Swoole\Http\Request::create();
    $initial_headers=count($req->header)===0; $initial_incomplete=!$req->isCompleted();
    $left=substr($data,0,$split); $right=substr($data,strlen($left));
    $first=$req->parse($left); $incomplete1=!$req->isCompleted();
    $second=$req->parse($right); $incomplete2=!$req->isCompleted();
    $ending=$req->parse("\r\n");
    $cookie=$req->cookie; if(is_array($cookie)) ksort($cookie);
    $checks=[
        'initial_headers'=>$initial_headers,
        'initial_incomplete'=>$initial_incomplete,
        'first_consumed'=>$first===strlen($left),
        'first_incomplete'=>$incomplete1,
        'second_consumed'=>$second===strlen($right),
        'second_incomplete'=>$incomplete2,
        'ending_consumed'=>$ending===2,
        'completed'=>$req->isCompleted(),
        'reject_extra'=>$req->parse('error data')===false,
        'method'=>$req->getMethod()==='GET',
        'headers'=>count($req->header)>4,
        'cookies'=>is_array($cookie) && count($cookie)===3,
        'original_data'=>$req->getData()===$data."\r\n",
    ];
    $rows[]=['split'=>$split,'checks'=>$checks,'cookies'=>$cookie,
        'failed_checks'=>array_keys(array_filter($checks,fn($value)=>!$value))];
}
echo json_encode(['request_length'=>strlen($data),'request_sha256'=>hash('sha256',$data),'rows'=>$rows],JSON_THROW_ON_ERROR);
'''

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--engine',action='append',required=True)
    parser.add_argument('--php',default='php')
    parser.add_argument('--php-extension',action='append',default=[])
    parser.add_argument('--output',type=Path,default=Path('target/http-check/request-splits.json'))
    args=parser.parse_args()
    original=subprocess.check_output(['git','-C',str(args.source),'show',PIN+':'+TEST])
    if hashlib.sha256(original).hexdigest()!=DIGEST: raise ValueError('Pinned original request PHPT checksum mismatch')
    text=original.decode(); begin=text.index('$data = "GET ');end=text.index('$req = Request::create();',begin)
    # Reuse exactly the original request construction statements, no original
    # assertions/expectations edited. The added sweep replaces random sampling.
    construction=text[begin:end]
    program='<?php\n'+construction+SWEEP
    report={'pin':PIN,'original_test':TEST,'engines':[],'execution_status':'running'}
    with tempfile.TemporaryDirectory(prefix='http-request-splits-') as temporary:
        script=Path(temporary)/'splits.php';script.write_text(program)
        for engine in parse_engines(args.engine,args.php,args.php_extension):
            metadata=engine.metadata()
            result=run_isolated(engine.command(script),cwd=temporary,timeout=30)
            row={'engine':metadata,'returncode':result.returncode,'stderr':result.stderr}
            if result.returncode==0:
                row['outcome']=json.loads(result.stdout)
                row['original_expectation_failures']=sum(bool(r['failed_checks']) for r in row['outcome']['rows'])
            else: row['stdout']=result.stdout
            report['engines'].append(row);write_report(args.output,report)
    valid=[r for r in report['engines'] if r['returncode']==0]
    report['execution_status']='complete'
    report['matched_outcomes']=len(valid)==len(report['engines']) and all(r['outcome']==valid[0]['outcome'] for r in valid)
    report['passed']=len(valid)==len(report['engines']) and all(r['original_expectation_failures']==0 for r in valid)
    write_report(args.output,report)
    print(json.dumps({'matched_outcomes':report['matched_outcomes'],'passed':report['passed'],
                      'original_expectation_failures':{r['engine']['name']:r.get('original_expectation_failures') for r in report['engines']}}))
    return 0 if report['passed'] else 1
if __name__=='__main__':sys.exit(main())
