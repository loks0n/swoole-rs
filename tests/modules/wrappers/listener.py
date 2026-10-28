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
from tools.build_hybrid import hybrid_tree
from tools.harness import run_isolated,write_report
from tools.build_upstream import require_build_space

def prefix(text):
    start=text.index('std::shared_ptr<Server> listen(');end=text.index('    http_server_on_request = cb;',start)
    return text[start:end]+'    return server;\n}\n'

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--archive',type=Path,required=True,help='Rust archive of the hybrid build under test');p.add_argument('--output',type=Path,required=True);p.add_argument('--core',type=Path);p.add_argument('--include',type=Path,action='append',default=[]);p.add_argument('--sanitize',action='store_true');p.add_argument('--rust-asan',action='store_true');a=p.parse_args();overlay.SOURCE=a.source
    if a.rust_asan and (not a.sanitize or '__asan_report_'not in subprocess.check_output(['nm','-u',str(a.archive)],text=True,stderr=subprocess.DEVNULL)):p.error('Actual instrumented archive and native sanitizer required')
    folder=a.output.resolve().with_suffix('');folder.mkdir(parents=True,exist_ok=True)
    # Original side from the pin, selected side from the hybrid build's fully patched tree.
    hybrid_source,hybrid_flags=hybrid_tree(a.archive);sides={'original':overlay.original,'selected':lambda path:(hybrid_source/path).read_text()}
    report={'scope':__doc__,'pin':overlay.PIN,'hybrid_tree':str(hybrid_source),'sdk':[],'native_instrumented':a.sanitize,'rust_instrumented':a.rust_asan,'passed':False,'native_io_executed':False,'whole_listener_lifecycle_qualified':False,'performance_qualified':False}
    # Each side's files share names in their own folder; the witness includes them by name.
    for side,read in sides.items():
        (folder/side).mkdir(exist_ok=True);(folder/side/'body.inc').write_text(prefix(read('src/wrapper/http.cc')))
        raw=read('include/swoole.h');start=raw.index('static inline long sw_atol(');end=raw.index('\nstatic inline void sw_memset_zero',start);(folder/side/'numbers.inc').write_text(raw[start:end])
    # Two translation units: the original side with only its pinned fragments, the selected
    # side and the driver with the hybrid build's flags.
    common=['c++','-std=c++17','-O1','-UNDEBUG',*(['-fsanitize=address,undefined','-fno-sanitize-recover=all','-g'] if a.sanitize else [])];witness=str(Path(__file__).with_suffix('.cc'))
    original=[*common,'-c','-DWRAPPERS_SIDE=original','-I'+str(folder/'original'),witness,'-o',str(folder/'original.o')]
    command=[*common,'-DWRAPPERS_SIDE=selected','-DWRAPPERS_DRIVER',*hybrid_flags,'-I'+str(folder/'selected'),witness,str(folder/'original.o'),str(a.archive.resolve()),'-lpthread','-o',str(folder/'listener')]
    if sys.platform=='linux':command+=['-ldl','-lm']
    require_build_space(ROOT);r=run_isolated(original,timeout=90)
    if not r.returncode:r=run_isolated(command,timeout=90)
    report['compile']={'commands':[original,command],'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
    if not r.returncode:
        r=run_isolated([str(folder/'listener')],timeout=30);report['run']={'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
    if a.core:
        core=a.core.resolve();base=['c++','-std=c++14','-O1','-UNDEBUG','-DHAVE_CONFIG_H',*['-I'+str(path)for path in [core,core/'include',core/'ext-src',core/'thirdparty',core/'thirdparty/llhttp',ROOT/'native/wrappers',core.parent/'rust-prefix/include',*[x.resolve()for x in a.include]]]]
        report['sdk_dependency_includes']=[str(x.resolve())for x in a.include]
        for engine in ['original','selected']:
            for source in ['src/wrapper/event.cc','src/wrapper/http.cc']:
                text=sides[engine](source);path=folder/(engine+'-'+Path(source).name);path.write_text(text);command=[*base,*(['-DSWOOLE_RS_WRAPPERS']if engine=='selected'else[]),'-fsyntax-only',str(path)];require_build_space(ROOT);r=run_isolated(command,cwd=core,timeout=120);report['sdk'].append({'engine':engine,'source':source,'command':command,'cwd':str(core),'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
    report['passed']=report.get('run',{}).get('exit')==0 and all(x['exit']==0 for x in report['sdk']);write_report(a.output,report);print(json.dumps({'passed':report['passed'],'run':report.get('run'),'sdk_exits':[x['exit']for x in report['sdk']]}));return int(not report['passed'])

if __name__=='__main__':sys.exit(main())
