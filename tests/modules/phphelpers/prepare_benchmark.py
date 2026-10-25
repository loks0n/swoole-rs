#!/usr/bin/env python3
"""Prepare immutable optimized helper subsets; no measurements or speed claim."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
import gate
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.build_upstream import require_build_space
from tools.harness import write_report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--work-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    work=a.work_root.resolve()/('prepared-'+uuid.uuid4().hex);work.mkdir(parents=True)
    report={'created_utc':datetime.now(timezone.utc).isoformat(),'passed':False,'scope':__doc__,'work':str(work),'commands':[],'measurement_performed':False}
    try:
        require_build_space(work);report['sources']=gate.stage(a.source,work)
        files={'lib.rs':ROOT/'crates/phphelpers/src/lib.rs','swoole_rs_phphelpers.h':ROOT/'native/phphelpers/swoole_rs_phphelpers.h','benchmark.cc':Path(__file__).with_name('benchmark.cc')}
        rust_source=ROOT/'crates/phphelpers/src'
        files.update({str(path.relative_to(rust_source)):path for path in rust_source.rglob('*.rs')})
        for name,path in files.items():
            destination=work/name;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(path.read_bytes())
        original=subprocess.check_output(['git','-C',str(a.source),'show',gate.PIN+':ext-src/swoole_stdext.cc'],text=True)
        start=original.index('static std::unordered_map<std::string, std::string> array_methods');end=original.index('\nstatic void move_first_element',start)
        (work/'aliases.inc').write_text(original[start:end]);(work/'arguments.inc').write_text(gate.body(original,'static void move_first_element('))
        (work/'selected-arguments.inc').write_text(gate.body((work/'ext-src/swoole_stdext.cc').read_text(),'static void move_first_element('))
        report['toolchains']={tool:subprocess.check_output([tool,'--version'],text=True).strip() for tool in ['rustc','c++']}
        archive=work/'libphphelpers.a';binary=work/'benchmark';temporary=work/'tmp';temporary.mkdir()
        environment={**os.environ,'TMPDIR':str(temporary)}
        commands=[['rustc','--edition=2024','--crate-type=staticlib','-C','opt-level=3',work/'lib.rs','-o',archive],
                  ['c++','-std=c++17','-O3','-UNDEBUG','-DSWOOLE_RS_PHPHELPERS','-Wall','-Wextra','-Werror','-I'+str(work),work/'benchmark.cc',archive,'-lpthread','-lm','-o',binary],
                  [binary,'--check']]
        if sys.platform.startswith('linux'):commands[1]+=['-ldl','-lrt','-lutil']
        for command in commands:
            require_build_space(work);command=list(map(str,command));result=subprocess.run(command,env=environment,capture_output=True,text=True,timeout=90)
            report['commands'].append({'command':command,'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr});write_report(a.output,report)
            if result.returncode:raise ValueError('Prepared helper command failed')
        report['check']=json.loads(result.stdout)
        report['artifacts']={str(path.relative_to(work)):str(path) for path in work.rglob('*') if path.is_file()}
        report['passed']=report['check']['passed'] and report['check']['elapsed_ns']==0
    except Exception as error:report['error']=str(error)
    write_report(a.output,report);print(json.dumps({key:report.get(key) for key in ['passed','error','work']}));return int(not report['passed'])


if __name__=='__main__':sys.exit(main())
