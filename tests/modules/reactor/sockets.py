#!/usr/bin/env python3
"""Whole actual registry callers, inert key/token semantics and separate Native live/copy order gate."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from ordered_gate import ROOT, PIN, block, apply_patch_verified
from tools.build_upstream import require_build_space
from tools.harness import run_compiler
from tools.harness import run_isolated

FLAG = '#if defined(SWOOLE_RS_REACTOR_SOCKETS_OWNED) && SWOOLE_RS_REACTOR_SOCKETS_OWNED'

def select_owned(text, enabled):
    """Select ONLY this module's literal flag. Preserve every other source byte."""
    result=[]; owned=False; depth=0; active=True
    for line in text.splitlines(keepends=True):
        stripped=line.strip()
        if not owned and stripped == FLAG:
            owned=True;depth=0;active=enabled;continue
        if owned:
            if stripped.startswith(('#if ', '#ifdef ', '#ifndef ')): depth+=1
            elif stripped=='#endif':
                if depth==0: owned=False;active=True;continue
                depth-=1
            elif stripped=='#else' and depth==0:active=not enabled;continue
        if active:result.append(line)
    if owned:raise ValueError('Unterminated owned conditional')
    return ''.join(result)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True);p.add_argument('--sanitize',action='store_true');p.add_argument('--standard',choices=['c++14','c++17','c++20'],help='Explicit supplemental standard; default retains all3');p.add_argument('--order-model',action='store_true',help='Separate30-scenario whole live/copy order model; retains default163-assertion inventory');a=p.parse_args()
    fixture=ROOT/'tests/modules/reactor'/('sockets_order.cc' if a.order_model else 'sockets.cc')
    standards=[a.standard] if a.standard else ['c++14','c++17','c++20']
    if a.report.exists():raise ValueError('Choose a unique report path')
    report=dict(scope=__doc__,assigned_to='@loks0n',pin=PIN,fixture=str(fixture),order_model=a.order_model,standards=standards,patch_application=[],sources={},commands=[],observations=[],source_controls_passed=False,order_passed=False,passed=False,actual_production_sdk=False,actual_production_runtime=False,performance=False,activation=False)
    with tempfile.TemporaryDirectory(prefix='swr-registry-') as temp:
        tree=Path(temp);manifest=ROOT/'migration/patches/reactor/manifest.json';entries=json.loads(manifest.read_text())['patches'];original={}
        try:
            for ent in entries:
                for name in ent['upstream_paths']:
                    if name not in original:
                        data=subprocess.check_output(['git','-C',str(a.source),'show',PIN+':'+name]);original[name]=data.decode();path=tree/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
            for ent in entries:report['patch_application'].append(apply_patch_verified(tree,manifest.parent/ent['path'],ent['upstream_paths'],ent['sha256']))
            selected=(tree/'include/swoole_reactor.h').read_text();native=original['include/swoole_reactor.h']
            for variant in ['native','selected-default','selected-off','selected-owned']:
                owned=variant=='selected-owned';header=select_owned(selected,owned) if variant!='native' else native
                field=next(line for line in header.splitlines() if line.strip() in ['std::unordered_map<int, network::Socket *> sockets_;','ReactorSocketRegistry sockets_;'])
                signatures=['bool exists(const int fd)', 'size_t get_event_num()', 'network::Socket *get_socket(', 'void foreach_socket(', 'void _add(', 'void _set(', 'bool _exists(', 'void _del(']
                signatures+=['ReactorSocketView socket_registry_view()', 'ReactorSocketSnapshot socket_registry_snapshot()'] if owned else ['const std::unordered_map<int, network::Socket *> &get_sockets()']
                methods=[block(header,header.index(sig))[0] for sig in signatures]
                report['sources'][variant]=dict(methods=signatures,field=field.strip())
                (tree/'registry.inc').write_text('namespace swoole { class RegistryFacade {\n'+field+'\npublic:\n'+'\n'.join(methods)+'\n};}\n')
                for standard in standards:
                    binary=tree/(variant+'-'+standard);cmd=['c++','-std='+standard,'-O1','-g','-I'+str(tree),'-I'+str(ROOT/'native/reactor'),fixture,a.archive.resolve(),'-lpthread','-o',binary]
                    if variant!='native':cmd+=['-DSWOOLE_RS_REACTOR=1']
                    if variant in ['selected-off','selected-owned']:cmd+=['-DSWOOLE_RS_REACTOR_SOCKETS_OWNED='+str(int(owned))]
                    if a.sanitize:cmd+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
                    if sys.platform.startswith('linux'):cmd+=['-ldl','-lm']
                    for stage,command in [('compile',cmd),('execute',[binary])]:
                        require_build_space(ROOT);require_build_space(tree)
                        result=run_compiler(command) if stage=='compile' else vars(run_isolated(list(map(str,command)),cwd=tree,timeout=60))
                        report['commands'].append(dict(variant=variant,standard=standard,stage=stage,command=list(map(str,command)),exit=result['returncode'],stdout=result['stdout'],stderr=result['stderr']))
                        if result['returncode'] or result['stderr']:raise RuntimeError(variant+' '+stage+' failed or warned')
                    report['observations'].append(dict(variant=variant,standard=standard,result=json.loads(result['stdout'])))
                    # The owner-private compiler cache keeps its artifact; release this
                    # disposable per-profile copy after hashing/execution, not all12 at end.
                    binary.unlink()
            results=report['observations'];native=results[0]['result']
            if any(r['result']['common']!=native['common'] for r in results):raise RuntimeError('Common key/token/assertion observations differ')
            report['source_controls_passed']=True
            report['order_passed']=all(r['result']['live_order']==native['live_order'] and r['result']['snapshot_order']==native['snapshot_order'] for r in results)
            report['order_scope']='Actual local standard-library live and by-value-copy traversal, separately observed; insertion order is NOT inferred Native parity'
            if not report['order_passed']:report['error']='Native live/copy ordering differs: explicit capability activation blocker'
            report['passed']=report['source_controls_passed'] and report['order_passed']
        except Exception as error:report['error']=str(error)
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({key:report.get(key) for key in ['passed','source_controls_passed','order_passed','error']}));return int(not report['passed'])

if __name__=='__main__':raise SystemExit(main())
