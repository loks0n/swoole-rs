#!/usr/bin/env python3
"""Compare defined callback-exception termination with pinned native destructors."""
import argparse
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, run_isolated, write_report
from staging import apply_module_patch
from baseline import PIN

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', default='target/reports/buffer-callback-exceptions.json')
    args = parser.parse_args()
    local = Path(__file__).resolve().parent
    patches = [ROOT / 'migration/patches/buffer' / name for name in ['0001-buffer-header.patch', '0002-buffer-body.patch']]
    report = {'pin': PIN, 'engines': {}}
    with tempfile.TemporaryDirectory(prefix='swr-buffer-callbacks-') as directory:
        tree = Path(directory)
        data = subprocess.check_output(['git', '-C', str(args.source), 'archive', PIN, 'include', 'src/core/buffer.cc'])
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for member in archive:
                if member.isfile():
                    path = tree / member.name; path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(archive.extractfile(member).read())
        for engine in ['upstream', 'rust']:
            if engine == 'rust':
                report['patch_application'] = [apply_module_patch(tree, patch) for patch in patches]
            binary = tree / engine
            command = ['c++', '-std=c++17', '-O1', '-g', '-I' + str(tree / 'include'), '-I' + str(ROOT / 'native/include'), '-I' + str(ROOT / 'native/buffer'),
                       str(tree / 'src/core/buffer.cc'), str(local / 'callback-exception.cc')]
            if engine == 'rust': command += ['-DSWOOLE_RS_BUFFER', str(args.archive.resolve()), '-lm']
            if sys.platform.startswith('linux'): command += ['-ldl', '-lpthread', '-lrt', '-lutil']
            command += ['-o', str(binary)]
            row = report['engines'][engine] = {'compile_command': command}
            compiled = run_isolated(command, timeout=45)
            row['compile'] = {'returncode': compiled.returncode, 'stderr': compiled.stderr}
            if compiled.returncode:
                write_report(args.output, report); print(compiled.stderr, file=sys.stderr); return 1
            row['cases'] = {}
            for case in ['data', 'native', 'teardown']:
                run = run_isolated([str(binary), case], timeout=5)
                row['cases'][case] = {'expected': 77, 'actual': run.returncode, 'stdout': run.stdout, 'stderr': run.stderr}
    report['passed'] = all(case['actual'] == case['expected'] for row in report['engines'].values() for case in row['cases'].values())
    write_report(args.output, report)
    print(json.dumps({'passed': report['passed'], 'cases': {name: row['cases'] for name, row in report['engines'].items()}}))
    return int(not report['passed'])

if __name__ == '__main__': sys.exit(main())
