#!/usr/bin/env python3
"""Actual original/selected cookie bodies: ordinary callbacks, no fault/reentry/alias profiles."""
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
from gate import PIN, body, apply_http_patch, add_archive_arguments, prepare_archive
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, run_isolated, write_report

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    profile=parser.add_mutually_exclusive_group()
    profile.add_argument('--status-only',action='store_true',help='Only original status/TLS controls; no cookie, routing or proxy profiles')
    profile.add_argument('--codes-only',action='store_true',help='Original public mutable status-array ABI plus status/TLS controls; shared-export probe is inspected, never loaded')
    add_archive_arguments(parser)
    args=parser.parse_args()
    args.status_only=args.status_only or args.codes_only
    if args.output.exists():parser.error('Refusing an existing receipt')
    local=Path(__file__).resolve().parent
    control=local/('status_buffer_gate.cc' if args.status_only else 'cookie_flow_gate.cc')
    report={'pin':PIN,'scope':'Actual public int[128] C++ ABI, mutable slots, normal status/TLS and export-only mini DSO inspection' if args.codes_only else 'Actual original/selected status strings, errno and normal concurrent TLS backing' if args.status_only else __doc__,'passed':False,'full_gate_passed':False,'native_sanitizers':True,
            'rust_instrumented':args.rust_sanitize,'precompiled_std_instrumented':False,'minimum_free_bytes':4*1024**3,
            'unrun_profiles':['Original complete headers corpus','Fault/exception/reentry/mutation/alias/extreme inputs','PHP/server/platform/allocation/lifetime/performance/default activation']}
    with tempfile.TemporaryDirectory(prefix='swr-cookie-flow-') as temp:
        tree=Path(temp)
        def guard():
            free=shutil.disk_usage(tree).free
            if free<report['minimum_free_bytes']:
                report['blocked']={'free_bytes':free};write_report(args.output,report);return False
            return True
        if not guard():return 1
        if not prepare_archive(args,tree,report):write_report(args.output,report);return 1
        data=subprocess.check_output(['git','-C',str(args.source),'archive',PIN,'include','thirdparty/multipart_parser.h','src/protocol/http.cc'])
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for member in archive:
                if member.isfile():
                    path=tree/member.name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(archive.extractfile(member).read())
        source=tree/'src/protocol/http.cc';original=source.read_text()
        apply_http_patch(tree,ROOT/'migration/patches/http/0001-http-helpers.patch',report)
        flags=['-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(tree/'include'),'-I'+str(tree),'-I'+str(ROOT/'native/http'),'-I'+str(local)]
        if args.codes_only:flags.append('-DSWR_HTTP_STATUS_CODES')
        flags+=shlex.split(subprocess.check_output(['pkg-config','--cflags','openssl'],text=True))
        if not guard():return 1
        command=['c++','-std=c++14',*flags,'-c',str(source),'-o',str(tree/'protocol.o')]
        compiled=run_isolated(command,timeout=60)
        report['actual_native_tu']={'command':command,'returncode':compiled.returncode,'stdout':compiled.stdout,'stderr':compiled.stderr}
        write_report(args.output,report)
        if compiled.returncode:print(compiled.stderr,file=sys.stderr);return 1
        dependencies=[]
        if args.status_only:
            base=subprocess.check_output(['git','-C',str(args.source),'show',PIN+':src/core/base.cc'],text=True)
            path=tree/'dependencies.cc';path.write_text('#include "headers_oracle.h"\n'+body(base,'size_t sw_snprintf('));dependencies.append(str(path))
        for namespace,text in [('upstream_headers',original),('candidate_headers',source.read_text())]:
            parts=body(text,'const char *get_status_message(' if args.status_only else 'void parse_cookie(')
            if args.codes_only and namespace=='upstream_headers':
                import re
                parts=re.search(r'int list_of_status_code\[128\] = \{.*?\};',original,re.S).group(0)+'\n'+parts
            if args.status_only and 'static thread_local char http_status_message[128];' in text:
                parts='static thread_local char http_status_message[128];\n'+parts
            path=tree/(namespace+'.cc');path.write_text('#include "headers_oracle.h"\nnamespace '+namespace+' {\n'+parts+'\n}\n')
        if not guard():return 1
        binary=tree/'gate';command=['c++','-std=c++17',*flags,str(tree/'upstream_headers.cc'),str(tree/'candidate_headers.cc'),str(control),*dependencies,str(args.archive.resolve()),'-lm','-o',str(binary)]
        if sys.platform.startswith('linux'):command+=['-ldl','-lpthread','-lrt','-lutil']
        compiled=run_isolated(command,timeout=60)
        report['compile']={'command':command,'returncode':compiled.returncode,'stdout':compiled.stdout,'stderr':compiled.stderr}
        write_report(args.output,report)
        if compiled.returncode:print(compiled.stderr,file=sys.stderr);return 1
        if args.codes_only:
            # No data reference or artificial force-load: only the actual status
            # forwarding body pulls its Rust member. Inspect, never load the DSO.
            selected=tree/'selected-export.cc'
            selected.write_text('#include "headers_oracle.h"\nnamespace swoole { namespace http_server {\n'+body(source.read_text(),'const char *get_status_message(')+'\n}}\n')
            shared=tree/'status-export.so'
            command=['c++','-std=c++14','-fPIC',*flags,str(selected),str(args.archive.resolve()),'-lm','-o',str(shared)]
            command.insert(1,'-dynamiclib' if sys.platform=='darwin' else '-shared')
            if sys.platform.startswith('linux'):command+=['-ldl','-lpthread','-lrt','-lutil']
            if not guard():return 1
            linked=run_isolated(command,timeout=60)
            report['shared_export_compile']={'command':command,'returncode':linked.returncode,'stdout':linked.stdout,'stderr':linked.stderr}
            write_report(args.output,report)
            if linked.returncode:return 1
            command=['nm','-m','-gU',str(shared)] if sys.platform=='darwin' else ['nm','-D','--defined-only',str(shared)]
            report['shared_export_symbol_command']=command
            report['shared_export_symbols']=subprocess.check_output(command,text=True)
            symbol=('_' if sys.platform=='darwin' else '')+'_ZN6swoole11http_server19list_of_status_codeE'
            found=[line for line in report['shared_export_symbols'].splitlines() if symbol in line.split() and 'private external' not in line and 'undefined' not in line and 'non-external' not in line]
            report['public_array_exported_without_artificial_reference']=len(found)==1
            if len(found)!=1:write_report(args.output,report);return 1
        report['actual_rust_symbol_present']=('swr_v2_http_status_message' if args.status_only else 'swr_v2_http_cookie_flow') in subprocess.check_output(['nm','-g',str(binary)],text=True)
        if not report['actual_rust_symbol_present']:write_report(args.output,report);return 1
        result=run_isolated([str(binary)],timeout=30)
        report['run']={'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
        report['passed']=result.returncode==0
        if report['passed']:report['outcome']=json.loads(result.stdout)
        write_report(args.output,report);print(json.dumps({'passed':report['passed'],'outcome':report.get('outcome')}))
        return 0 if report['passed'] else 1
if __name__=='__main__':sys.exit(main())
