#!/usr/bin/env python3
"""Differential actual ListenPort bodies and compile actual PHP Port SDK translation units."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import overlay
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.harness import run_isolated,write_report
from tools.build_upstream import require_build_space


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--core',type=Path,required=True);p.add_argument('--archive',type=Path,help='Consume exact selected archive without rebuilding Rust');p.add_argument('--socket-io',choices=['none','probe','connect','custody'],default='none');p.add_argument('--openssl-root',type=Path);p.add_argument('--php-config',default='php-config');p.add_argument('--output',type=Path,required=True);a=p.parse_args();overlay.SOURCE=a.source
    output=a.output.resolve();folder=output.with_suffix('');folder.mkdir(parents=True,exist_ok=True)
    core=a.core.resolve();library=(core/('lib/libswoole.dylib' if sys.platform=='darwin' else 'lib/libswoole.so')).resolve()
    report={'scope':__doc__,'pin':overlay.PIN,'platform':sys.platform,'core_library':str(library),'core_sha256':sha(library),'results':[],'passed':False,'socket_io_profile':a.socket_io}
    generated=overlay.generated();outputs=[]
    base=['c++','-std=c++14','-O1','-UNDEBUG','-DHAVE_CONFIG_H','-I'+str(core),'-I'+str(core/'include'),'-I'+str(core/'thirdparty/llhttp'),'-I'+str(core/'thirdparty'),'-I'+str(core/'ext-src'),'-I'+str(ROOT/'native/ports')]
    if a.openssl_root:base+=['-I'+str(a.openssl_root/'include'),'-L'+str(a.openssl_root/'lib')]
    archive=a.archive.resolve() if a.archive else folder/'libports.a';command=['rustc','--edition','2024','--crate-type','staticlib','-C','opt-level=2',str(ROOT/'crates/ports/src/lib.rs'),'-o',str(archive)]
    if not a.archive:
        require_build_space(ROOT)
        r=run_isolated(command,timeout=90);report['rust_compile']={'command':command,'exit':r.returncode,'stderr':r.stderr}
        if r.returncode:write_report(output,report);return 1
    report['archive_path']=str(archive);report['selected_archive_consumed']=bool(a.archive)
    for engine in ['upstream','rust']:
        directory=folder/engine;directory.mkdir(exist_ok=True);raw=overlay.original('src/server/port.cc') if engine=='upstream' else generated['src/server/port.cc'];(directory/'port.inc').write_text(raw)
        command=[*base,'-I'+str(directory),*(['-DSWOOLE_RS_PORTS'] if engine=='rust' else []),str(Path(__file__).with_suffix('.cc')),*([str(archive)] if engine=='rust' else []),'-L'+str(core/'lib'),'-Wl,-rpath,'+str(core/'lib'),'-lswoole','-lssl','-lcrypto','-lpthread','-o',str(directory/'witness')]
        if sys.platform=='linux':command+=['-ldl','-lm']
        require_build_space(ROOT)
        r=run_isolated(command,timeout=120);row={'engine':engine,'compile':command,'compile_exit':r.returncode,'compile_stderr':r.stderr};report['results'].append(row)
        if r.returncode:write_report(output,report);return 1
        r=run_isolated([str(directory/'witness'),a.socket_io],timeout=45);(directory/'stdout.txt').write_text(r.stdout);(directory/'stderr.txt').write_text(r.stderr);row.update(exit=r.returncode,stderr=r.stderr)
        actual=[line[5:] for line in r.stderr.splitlines() if line.startswith('CORE ')];row['core_identity_verified']=len(actual)==1 and Path(json.loads(actual[0])).resolve()==library and sha(library)==report['core_sha256']
        if not row['core_identity_verified']:write_report(output,report);return 1
        outputs.append(r.stdout)
    report['actual_effect_outputs_match']=outputs[0]==outputs[1];report['case_count']=sum(not line.startswith('SOCKET-IO ') for line in outputs[0].splitlines());report['socket_io_observations']=[line for line in outputs[0].splitlines() if line.startswith('SOCKET-IO ')]
    includes=shlex.split(subprocess.check_output([a.php_config,'--includes'],text=True))
    report['php_sdk']=[]
    for engine in ['upstream','rust']:
        directory=folder/engine;raw=overlay.original('ext-src/swoole_server_port.cc') if engine=='upstream' else generated['ext-src/swoole_server_port.cc'];source=directory/'php-port.cc';source.write_text(raw)
        command=[*base,*includes,*(['-DSWOOLE_RS_PORTS'] if engine=='rust' else []),'-I'+str(core),'-fsyntax-only',str(source)]
        require_build_space(ROOT)
        r=run_isolated(command,timeout=120);report['php_sdk'].append({'engine':engine,'command':command,'exit':r.returncode,'stderr':r.stderr})
    report['passed']=report['actual_effect_outputs_match'] and all(r['exit']==0 for r in report['results']) and all(r['exit']==0 for r in report['php_sdk']);write_report(output,report);print(json.dumps({'passed':report['passed'],'effect_cases':report['case_count'],'actual_effect_outputs_match':report['actual_effect_outputs_match'],'php_sdk_exits':[r['exit'] for r in report['php_sdk']]}));return int(not report['passed'])


if __name__=='__main__':sys.exit(main())
