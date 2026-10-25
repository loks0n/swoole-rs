#!/usr/bin/env python3
"""Clean pinned-header mirror plus captured old SDK config: syntax only, not runtime."""
import argparse
import io
import json
import re
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile
import uuid
from gate import ROOT,PIN,sha,stage
from tools.build_upstream import require_build_space
from tools.harness import run_isolated,write_report


def memory_headers(mirror):
    """Current M12 header dependency, in a private selected mirror only."""
    directory=ROOT/'migration/patches/memory'
    manifest=json.loads((directory/'manifest.json').read_text())
    if manifest['upstream_commit']!=PIN: raise ValueError('Memory dependency pin differs')
    selected=[]
    for item in manifest['patches']:
        names=[name for name in item['upstream_paths'] if name.startswith('include/') and Path(name).suffix in ['.h','.hpp','.inc']]
        if not names: continue
        patch=directory/item['path']
        if sha(patch)!=item['sha256']: raise ValueError('Memory dependency checksum differs')
        selected.append((patch,names))
    headers=sorted((ROOT/'native/memory').glob('*.h'))
    if not any(path.name=='swoole_rs_memory_table_v2.h' for path in headers): raise ValueError('Concrete TableV2 dependency is missing')
    subprocess.run(['git','init','-q',str(mirror)],check=True)
    for patch,names in selected:
        args=['git','apply',*['--include='+name for name in names],str(patch)]
        subprocess.run([*args[:2],'--check',*args[2:]],cwd=mirror,check=True,capture_output=True)
        subprocess.run(args,cwd=mirror,check=True,capture_output=True)
    for path in headers:
        shutil.copy2(path,mirror/path.name)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--sdk-export',type=Path,required=True)
    p.add_argument('--php-config',default='php-config');p.add_argument('--include',type=Path,action='append',default=[])
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    output=a.output.resolve();work=output.parent/('phpcollections-sdk-'+uuid.uuid4().hex);work.mkdir(parents=True)
    r={'passed':False,'pin':PIN,'scope':__doc__,'work':str(work),'commands':[]}
    try:
        require_build_space(ROOT);require_build_space(work)
        config=a.sdk_export.parent/'config.h';export=json.loads(a.sdk_export.read_text())
        config_sha256=export['files']['config.h']['sha256']
        if sha(config)!=config_sha256:raise ValueError('SDK config identity differs')
        shutil.copy2(config,work/'config.h');shutil.copy2(a.sdk_export,work/'export.json')
        r.update(sdk_source_ref=export['source_ref'])
        names=subprocess.check_output(['git','-C',str(a.source),'ls-tree','-r','--name-only',PIN],text=True).splitlines()
        names=[n for n in names if Path(n).suffix in ['.h','.hpp','.inc']]
        data=subprocess.check_output(['git','-C',str(a.source),'archive',PIN,'--',*names])
        mirror=work/'headers';mirror.mkdir()
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            for item in tar:
                if not item.isfile():continue
                path=Path(item.name)
                if path.is_absolute() or '..' in path.parts:raise ValueError('Unsafe archive path')
                out=mirror/path;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(tar.extractfile(item).read())
        # A newer captured config may already enable this module. Keep the
        # immutable input unchanged, but make this syntax variant's module flag
        # controlled solely by each expected enabled/disabled command below.
        syntax_config = re.sub(r'(?m)^#define SWOOLE_RS_PHPCOLLECTIONS(?:[ \t]+[^\n]*)?$',
                               '/* #undef SWOOLE_RS_PHPCOLLECTIONS */', (work/'config.h').read_text())
        (mirror/'config.h').write_text(syntax_config)
        shutil.copy2(ROOT/'native/phpcollections/swoole_rs_phpcollections.h',mirror/'swoole_rs_phpcollections.h')
        overlay=work/'overlay';overlay.mkdir();r['sources']=stage(a.source,overlay)
        includes=shlex.split(subprocess.check_output([a.php_config,'--includes'],text=True))
        r['php_version']=subprocess.check_output([a.php_config,'--version'],text=True).strip()
        depflags=subprocess.run(['pkg-config','--cflags','openssl','libpcre2-8','libcurl'],capture_output=True,text=True)
        r['pkg_config']=dict(returncode=depflags.returncode,stdout=depflags.stdout,stderr=depflags.stderr)
        base=['c++','-std=c++17','-fsyntax-only','-DENABLE_PHP_SWOOLE','-DHAVE_CONFIG_H',
              *['-I'+str(x) for x in [mirror,mirror/'include',mirror/'ext-src',mirror/'thirdparty',mirror/'thirdparty/llhttp',*a.include]],
              *includes,*shlex.split(depflags.stdout)]
        selected_headers_ready=False
        for engine,enabled in [('native',False),('selected',True),('selected',False)]:
            if engine=='selected' and not selected_headers_ready:
                memory_headers(mirror)
                selected_headers_ready=True
            for name in r['sources']:
                unit=work/(engine+'-'+str(enabled)+'-'+Path(name).name)
                unit.write_bytes(subprocess.check_output(['git','-C',str(a.source),'show',PIN+':'+name]) if engine=='native' else (overlay/name).read_bytes())
                deps=unit.with_suffix('.d');cmd=[*base,*(['-DSWOOLE_RS_PHPCOLLECTIONS'] if enabled else ['-USWOOLE_RS_PHPCOLLECTIONS']),'-MD','-MF',str(deps),unit]
                require_build_space(ROOT);require_build_space(work);x=run_isolated(list(map(str,cmd)),timeout=90)
                refusal=engine=='selected' and not enabled
                observed=(x.returncode!=0 and 'PHP collections overlay requires --enable-swoole-rs-phpcollections' in x.stderr) if refusal else x.returncode==0
                row=dict(engine=engine,enabled=enabled,path=name,command=list(map(str,cmd)),returncode=x.returncode,stdout=x.stdout,stderr=x.stderr,expected_refusal=refusal,passed=observed)
                if x.returncode==0:
                    paths=shlex.split(deps.read_text().replace('\\\n',' ').split(':',1)[1])
                    if any(str(a.source.resolve()) in str(Path(x).resolve()) for x in paths):raise ValueError('Compiler escaped pinned mirror')
                r['commands'].append(row);write_report(output,r)
        r['passed']=len(r['commands'])==6 and all(x['passed'] for x in r['commands'])
        if sha(config)!=config_sha256:raise ValueError('SDK config changed during check')
    except Exception as e:
        r['error']=str(e)
        if isinstance(e,subprocess.CalledProcessError):r['stderr']=str(e.stderr)
    write_report(output,r);print(json.dumps({k:r.get(k) for k in ['passed','error','work']}));return int(not r['passed'])
if __name__=='__main__':sys.exit(main())
