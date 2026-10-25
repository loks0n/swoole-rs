#!/usr/bin/env python3
"""Normal initialized PHP Port getter fixture; current source-attested candidate required, no lifetime/reentry profiles."""
import argparse
import json
from pathlib import Path
import sys
from server import attest
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.harness import parse_engines,run_isolated,write_report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--engine',action='append',required=True);p.add_argument('--php',default='php');p.add_argument('--php-extension',action='append',default=[])
    p.add_argument('--build-manifest',type=Path,required=True);p.add_argument('--archive',type=Path,required=True);p.add_argument('--source-ref',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    script=Path(__file__).with_name('callback_property.php');engines=parse_engines(a.engine,a.php,a.php_extension)
    report={'scope':__doc__,'engines':[e.metadata()for e in engines],'results':[],'passed':False}
    try:report['candidate_attestation']=attest(a.build_manifest,a.archive,a.source_ref,report['engines'])
    except Exception as error:report['candidate_attestation']={'passed':False,'error':str(error)};write_report(a.output,report);return 1
    for engine in engines:
        command=engine.command(script);r=run_isolated(command,timeout=30);row={'engine':engine.name,'command':command,'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'passed':False}
        if not r.returncode and not r.stderr:
            try:row['observations']=json.loads(r.stdout);row['passed']=row['observations']['getter_checks']>3000 and row['observations']['callbacks']==12 and bool(row['observations']['locales'])
            except (ValueError,KeyError,TypeError):pass
        report['results'].append(row)
    report['backend_comparison_present']={bool(e['rust_feature_bits']&8388608)for e in report['engines']}=={False,True}
    report['observations_match']=bool(report['results'])and all(r.get('observations')==report['results'][0].get('observations')for r in report['results'])
    report['passed']=report['backend_comparison_present']and report['observations_match']and all(r['passed']for r in report['results']);write_report(a.output,report);print(json.dumps({'passed':report['passed'],'results':report['results']}));return int(not report['passed'])


if __name__=='__main__':sys.exit(main())
