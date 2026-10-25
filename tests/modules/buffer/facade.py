#!/usr/bin/env python3
"""Compare seeded positive Buffer facade lifecycles against original native controls."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import platform
import subprocess
import sys
import tarfile
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, run_isolated, write_report
from tools.build_upstream import COMMIT, require_build_space


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--rust-asan', action='store_true', help='Declare separately instrumented Rust archive; require native sanitizer runtime and ASan imports')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.rust_asan and not args.sanitize: parser.error('Rust ASan requires the native sanitizer runtime')
    report = dict(passed=False, assigned_to='@loks0n', upstream_commit=COMMIT,
                  host=platform.platform(),
                  sanitizer_scope='Declared supplied archive Rust ASan plus C++ ASan/UBSan; precompiled Rust std remains outside instrumentation' if args.rust_asan else 'C++ ASan/UBSan only; Rust instructions uninstrumented' if args.sanitize else 'none',
                  rust_asan_declared=args.rust_asan,
                  engines={}, full_module_parity_passed=False, performance_qualified=False,
                  scope='Six seeded positive facade sequences with binary data and CLOSE tokens, partial-consume offsets, CLOSE-token callbacks, stable cached identity and mixed teardown. DATA destroy callbacks are excluded from this separate supported original-control profile. No original DATA-token underflow or unsafe vector/zero probes. Independent model and allocation replay remain separate.')
    def run(command, tree):
        require_build_space(ROOT)
        require_build_space(tree)
        row = run_isolated(list(map(str,command)), timeout=60, cwd=tree)
        return dict(command=list(map(str,command)), exit=row.returncode, stdout=row.stdout, stderr=row.stderr)
    try:
        if args.rust_asan:
            probe=subprocess.run(['nm','-u',str(args.archive)],capture_output=True,text=True)
            report['asan_import_probe']={'exit':probe.returncode,'stdout':probe.stdout,'stderr':probe.stderr}
            if '__asan_report_' not in probe.stdout: raise ValueError('Supplied archive lacks Rust ASan report imports')
        with tempfile.TemporaryDirectory(prefix='swr-buffer-facade-') as temporary:
            tree=Path(temporary)
            data=subprocess.check_output(['git','-C',str(args.source),'archive',COMMIT,'include','src/core/buffer.cc'])
            with tarfile.open(fileobj=io.BytesIO(data)) as archive:
                for member in archive:
                    if member.isfile():
                        p=tree/member.name; p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(archive.extractfile(member).read())
            subprocess.run(['git','init','-q',str(tree)],check=True)
            manifest=json.loads((ROOT/'migration/patches/buffer/manifest.json').read_text())
            report['compiler']=run(['c++','--version'],tree)
            for name in ['native','selected']:
                if name=='selected':
                    for item in manifest['patches'][:2]:
                        patch=ROOT/'migration/patches/buffer'/item['path']
                        if sha(patch)!=item['sha256']:raise ValueError('Overlay checksum differs')
                        subprocess.run(['git','apply','--check',str(patch)],cwd=tree,check=True,capture_output=True)
                        subprocess.run(['git','apply',str(patch)],cwd=tree,check=True,capture_output=True)
                binary=tree/name
                command=['c++','-std=c++17','-O1','-g','-DMODEL_FACADE_ONLY','-DMODEL_FACADE_CONTROL','-ffunction-sections','-fdata-sections',
                         '-I'+str(tree/'include'),'-I'+str(ROOT/'native/include'),'-I'+str(ROOT/'native/buffer'),
                         str(tree/'src/core/buffer.cc'),str(ROOT/'tests/modules/buffer/model.cc')]
                if name=='selected':command+=['-DSWOOLE_RS_BUFFER',str(args.archive.resolve())]
                command+=['-Wl,-dead_strip'if sys.platform=='darwin'else'-Wl,--gc-sections','-lm']
                if sys.platform.startswith('linux'):command+=['-ldl','-lpthread','-lrt','-lutil']
                if args.sanitize:command+=['-fsanitize=address,undefined','-fno-sanitize-recover=all']
                command+=['-o',str(binary)]
                row=report['engines'][name]={'compile':run(command,tree)}
                if row['compile']['exit']:raise ValueError(name+' compilation failed')
                row['run']=run([binary],tree)
                if row['run']['exit'] or row['run']['stderr']:raise ValueError(name+' execution failed or warned')
                row['outcome']=json.loads(row['run']['stdout'])
                if row['outcome']['facade_sequences']!=6 or row['outcome']['steps_per_sequence']!=64 or not row['outcome']['passed'] or not row['outcome']['callbacks']:raise ValueError('Facade inventory/outcomes differ')
            if report['engines']['native']['outcome'] != report['engines']['selected']['outcome']:raise ValueError('Native/selected supported outcomes differ')
            report['passed']=True
    except Exception as error:
        report['error']=f'{type(error).__name__}: {error}'
        if isinstance(error,subprocess.CalledProcessError):report['command_error']={'stdout':str(error.stdout),'stderr':str(error.stderr)}
    write_report(args.output,report)
    print(json.dumps({key:report.get(key)for key in ['passed','error','host']}))
    return int(not report['passed'])


if __name__=='__main__':
    sys.exit(main())
