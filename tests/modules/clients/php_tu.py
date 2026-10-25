#!/usr/bin/env python3
"""Compile exact selected PHP destinations against an explicit frozen SDK config.

Bounded syntax/feature-guard evidence only, not coherent extension/runtime proof.
Uses a private pinned PHP header mirror so quote-includes cannot select an
untracked config next to the shared pinned source.
"""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys
import gate

PHP_SOURCES = [f'ext-src/{name}.cc' for name in (
    'swoole_client', 'swoole_client_async', 'swoole_client_coro',
    'swoole_name_resolver', 'swoole_http_client_coro')]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--sdk',type=Path,required=True)
    p.add_argument('--php-config',default='php-config')
    p.add_argument('--cxx',default='c++')
    p.add_argument('--include',action='append',default=[])
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    work=a.output.parent/(a.output.stem+'-artifacts');work.mkdir(parents=True,exist_ok=True)
    report=dict(passed=False,scope=__doc__,rows=[])
    try:
        mirror=work/'headers';mirror.mkdir(exist_ok=True)
        files=['php_swoole.h','php_swoole_api.h']+subprocess.check_output(
            ['git','-C',str(a.source),'ls-tree','-r','--name-only',gate.PIN,'ext-src'],text=True).splitlines()
        files=[name for name in files if name.endswith('.h')]
        for name in files:
            target=mirror/name;target.parent.mkdir(parents=True,exist_ok=True)
            data=subprocess.check_output(['git','-C',str(a.source),'show',f'{gate.PIN}:{name}'])
            target.write_bytes(data)
        (mirror/'config.h').write_bytes((a.sdk/'config.h').read_bytes())
        patched=work/'patched';patched.mkdir(exist_ok=True)
        subprocess.run(['git','init','-q',str(patched)],check=True)
        for name in gate.overlay_manifest()['upstream_paths']:
            target=patched/name;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(subprocess.check_output(['git','-C',str(a.source),'show',f'{gate.PIN}:{name}']))
        report['overlay']=gate.apply_overlay(patched,work)
        flags=shlex.split(subprocess.check_output([a.php_config,'--includes'],text=True))
        includes=[gate.ROOT/'native/clients',mirror/'ext-src',mirror,
                  a.sdk/'include',a.sdk/'thirdparty',a.sdk/'rust-prefix/include',a.sdk,*map(Path,a.include)]
        flags += [part for path in includes for part in ['-I',str(path)]]
        for name in PHP_SOURCES:
            selected=patched/name
            text=selected.read_text()
            if '#include "swoole_rs_clients.h"' not in text or 'Clients overlay requires --enable-swoole-rs-clients' not in text:
                raise ValueError(f'{name}: missing module header/selected-source guard')
            for enabled in [True,False]:
                command=[a.cxx,'-std=c++17','-fsyntax-only','-DHAVE_CONFIG_H',
                         *(['-DSWOOLE_RS_CLIENTS=1'] if enabled else []),*flags,str(selected)]
                # The compilation input is explicitly this source; never reuse a
                # command whose source path came from an unrelated receipt.
                assert Path(command[-1])==selected
                result=subprocess.run(command,capture_output=True,text=True)
                passed=(result.returncode==0 if enabled else result.returncode!=0 and
                        'Clients overlay requires --enable-swoole-rs-clients' in result.stderr)
                report['rows'].append(dict(source=name,enabled=enabled,
                    command=command,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr,passed=passed))
                a.output.write_text(json.dumps(report,indent=2)+'\n')
        report['passed']=all(row['passed'] for row in report['rows'])
    except Exception as error:
        report['error']=f'{type(error).__name__}: {error}'
    a.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(passed=report['passed'],rows=len(report['rows']),error=report.get('error'))))
    return int(not report['passed'])

if __name__=='__main__':sys.exit(main())
