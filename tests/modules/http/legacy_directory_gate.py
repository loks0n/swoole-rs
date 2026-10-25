#!/usr/bin/env python3
"""Real Legacy directory callers and typed Rust-owned value controls; normal-only."""
import argparse
import io
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
from gate import PIN, body, apply_http_patch, apply_static_header, prepare_index_buffer
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, run_isolated, write_report
from tools.build_hybrid import apply_patch_verified


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', default='target/reports/http-legacy-directory.json')
    args = parser.parse_args()
    if Path(args.output).exists(): parser.error('Refusing an existing receipt')
    local = Path(__file__).resolve().parent
    report = {'pin': PIN, 'passed': False, 'full_gate_passed': False,
              'scope': 'Actual three pinned/selected Legacy method bodies, inert counted directory/String/Server facades and initialized typed directory values. No filesystem/full Handler construction or lifetime/runtime/performance proof.', 'native_sanitizers': True,
              'rust_instrumented': False, 'rust_std_instrumented': False,
              'checks': [], 'unrun': ['filesystem/errors', 'full Handler lifetime', 'fault/reentry/thread/fork/IPC', 'other platforms', 'performance/default/external SDK']}
    with tempfile.TemporaryDirectory(prefix='swr-legacy-directory-') as temporary:
        tree = Path(temporary)
        def checked(command, name, timeout=60):
            row = {'name': name, 'command': command, 'guard_bytes': 4*1024**3,
                   'free_bytes': {str(p): shutil.disk_usage(p).free for p in [ROOT,tree,args.archive.resolve().parent]}}
            report['checks'].append(row)
            if min(row['free_bytes'].values()) < row['guard_bytes']:
                row['blocked'] = 'unchanged disk guard'; return None
            result = run_isolated(command, timeout=timeout)
            row.update(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
            return result if result.returncode == 0 else None
        data = subprocess.check_output(['git','-C',str(args.source),'archive',PIN,'include','src/server/static_handler.cc'])
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for member in archive:
                if member.isfile():
                    path=tree/member.name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(archive.extractfile(member).read())
        source=tree/'src/server/static_handler.cc';original=source.read_text()
        apply_http_patch(tree,ROOT/'migration/patches/http/0002-static-ranges.patch',report)
        apply_static_header(tree,report);prepare_index_buffer(tree,report)
        selected=source.read_text()
        manifest=ROOT/'migration/patches/integration/manifest.json'
        for entry in json.loads(manifest.read_text())['patches']:
            if entry['upstream_paths']==['include/swoole_server.h']:
                report.setdefault('shared_patch_application',[]).append(apply_patch_verified(tree,manifest.parent/entry['path'],entry['upstream_paths'],entry['sha256']))
        flags=['-std=c++17','-DSWOOLE_RS_HTTP=1','-DSWOOLE_RS_HTTP_LEGACY_DIRECTORY_STORE=1',
               '-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all',
               '-I'+str(tree/'include'),'-I'+str(ROOT/'native/http'),'-I'+str(local),'-I'+str(tree)]
        flags+=shlex.split(subprocess.check_output(['pkg-config','--cflags','openssl'],text=True))
        # Existing assertions are reused verbatim; only the selected real facade
        # type differs from the older V2 fixture. Native controls remain std::set.
        oracle=(local/'directory_oracle.h').read_text()
        oracle=oracle.replace('#define DIRECTORY_ORACLE(ns)', '#define DIRECTORY_ORACLE(ns, STORE)')
        oracle=oracle.replace('std::set<std::string> dir_files;', 'STORE dir_files;')
        oracle=oracle.replace('DIRECTORY_ORACLE(upstream_directory)', 'DIRECTORY_ORACLE(upstream_directory, std::set<std::string>)')
        oracle=oracle.replace('DIRECTORY_ORACLE(candidate_directory)', 'DIRECTORY_ORACLE(candidate_directory, swoole::http_server::LegacyDirectory)')
        oracle='#include "swoole_rs_http_legacy_directory.h"\n#include "swoole_rs_http_static_config.h"\n'+oracle
        config='swoole::http_server::StaticConfig configuration;const auto &static_files()const{return configuration;} auto &static_files(){return configuration;}'
        oracle=oracle.replace('bool http_autoindex=false;};', 'bool http_autoindex=false;'+config+'};')
        (tree/'directory_oracle.h').write_text(oracle)
        (tree/'directory_candidate.h').write_text('#pragma once\n')
        # Force this private transformed model, never the unchanged local oracle.
        fixture=(local/'directory_gate.cc').read_text().replace('candidate_directory::StaticHandlerV2','candidate_directory::StaticHandler')
        fixture=fixture.replace('size_t cases=0;', 'const size_t value_checks=check_directory_values(); size_t cases=0;')
        # Add one ordinary empty successful scan; keep all original 324 tuples.
        fixture=fixture.replace('{".",".."},', '{}, {".",".."},',1)
        key='  upstream_directory::StaticHandler old('
        fixture=fixture.replace(key, '#if defined(SWOOLE_RS_HTTP_STATIC_CONFIG) && SWOOLE_RS_HTTP_STATIC_CONFIG\n  if(b.http_index_files)for(const auto &name:*b.http_index_files)b.configuration.add_index(name);\n#endif\n'+key)
        fixture=fixture.replace('<<",\\\"errors\\\":0', '<<",\\\"value_checks\\\":"<<value_checks<<",\\\"errors\\\":0')
        (tree/'fixture.cc').write_text('#include "legacy_directory_values.cc"\n'+fixture)
        base=subprocess.check_output(['git','-C',str(args.source),'show',PIN+':src/core/base.cc'],text=True)
        signatures=['bool StaticHandler::get_dir_files(', 'bool StaticHandler::try_serve_index_file(', 'size_t StaticHandler::make_index_page(']
        for namespace,text in [('upstream_directory',original),('candidate_directory',selected)]:
            parts=[body(base,'std::string intersection(')]
            if namespace=='candidate_directory':
                parts += [body(selected,'static void append_index_part('),body(selected,'static void append_legacy_directory_part(')]
            # This method has two alternative #if switch openings and one
            # common closing brace. A raw brace counter would include later V2
            # functions; use its exact next top-level declaration boundary.
            index_start=text.index('bool StaticHandler::try_serve_index_file(')
            next_signature='static void append_index_part(' if namespace=='candidate_directory' else 'size_t StaticHandler::make_index_page('
            index_method=text[index_start:text.index(next_signature,index_start)].rstrip()
            parts += [body(text,signatures[0]),index_method,body(text,signatures[2])]
            (tree/(namespace+'.cc')).write_text('#include "directory_oracle.h"\nnamespace '+namespace+' {\nusing swoole::http_server::LegacyDirectory;\n'+'\n'.join(parts)+'\n}\n')
        dependency=tree/'dependencies.cc';dependency.write_text('#include "directory_oracle.h"\n'+body(base,'size_t sw_snprintf('))
        report['profiles']=[]
        for config_on in [False,True]:
            mode=['-DSWOOLE_RS_HTTP_STATIC_CONFIG=1'] if config_on else []
            name='static-config-'+('on' if config_on else 'off')
            if checked(['c++',*['-std=c++14' if f=='-std=c++17' else f for f in flags],*mode,'-fsyntax-only',str(source)],name+'-whole-tu') is None:
                write_report(args.output,report);return 1
            binary=tree/name
            command=['c++',*flags,*mode,str(tree/'upstream_directory.cc'),str(tree/'candidate_directory.cc'),str(dependency),str(tree/'fixture.cc'),str(args.archive.resolve()),'-lm','-o',str(binary)]
            if sys.platform.startswith('linux'): command+=['-ldl','-lpthread','-lrt','-lutil']
            if checked(command,name+'-compile') is None:write_report(args.output,report);return 1
            symbols=subprocess.check_output(['nm','-g',str(binary)],text=True)
            names=['swr_v2_http_directory_clone','swr_v2_http_directory_emit']
            if config_on:names+=['swr_v2_http_config_directory_index']
            if not all(name in symbols for name in names):
                report['failed']='Actual linked archive symbols absent';write_report(args.output,report);return 1
            value=checked([str(binary)],name+'-positive',30)
            if value is None:write_report(args.output,report);return 1
            report['profiles'].append({'name':name,'outcome':json.loads(value.stdout.splitlines()[-1])})
        report['passed']=True;write_report(args.output,report)
    return 0

if __name__=='__main__':sys.exit(main())
