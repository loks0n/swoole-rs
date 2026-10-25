#!/usr/bin/env python3
"""Exact normal listener address-prefix policy and optional whole native wrapper SDK; no network or parser execution."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import overlay
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.harness import run_isolated,write_report
from tools.build_upstream import require_build_space

def prefix(text):
    start=text.index('std::shared_ptr<Server> listen(');end=text.index('    http_server_on_request = cb;',start)
    return text[start:end]+'    return server;\n}\n'

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--archive',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--core',type=Path);p.add_argument('--include',type=Path,action='append',default=[]);p.add_argument('--sanitize',action='store_true');p.add_argument('--rust-asan',action='store_true');a=p.parse_args();overlay.SOURCE=a.source
    if a.rust_asan and (not a.sanitize or '__asan_report_'not in subprocess.check_output(['nm','-u',str(a.archive)],text=True,stderr=subprocess.DEVNULL)):p.error('Actual instrumented archive and native sanitizer required')
    folder=a.output.resolve().with_suffix('');folder.mkdir(parents=True,exist_ok=True);generated=overlay.generated();report={'scope':__doc__,'pin':overlay.PIN,'sdk':[],'native_instrumented':a.sanitize,'rust_instrumented':a.rust_asan,'passed':False,'native_io_executed':False,'whole_listener_lifecycle_qualified':False,'performance_qualified':False}
    for name,text in [('original',overlay.original('src/wrapper/http.cc')),('selected',generated['src/wrapper/http.cc'])]:
        (folder/(name+'.inc')).write_text(prefix(text))
    raw=overlay.original('include/swoole.h');start=raw.index('static inline long sw_atol(');end=raw.index('\nstatic inline void sw_memset_zero',start);(folder/'numbers.inc').write_text(raw[start:end])
    command=['c++','-std=c++17','-O1','-UNDEBUG','-DSWOOLE_RS_WRAPPERS','-I'+str(ROOT/'native/wrappers'),'-I'+str(folder),str(Path(__file__).with_suffix('.cc')),str(a.archive.resolve()),'-lpthread','-o',str(folder/'listener')]
    if sys.platform=='linux':command+=['-ldl','-lm']
    if a.sanitize:command+=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-g']
    require_build_space(ROOT);r=run_isolated(command,timeout=90);report['compile']={'command':command,'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
    if not r.returncode:
        r=run_isolated([str(folder/'listener')],timeout=30);report['run']={'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
    if a.core:
        core=a.core.resolve();base=['c++','-std=c++14','-O1','-UNDEBUG','-DHAVE_CONFIG_H',*['-I'+str(path)for path in [core,core/'include',core/'ext-src',core/'thirdparty',core/'thirdparty/llhttp',ROOT/'native/wrappers',core.parent/'rust-prefix/include',*[x.resolve()for x in a.include]]]]
        report['sdk_dependency_includes']=[str(x.resolve())for x in a.include]
        for engine in ['original','selected']:
            for source in ['src/wrapper/event.cc','src/wrapper/http.cc']:
                text=overlay.original(source)if engine=='original'else generated[source];path=folder/(engine+'-'+Path(source).name);path.write_text(text);command=[*base,*(['-DSWOOLE_RS_WRAPPERS']if engine=='selected'else[]),'-fsyntax-only',str(path)];require_build_space(ROOT);r=run_isolated(command,cwd=core,timeout=120);report['sdk'].append({'engine':engine,'source':source,'command':command,'cwd':str(core),'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
    report['passed']=report.get('run',{}).get('exit')==0 and all(x['exit']==0 for x in report['sdk']);write_report(a.output,report);print(json.dumps({'passed':report['passed'],'run':report.get('run'),'sdk_exits':[x['exit']for x in report['sdk']]}));return int(not report['passed'])

if __name__=='__main__':sys.exit(main())
