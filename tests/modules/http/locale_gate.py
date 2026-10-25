#!/usr/bin/env python3
"""Pinned native HTTP locale comparisons against actual Rust, without global host changes."""
import argparse
import io
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import tempfile
from gate import PIN, body
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, run_isolated, write_report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();local=Path(__file__).resolve().parent
    report={'pin':PIN,'scope':'Actual pinned get_method/boundary bodies and location/disposition libc helpers; unavailable locales unsupported, not passed. No PHP/full activation or performance claim.',
            'rust_instrumented':False,'native_sanitizers':False,'sanitizer_note':'Unsanitized native libc required: Mac ASan interceptor folds ASCII instead of selected locale','passed':False}
    with tempfile.TemporaryDirectory(prefix='swr-http-locale-') as temporary:
        tree=Path(temporary)
        data=subprocess.check_output(['git','-C',str(args.source),'archive',PIN,'include','src/protocol/http.cc'])
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for member in archive:
                if member.isfile():
                    path=tree/member.name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(archive.extractfile(member).read())
        source=tree/'src/protocol/http.cc';text=source.read_text()
        start=text.index('static const char *method_strings[]');end=text.index('};',start)+2
        extracted=tree/'native.cc'
        extracted.write_text('#include "swoole_http.h"\nnamespace upstream_locale {\n'+text[start:end]+'\n'+body(text,'int get_method(')+'\n'+body(text,'bool parse_multipart_boundary(')+'\n}\n')
        binary=tree/'gate'
        flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','openssl'],text=True))
        command=['c++','-std=c++17','-O1','-g','-I'+str(tree/'include'),'-I'+str(ROOT/'native/http'),*flags,str(extracted),str(local/'locale_gate.cc'),str(args.archive.resolve()),'-lm','-o',str(binary)]
        if sys.platform.startswith('linux'):command+=['-ldl','-lpthread','-lrt','-lutil']
        compiled=run_isolated(command,timeout=60);report['compile']={'command':command,'returncode':compiled.returncode,'stderr':compiled.stderr}
        if compiled.returncode:write_report(args.output,report);print(compiled.stderr);return 1
        result=run_isolated([str(binary)],timeout=60);report['run']={'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
        if result.stdout:report['outcome']=json.loads(result.stdout.splitlines()[-1])
        report['passed']=result.returncode==0;write_report(args.output,report);print(result.stdout,result.stderr)
        return 0 if report['passed'] else 1


if __name__=='__main__':sys.exit(main())
