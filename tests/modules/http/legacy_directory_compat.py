#!/usr/bin/env python3
"""Inert whole-SDK/layout/copy/reference controls for the private Legacy owner."""
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
from gate import PIN, apply_http_patch
from directory_compat import legacy_fields
from rewrite_store_compat import record_layout
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, run_isolated, write_report
from tools.build_hybrid import apply_patch_verified


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',default='target/reports/http-legacy-directory-compat.json')
    args=parser.parse_args()
    if Path(args.output).exists():parser.error('Refusing an existing receipt')
    report={'pin':PIN,'passed':False,'full_gate_passed':False,'checks':[],
            'scope':'Inert unconfigured pinned/selected SDK direct member layout, value-copy/reference traits and complete static TU syntax. No actual full Handler construction/lifetime, external compiled SDK or runtime qualification.',
            'selected_sdk_required':True,'old_compiled_sdk_compatible':False}
    with tempfile.TemporaryDirectory(prefix='swr-legacy-directory-sdk-') as temporary:
        tree=Path(temporary);original=tree/'original';selected=tree/'selected'
        def checked(command,name):
            row={'name':name,'command':command,'guard_bytes':4*1024**3,'free_bytes':min(shutil.disk_usage(p).free for p in [ROOT,tree])}
            report['checks'].append(row)
            if row['free_bytes']<row['guard_bytes']:row['blocked']='unchanged disk guard';return None
            value=run_isolated(command,timeout=60);row.update(returncode=value.returncode,stdout=value.stdout,stderr=value.stderr)
            return value if value.returncode==0 else None
        data=subprocess.check_output(['git','-C',str(args.source),'archive',PIN,'include','src/server/static_handler.cc'])
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for member in archive:
                if member.isfile():
                    path=original/member.name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(archive.extractfile(member).read())
        shutil.copytree(original,selected)
        for patch in ['0002-static-ranges.patch','0003-static-inline.patch']:
            apply_http_patch(selected,ROOT/'migration/patches/http'/patch,report)
        report['default_data_declarations_equal']=legacy_fields((original/'include/swoole_static_handler.h').read_text())==legacy_fields((selected/'include/swoole_static_handler.h').read_text())
        if not report['default_data_declarations_equal']:write_report(args.output,report);return 1
        manifest=ROOT/'migration/patches/integration/manifest.json'
        for entry in json.loads(manifest.read_text())['patches']:
            if entry['upstream_paths']==['include/swoole_server.h']:
                report.setdefault('shared_patch_application',[]).append(apply_patch_verified(selected,manifest.parent/entry['path'],entry['upstream_paths'],entry['sha256']))
        code='''#include "swoole_static_handler.h"
#include <type_traits>
#include <utility>
using T=swoole::http_server::StaticHandler;
static_assert(std::is_copy_constructible<T>::value && std::is_copy_assignable<T>::value,"public value copy");
static_assert(std::is_move_constructible<T>::value && std::is_move_assignable<T>::value,"public value move");
static_assert(std::is_same<decltype(std::declval<T&>().get_tasks()),const std::vector<T::task_t>&>::value,"original task reference");
static_assert(std::is_same<decltype(std::declval<T&>().get_content_type()),const std::string&>::value,"original content reference");
static_assert(std::is_same<decltype(std::declval<const T&>().get_mimetype()),const std::string&>::value,"original MIME reference");
#if defined(SWOOLE_RS_HTTP_LEGACY_DIRECTORY_STORE) && SWOOLE_RS_HTTP_LEGACY_DIRECTORY_STORE
static_assert(std::is_same<decltype(std::declval<T&>().dir_files),swoole::http_server::LegacyDirectory>::value,"sole typed directory field");
#else
static_assert(std::is_same<decltype(std::declval<T&>().dir_files),std::set<std::string>>::value,"original directory field");
#endif
static_assert(sizeof(T)>0,"complete layout only, no Handler instance");
'''
        path=tree/'layout.cc';path.write_text(code)
        flags=['-DSWOOLE_RS_HTTP=1','-fsyntax-only','-fno-access-control','-I'+str(ROOT/'native/http')]
        flags+=shlex.split(subprocess.check_output(['pkg-config','--cflags','openssl'],text=True))
        cap='-DSWOOLE_RS_HTTP_LEGACY_DIRECTORY_STORE='
        modes=[('original',original,[]),('omitted',selected,[]),('off',selected,[cap+'0']),('on',selected,[cap+'1']),
               ('on-config',selected,[cap+'1','-DSWOOLE_RS_HTTP_STATIC_CONFIG=1']),
               ('on-rewrite',selected,[cap+'1','-DSWOOLE_RS_HTTP_REWRITE_STORE=1']),
               ('on-both',selected,[cap+'1','-DSWOOLE_RS_HTTP_STATIC_CONFIG=1','-DSWOOLE_RS_HTTP_REWRITE_STORE=1'])]
        for standard in ['c++14','c++17']:
            baseline=None
            for name,world,macros in modes:
                value=checked(['c++','-std='+standard,*flags,*macros,'-I'+str(world/'include'),'-Xclang','-fdump-record-layouts',str(path)],standard+'-'+name+'-layout')
                if value is None:write_report(args.output,report);return 1
                layout=record_layout(value.stdout+'\n'+value.stderr,'swoole::http_server::StaticHandler',{'dir_files':'PRIVATE_DIRECTORY_FIELD'})
                report['checks'][-1]['layout']=layout
                if baseline is None:baseline=layout
                elif layout!=baseline:report['failed']='Handler geometry/member offset changed: '+name;write_report(args.output,report);return 1
                if world==selected and checked(['c++','-std='+standard,*flags,*macros,'-I'+str(world/'include'),str(world/'src/server/static_handler.cc')],standard+'-'+name+'-whole-tu') is None:
                    write_report(args.output,report);return 1
        report['passed']=True;write_report(args.output,report)
    return 0

if __name__=='__main__':sys.exit(main())
