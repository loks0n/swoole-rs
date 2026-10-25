#!/usr/bin/env python3
"""Actual RequestV2 facade with a borrowed-buffer model and real Rust metadata owner."""
import argparse
import io
import json
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import tarfile
import tempfile
from gate import PIN, body, apply_http_patch, add_archive_arguments, prepare_archive
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, run_isolated, write_report

METHODS=['RequestV2::RequestV2()', 'RequestV2::~RequestV2()', 'void RequestV2::control(',
         'swr_v2_http_request_observation RequestV2::observe()', 'int RequestV2::frame(',
         'int RequestV2::get_protocol()', 'int RequestV2::get_header_length()',
         'void RequestV2::parse_header_info()', 'std::string RequestV2::get_header(',
         'bool RequestV2::has_expect_header()']
PRELUDE=r'''
#include "swoole_rs_http.h"
#include "swoole_http.h"
#include "swoole_http2.h"
#include <cerrno>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#include <utility>
'''
MODEL=r'''
namespace model {
// Explicit external buffer double: no production String/allocation/IO claim.
struct String {
    std::string storage;
    char *str;
    size_t length,offset=0;
    explicit String(std::string text):storage(std::move(text)),str(&storage[0]),length(storage.size()) {}
};
struct multipart_parser;
struct Server;
// Never executed by these normal metadata controls. Any resource call is a failure.
inline int http_no_digits_errno() { throw std::logic_error("Excluded numeric-error effect"); }
'''

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    add_archive_arguments(parser)
    args=parser.parse_args()
    if args.output.exists(): parser.error('Refusing an existing receipt')
    local=Path(__file__).resolve().parent
    report={'pin':PIN,'scope':__doc__+'; actual pinned header and six original method bodies on the same ordinary metadata inputs','passed':False,'full_gate_passed':False,
            'minimum_free_bytes':4*1024**3,'native_sanitizers':True,'rust_instrumented':args.rust_sanitize,
            'rust_std_instrumented':False,'unrun_profiles':['Actual Native String/parser/IO/allocation/failure/lifetime/receive/producer behavior','Original inventories/platform/performance/default activation']}
    with tempfile.TemporaryDirectory(prefix='swr-request-v2-model-') as temp:
        tree=Path(temp)
        def guard():
            free=shutil.disk_usage(tree).free
            if free<report['minimum_free_bytes']:
                report['blocked']={'free_bytes':free};write_report(args.output,report);return False
            return True
        if not guard(): return 1
        if not prepare_archive(args,tree,report): write_report(args.output,report);return 1
        data=subprocess.check_output(['git','-C',str(args.source),'archive',PIN,'include','src/protocol/http.cc'])
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for member in archive:
                if member.isfile():
                    path=tree/member.name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(archive.extractfile(member).read())
        source=tree/'src/protocol/http.cc'
        original=source.read_text()
        original_header=(tree/'include/swoole_http.h').read_text()
        apply_http_patch(tree,ROOT/'migration/patches/http/0001-http-helpers.patch',report)
        header=ROOT/'native/http/swoole_rs_http_request_v2.h'
        text=header.read_text()
        # Extract exact C declarations, class and actual method bodies; only namespace/resource doubles differ.
        declarations=text[text.index('typedef struct swr_v2_http_request'):text.index('#ifdef __cplusplus\n}\n#include')]
        generated=tree/'model.cc'
        generated.write_text(PRELUDE+'\nextern "C" {\n'+declarations+'\n}\n'+MODEL+body(text,'class RequestV2 {')+';\n'+
            '\n'.join(body(source.read_text(),signature) for signature in METHODS)+
            '\nvoid RequestV2::destroy_multipart_parser() { throw std::logic_error("Excluded active resource teardown"); }\n}\n'+
            'namespace upstream_model { using String=model::String; struct Server;\n'+
            body(original_header,'struct FormData {')+';\n'+body(original_header,'struct Request {')+';\n'+
            original[original.index('static const char *method_strings[]'):original.index('};',original.index('static const char *method_strings[]'))+2]+'\n'+
            '\n'.join(body(original,signature) for signature in ['int Request::get_protocol(', 'int Request::get_header_length(', 'void Request::parse_header_info(', 'std::string Request::get_header(', 'bool Request::has_expect_header(', 'Request::~Request()'])+
            '\nvoid Request::destroy_multipart_parser() { throw std::logic_error("Excluded original active resource teardown"); }\n}\n'+(local/'request_v2_model.cc').read_text())
        if not guard(): return 1
        binary=tree/'model'
        command=['c++','-std=c++14','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(ROOT/'native/http'),'-I'+str(tree/'include'),*shlex.split(subprocess.check_output(['pkg-config','--cflags','openssl'],text=True)),str(generated),str(args.archive.resolve()),'-lm','-o',str(binary)]
        if sys.platform.startswith('linux'):command+=['-ldl','-lpthread','-lrt','-lutil']
        compiled=run_isolated(command,timeout=60)
        report['compile']={'command':command,'returncode':compiled.returncode,'stdout':compiled.stdout,'stderr':compiled.stderr}
        write_report(args.output,report)
        if compiled.returncode:print(compiled.stderr,file=sys.stderr);return 1
        result=run_isolated([str(binary)],timeout=30)
        report['run']={'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
        if result.returncode:
            write_report(args.output,report);print(result.stderr,file=sys.stderr);return 1
        report['outcome']=json.loads(result.stdout)
        # Exercise new owner/snapshot operations through this same exact archive,
        # without a second private driver or any parser/Native String effects.
        if not guard():return 1
        metadata=tree/'upload-metadata'
        command=['cc','-std=c11','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(ROOT/'native/http'),str(local/'request_upload_gate.c'),str(args.archive.resolve()),'-lm','-o',str(metadata)]
        if sys.platform.startswith('linux'):command+=['-ldl','-lpthread','-lrt','-lutil']
        compiled=run_isolated(command,timeout=60)
        check={'scope':'Selected Rust owner operations only; no original engine counterpart/parser/Native String effect proof',
               'compile':{'command':command,'returncode':compiled.returncode,'stdout':compiled.stdout,'stderr':compiled.stderr}}
        report['upload_metadata_cabi']=check
        write_report(args.output,report)
        if compiled.returncode:print(compiled.stderr,file=sys.stderr);return 1
        result=run_isolated([str(metadata)],timeout=30)
        check['run']={'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
        report['passed']=result.returncode==0
        if report['passed']:check['outcome']=json.loads(result.stdout)
        write_report(args.output,report)
        print(json.dumps({'passed':report['passed'],'outcome':report.get('outcome')}))
        return 0 if report['passed'] else 1
if __name__=='__main__':sys.exit(main())
