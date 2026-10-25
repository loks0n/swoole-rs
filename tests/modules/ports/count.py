#!/usr/bin/env python3
"""Ordinary stable counter storage: exact accessor bodies, actual Rust ABI and optional whole SDK compile."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys
import overlay
from socket_workflow import configured_flags
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.harness import run_isolated,write_report
from tools.build_upstream import require_build_space

def accessor(text,signature='size_t ListenPort::get_connection_num() const'):
    start=text.index(signature);end=text.index('\n}\n',start)+3
    return text[start:end]

def main(signatures=None,witness=None,scope=None,support=None,source_path="src/server/port.cc",extra_support=None,body_extractor=accessor):
    scope=scope or __doc__;signatures=signatures or ['size_t ListenPort::get_connection_num() const'];witness=witness or Path(__file__).with_suffix('.cc')
    p=argparse.ArgumentParser(description=scope);p.add_argument('--source',type=Path,required=True);p.add_argument('--archive',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--core',type=Path);p.add_argument('--sdk-origin',type=Path,help='Original configured src path when compiling a verified private SDK copy');p.add_argument('--php-config',default='php-config');p.add_argument('--openssl-root',type=Path);p.add_argument('--include',type=Path,action='append',default=[]);p.add_argument('--sanitize',action='store_true');p.add_argument('--rust-asan',action='store_true');a=p.parse_args();overlay.SOURCE=a.source
    if a.rust_asan and (not a.sanitize or '__asan_report_' not in subprocess.check_output(['nm','-u',str(a.archive)],text=True,stderr=subprocess.DEVNULL)):p.error('Actual Rust ASan archive and native sanitizer flag required')
    folder=a.output.resolve().with_suffix('');folder.mkdir(parents=True,exist_ok=True);generated=overlay.generated()
    report={'scope':scope,'pin':overlay.PIN,'method_signatures':signatures,'native_instrumented':a.sanitize,'rust_instrumented':a.rust_asan,'support':{},'sdk':[],'passed':False}
    for name,text in [('original',overlay.original(source_path)),('selected',generated[source_path])]:
        path=folder/(name+'.inc');path.write_text('\n'.join(body_extractor(text,signature)for signature in signatures))
    for name,(source,signature)in (support or {}).items():
        path=folder/name;raw=overlay.original(source);path.write_text(accessor(raw,signature) if signature else raw);report['support'][name]={'source':source,'signature':signature}
    if extra_support:
        report['extra_support'] = extra_support(folder, a)
    def checked_space():
        try:
            require_build_space(ROOT)
        except RuntimeError as error:
            report.update(execution_status='blocked_build_space', error=str(error), passed=False)
            write_report(a.output, report)
            raise
    report['execution_status'] = 'running'
    write_report(a.output, report)
    command=['c++','-std=c++17','-O1','-UNDEBUG','-DSWOOLE_RS_PORTS','-I'+str(ROOT/'native/ports'),'-I'+str(folder),str(witness),str(a.archive.resolve()),'-lpthread','-o',str(folder/'count')]
    if sys.platform=='linux':command+=['-ldl','-lm']
    if a.sanitize:command+=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-g']
    checked_space();r=run_isolated(command,timeout=90);report['compile']={'command':command,'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
    if not r.returncode:
        r=run_isolated([str(folder/'count')],timeout=30);report['run']={'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
    write_report(a.output, report)
    if a.core:
        core=a.core.resolve();flags,configuration=configured_flags(core)
        if a.sdk_origin:
            origin=a.sdk_origin.parent;private=core.parent
            flags=['-I'+str(private/Path(flag[2:]).relative_to(origin)) if flag.startswith('-I') and Path(flag[2:]).is_relative_to(origin) else flag for flag in flags]
            configuration['relocation']={'original_build_root':str(origin),'private_build_root':str(private)}
        configuration['effective_argv']=flags;report['extra_includes']={str(x.resolve()):'explicit private declaration include'for x in a.include};report['configured_compiler_flags']=configuration
        base=['c++','-std=c++14','-O1','-UNDEBUG','-DHAVE_CONFIG_H','-I'+str(core),'-I'+str(core/'include'),'-I'+str(core/'thirdparty/llhttp'),'-I'+str(core/'thirdparty'),'-I'+str(core/'ext-src'),'-I'+str(ROOT/'native/ports'),*['-I'+str(x.resolve())for x in a.include],*flags]
        if a.openssl_root:base+=['-I'+str(a.openssl_root.resolve()/'include')]
        includes=shlex.split(subprocess.check_output([a.php_config,'--includes'],text=True))
        for engine in ['original','selected']:
            for source in ['src/server/port.cc','ext-src/swoole_server_port.cc']:
                raw=overlay.original(source) if engine=='original' else generated[source];path=folder/(engine+'-'+Path(source).name);path.write_text(raw)
                command=[*base,*(['-DSWOOLE_RS_PORTS'] if engine=='selected' else []),*(includes if source.startswith('ext-src') else []),'-fsyntax-only',str(path)]
                checked_space();r=run_isolated(command,cwd=core,timeout=120);report['sdk'].append({'engine':engine,'source':source,'command':command,'compile_cwd':str(core),'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr});write_report(a.output,report)
    report['execution_status']='complete'
    report['passed']=report.get('run',{}).get('exit')==0 and all(r['exit']==0 for r in report['sdk']);write_report(a.output,report);print(json.dumps({'passed':report['passed'],'run':report.get('run'),'sdk_exits':[r['exit']for r in report['sdk']]}));return int(not report['passed'])

if __name__=='__main__':sys.exit(main())
