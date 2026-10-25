#!/usr/bin/env python3
"""Linux actual Rust ASan plus native callers; separate invalid-ABI-caller reachability control."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.build_upstream import require_build_space
from tools.harness import run_isolated,write_report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--core',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if sys.platform!='linux':p.error('Linux-only matched runtime; do not substitute the incompatible Mac native/Rust pair')
    folder=a.output.resolve().with_suffix('');folder.mkdir(parents=True,exist_ok=True);archive=folder/'libports-asan.a'
    report={'scope':__doc__,'valid_checks':[],'passed':False,'rust_compile_environment':{'RUSTC_BOOTSTRAP':'1'},'toolchain':{name:subprocess.check_output(command,text=True,stderr=subprocess.STDOUT) for name,command in [('rustc',['rustc','-vV']),('c++',['c++','--version'])]}}
    command=['rustc','--edition','2024','--crate-type','staticlib','--crate-name','swoole_rs_ports','--target','aarch64-unknown-linux-gnu','-Zsanitizer=address','-Copt-level=1','-g',str(ROOT/'crates/ports/src/lib.rs'),'-o',str(archive)]
    require_build_space(ROOT);r=run_isolated(command,env={**os.environ,'RUSTC_BOOTSTRAP':'1'},timeout=90);report['compile']={'command':command,'exit':r.returncode,'stderr':r.stderr}
    if r.returncode:write_report(a.output,report);return 1
    report['rust_asan_symbols']= '__asan_report_' in subprocess.check_output(['nm','-u',str(archive)],text=True,stderr=subprocess.DEVNULL)
    for script,extra in [('gate.py',['--rust-asan']),('listen.py',[]),('socket_workflow.py',['--core',str(a.core)])]:
        output=folder/(Path(script).stem+'.json');command=[sys.executable,str(ROOT/'tests/modules/ports'/script),'--source',str(a.source),'--archive',str(archive),'--sanitize',*extra,'--output',str(output)]
        r=run_isolated(command,timeout=120);row={'script':script,'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'report':str(output)};report['valid_checks'].append(row)
        if output.exists():row['result']=json.loads(output.read_text())
        if r.returncode:write_report(a.output,report);return 1
    # Intentionally invalid ABI caller, not upstream input or valid-contract parity.
    probe=folder/'invalid-caller.cc';probe.write_text('#include "swoole_rs_ports.h"\nint main(){auto p=new uint8_t[7]{0,99,111,110,110,101,99};return swr_v1_ports_event(p+1,7,0).index;}\n')
    command=['c++','-std=c++14','-O1','-g','-DSWOOLE_RS_PORTS','-I'+str(ROOT/'native/ports'),str(probe),str(archive),'-fsanitize=address,undefined','-fno-sanitize-recover=all','-lpthread','-ldl','-lm','-o',str(folder/'invalid-caller')]
    require_build_space(ROOT);r=run_isolated(command,timeout=90);control={'scope':'Expected invalid caller; independent of valid checks and not a supported-input assertion','compile':command,'compile_exit':r.returncode,'compile_stderr':r.stderr}
    if not r.returncode:
        r=run_isolated([str(folder/'invalid-caller')],timeout=15);control.update(exit=r.returncode,stderr=r.stderr,detected=r.returncode!=0 and 'AddressSanitizer: heap-buffer-overflow' in r.stderr and 'swr_v1_ports_event' in r.stderr)
    report['invalid_caller_control']=control
    if not control['compile_exit']:report['linked_runtime']=subprocess.check_output(['ldd',str(folder/'invalid-caller')],text=True,stderr=subprocess.STDOUT)
    report['passed']=report['rust_asan_symbols'] and bool(control.get('detected'));write_report(a.output,report);print(json.dumps({'passed':report['passed'],'valid_check_count':len(report['valid_checks']),'expected_invalid_caller_detected':control.get('detected')}));return int(not report['passed'])


if __name__=='__main__':sys.exit(main())
