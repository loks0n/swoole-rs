#!/usr/bin/env python3
"""Compile both actual PHP helper TUs with stdext enabled/disabled; no runtime claim."""
import argparse
import io
import json
import os
import re
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile
import uuid
from gate import ROOT,PIN,sha,stage,body
from tools.build_upstream import require_build_space
from tools.harness import run_isolated,write_report


def dependency_flags():
    """Preserve every optional probe; one failure must not erase other flags."""
    probes={}
    for package in ['openssl','libpcre2-8','libcurl','libpq']:
        try:
            result=subprocess.run(['pkg-config','--cflags',package],text=True,capture_output=True)
            probes[package]={'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
        except OSError as error:
            probes[package]={'returncode':None,'stdout':'','stderr':str(error),'error_type':type(error).__name__}
    return {'returncode':int(any(row['returncode']!=0 for row in probes.values())),
            'stdout':' '.join(row['stdout'].strip() for row in probes.values() if row['returncode']==0),
            'stderr':'\n'.join(package+': '+row['stderr'].strip() for package,row in probes.items() if row['stderr']),
            'probes':probes}


def facade_surface(native,selected):
    """Pinned-format source guard, in addition to actual compiler/layout checks."""
    classes={}
    for name in ['String','KeyValue','ArrayIterator','Array','Variable','CharPtr','Callable']:
        def declarations(text):
            piece=body(text,'class '+name+' {')
            methods=list(re.finditer(r'^    (\S[^\n{};]*\([^\n{};]*\)[^\n{};]*\{)',piece,re.M))
            skeleton=piece
            for match in reversed(methods):
                end=match.start()+len(body(piece,match.group(0)))
                skeleton=skeleton[:match.end()]+skeleton[end-1:]
            return skeleton,len(methods)
        original,count=declarations(native);candidate,selected_count=declarations(selected)
        if original!=candidate or count!=selected_count:
            raise ValueError('Common facade declarations changed: '+name)
        classes[name]={'inline_methods':count}
    def macros(text):
        lines=iter(text.splitlines(keepends=True));definitions=[]
        for line in lines:
            if re.match(r'^\s*#\s*define\s',line):
                value=line
                while line.rstrip('\r\n').endswith('\\'):
                    line=next(lines);value+=line
                definitions.append(value)
        return definitions
    original=macros(native)
    if original!=macros(selected):raise ValueError('Public macro definitions changed')
    return {'matched':True,'classes':classes,'macro_definitions':len(original)}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--sdk-export',type=Path,required=True,help='Immutable completed export.json with config.h identity')
    p.add_argument('--php-config',default='php-config')
    p.add_argument('--include',type=Path,action='append',default=[])
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();output=a.output.resolve();work=output.parent/('phphelpers-sdk-'+uuid.uuid4().hex);work.mkdir(parents=True)
    report={'passed':False,'pin':PIN,'scope':__doc__,'work':str(work),'commands':[]}
    try:
        require_build_space(ROOT)
        config=a.sdk_export.parent/'config.h';export=json.loads(a.sdk_export.read_text())
        config_sha256=export['files']['config.h']['sha256']
        if sha(config)!=config_sha256:raise ValueError('Captured SDK config differs from immutable export')
        shutil.copy2(config,work/'config.h');shutil.copy2(a.sdk_export,work/'export.json')
        report['selected_source_ref']=export['source_ref']
        names=subprocess.check_output(['git','-C',str(a.source),'ls-tree','-r','--name-only',PIN],text=True).splitlines()
        names=[name for name in names if Path(name).suffix in ['.h','.hpp','.inc']]
        # stdext deliberately includes this vendored C fragment; it stays native.
        names.append('thirdparty/php/zend/zend_execute.c')
        archive=subprocess.check_output(['git','-C',str(a.source),'archive',PIN,'--',*names])
        mirror=work/'headers';mirror.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
            for item in bundle:
                if not item.isfile():continue
                path=Path(item.name)
                if path.is_absolute() or '..' in path.parts:raise ValueError('Unsafe pinned header path')
                target=mirror/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(bundle.extractfile(item).read())
        shutil.copy2(config,mirror/'config.h')
        shutil.copy2(ROOT/'native/phphelpers/swoole_rs_phphelpers.h',mirror/'swoole_rs_phphelpers.h')
        # entrypoint.py checks this against the pinned public header ABI.
        report['mirror_sha256']={'ext-src/php_swoole_cxx.h':sha(mirror/'ext-src/php_swoole_cxx.h')}
        overlay=work/'overlay';overlay.mkdir();report['sources']=stage(a.source,overlay)
        report['declaration_surface']=facade_surface((mirror/'ext-src/php_swoole_cxx.h').read_text(),(overlay/'ext-src/php_swoole_cxx.h').read_text())
        includes=shlex.split(subprocess.check_output([a.php_config,'--includes'],text=True))
        report['php_version']=subprocess.check_output([a.php_config,'--version'],text=True).strip()
        report['php_includes']=includes
        report['pkg_config']=dependency_flags()
        report['cpp_standards']=['c++14','c++17']
        base=['c++','-std=c++14','-fsyntax-only','-DENABLE_PHP_SWOOLE','-DHAVE_CONFIG_H',
              *['-I'+str(p) for p in [mirror,mirror/'include',mirror/'ext-src',mirror/'thirdparty',mirror/'thirdparty/llhttp',*a.include]],
              *includes,*shlex.split(report['pkg_config']['stdout'])]
        profiles={}
        for enabled in [False,True]:
            profile=work/('profile-'+str(enabled));profile.mkdir()
            shutil.copy2(mirror/'php_swoole.h',profile/'php_swoole.h')
            (profile/'config.h').write_text(config.read_text()+'\n/* Private syntax-only optional-feature profile. */\n#undef SW_STDEXT\n'+('#define SW_STDEXT 1\n' if enabled else ''))
            profiles[enabled]=profile
        report['stdext_profiles']={str(enabled):str(profile) for enabled,profile in profiles.items()}
        feature_names=sorted(set(__import__('re').findall(r'^#define (SWOOLE_RS_[A-Z0-9_]+)\b',config.read_text(),__import__('re').M)))
        report['feature_profiles']={'native':[],'rust':['SWOOLE_RS_PHPHELPERS'],'combined':sorted(set(feature_names+['SWOOLE_RS_PHPHELPERS']))}
        report['selected_header_sha256']=sha(overlay/'ext-src/php_swoole_cxx.h')
        engine_headers={}
        for engine,features in report['feature_profiles'].items():
            engine_mirror=work/('headers-'+engine)
            shutil.copytree(mirror,engine_mirror,copy_function=os.link)
            header=engine_mirror/'ext-src/php_swoole_cxx.h'
            header.unlink()
            shutil.copy2(mirror/'ext-src/php_swoole_cxx.h' if engine=='native' else overlay/'ext-src/php_swoole_cxx.h',header)
            engine_headers[engine]=header
            engine_base=[item.replace('-I'+str(mirror),'-I'+str(engine_mirror),1) if item.startswith('-I'+str(mirror)) else item for item in base]
            for enabled in [False,True]:
                profile=work/(engine+'-profile-'+str(enabled));profile.mkdir()
                shutil.copy2(mirror/'php_swoole.h',profile/'php_swoole.h')
                (profile/'config.h').write_text((profiles[enabled]/'config.h').read_text()+'\n'+''.join('#undef '+name+'\n' for name in feature_names+['SWOOLE_RS_PHPHELPERS'])+''.join('#define '+name+' 1\n' for name in features))
                for name in report['sources']:
                    if not name.endswith('.cc'):continue
                    unit=work/(engine+'-'+str(enabled)+'-'+Path(name).name)
                    raw=(subprocess.check_output(['git','-C',str(a.source),'show',PIN+':'+name]) if engine=='native' else (overlay/name).read_bytes())
                    unit.write_bytes(raw)
                    for standard in report['cpp_standards']:
                        dep=unit.with_suffix('.'+standard+'.d')
                        command=[engine_base[0],'-std='+standard,*engine_base[2:5],'-I'+str(profile),*engine_base[5:],
                                 '-MD','-MF',str(dep),str(unit)]
                        require_build_space(ROOT)
                        result=run_isolated(command,timeout=120)
                        row={'cpp_standard':standard,'engine':engine,'stdext_enabled':enabled,'unit':name,'command':command,
                             'feature_macros':features,'config_sha256':sha(profile/'config.h'),
                             'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
                        report['commands'].append(row)
                        if result.returncode==0:
                            paths=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1])
                            row['dependencies_sha256']={str(Path(path).resolve()):sha(path) for path in paths}
                            if (enabled or name.endswith('php_swoole_cxx.cc')) and str(header.resolve()) not in row['dependencies_sha256']:raise ValueError('Actual TU did not consume its assigned facade header')
                            if any(str(a.source.resolve()) in path for path in row['dependencies_sha256']):raise ValueError('Compiler escaped mirror into pinned checkout')
                        write_report(output,report)
        # Observe only public sizes/alignment: no Zend objects or VM calls.
        layout=work/'layout.cc'
        classes=['String','KeyValue','ArrayIterator','Array','Variable','CharPtr','Callable']
        layout.write_text('#include "php_swoole_cxx.h"\n#include <cstdio>\nint main() {\n'+''.join(
            'std::printf("'+name+':%zu:%zu\\n",sizeof(zend::'+name+'),alignof(zend::'+name+'));\n' for name in classes)+'}\n')
        report['layout_commands']=[]
        for engine in report['feature_profiles']:
            profile=work/(engine+'-profile-True');binary=work/(engine+'-layout')
            engine_mirror=engine_headers[engine].parents[1]
            engine_base=[item.replace('-I'+str(mirror),'-I'+str(engine_mirror),1) if item.startswith('-I'+str(mirror)) else item for item in base]
            command=[engine_base[0],'-std=c++14',*engine_base[3:5],'-I'+str(profile),*engine_base[5:],'-O2',str(layout),'-o',str(binary)]
            require_build_space(ROOT);compiled=run_isolated(command,timeout=120)
            row={'engine':engine,'command':command,'exit':compiled.returncode,'stdout':compiled.stdout,'stderr':compiled.stderr}
            report['layout_commands'].append(row)
            if not compiled.returncode:
                observed=run_isolated([str(binary)],timeout=10)
                row.update(run_exit=observed.returncode,layout=observed.stdout,run_stderr=observed.stderr)
        # Force optimized code generation for the whole actual inline helper.
        # This compiles a caller only; it never executes fn or coroutine::async.
        async_unit=work/'async-codegen.cc'
        async_unit.write_text('#include "php_swoole_cxx.h"\n'
                              'bool swr_sdk_force_async(bool blocking,const std::function<void(void)>& fn) {\n'
                              '    return php_swoole_async(blocking,fn);\n}\n')
        report['async_codegen_commands']=[]
        for engine in report['feature_profiles']:
            profile=work/(engine+'-profile-True')
            engine_mirror=engine_headers[engine].parents[1]
            engine_base=[item.replace('-I'+str(mirror),'-I'+str(engine_mirror),1) if item.startswith('-I'+str(mirror)) else item for item in base]
            for standard in report['cpp_standards']:
                obj=work/(engine+'-async-'+standard+'.o');dep=obj.with_suffix('.d')
                command=[engine_base[0],'-std='+standard,*engine_base[3:5],'-I'+str(profile),*engine_base[5:],
                         '-O2','-Wall','-Werror','-MD','-MF',str(dep),'-c',str(async_unit),'-o',str(obj)]
                require_build_space(ROOT);compiled=run_isolated(command,timeout=120)
                row={'engine':engine,'cpp_standard':standard,'command':command,'exit':compiled.returncode,
                     'stdout':compiled.stdout,'stderr':compiled.stderr}
                report['async_codegen_commands'].append(row)
                if not compiled.returncode:
                    paths=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1])
                    if str(engine_headers[engine].resolve()) not in {str(Path(path).resolve()) for path in paths}:
                        raise ValueError('Optimized async caller missed assigned whole header')
                    symbols=run_isolated(['nm','-u',str(obj)],timeout=20)
                    row.update(nm_exit=symbols.returncode,undefined_symbols=symbols.stdout,nm_stderr=symbols.stderr)
                    imported='swr_v1_phphelpers_async' in symbols.stdout
                    row['expected_async_import']=symbols.returncode==0 and not symbols.stderr and imported==(engine!='native')
                write_report(output,report)
        report['async_codegen_passed']=len(report['async_codegen_commands'])==6 and all(
            row['exit']==0 and row.get('expected_async_import') for row in report['async_codegen_commands'])
        report['layout_matched']=all(row['exit']==0 and row.get('run_exit')==0 and not row.get('run_stderr') for row in report['layout_commands']) and len({row.get('layout') for row in report['layout_commands']})==1
        report['passed']=len(report['commands'])==24 and all(row['returncode']==0 for row in report['commands']) and report['layout_matched'] and report['async_codegen_passed']
        if sha(config)!=config_sha256:raise ValueError('Input SDK config changed')
    except Exception as error:
        report['passed']=False;report['error']=str(error)
        if isinstance(error,subprocess.CalledProcessError):report['error_stderr']=str(error.stderr)
    write_report(output,report);print(json.dumps({k:report.get(k) for k in ['passed','error','work']}));return int(not report['passed'])


if __name__=='__main__':sys.exit(main())
