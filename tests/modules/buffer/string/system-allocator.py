#!/usr/bin/env python3
"""Private executable-only libc interposition for actual native/Rust String consumers; no timing."""
import argparse
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from tools.harness import ROOT, run_isolated, write_report
from tools.build_upstream import COMMIT as PIN

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--directory', type=Path, required=True, help='New private output directory, retained with exact source/binaries')
    args = p.parse_args()
    directory = args.directory.resolve(); directory.mkdir(parents=True, exist_ok=False)
    local = Path(__file__).resolve().parent
    report = {'pin': PIN, 'scope': __doc__, 'passed': False,
              'commands': [], 'results': []}
    output = directory / 'report.json'
    def compile(command):
        r = run_isolated(command, timeout=90)
        report['commands'].append({'command': command, 'returncode': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr})
        write_report(output, report)
        if r.returncode: raise RuntimeError('Compile failed; first output retained')
    try:
        tree = directory / 'source'; tree.mkdir()
        subprocess.run(['git', 'init', '--quiet', str(tree)], check=True)
        data = subprocess.check_output(['git', '-C', str(args.source), 'archive', PIN, 'include', 'src/core/string.cc', 'src/core/base.cc', 'src/os/base.cc', 'src/core/base64.cc'])
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for m in archive:
                if m.isfile():
                    path = tree / m.name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(archive.extractfile(m).read())
        library = directory / ('interpose.dylib' if sys.platform == 'darwin' else 'interpose.so')
        compile(['c++', '-std=c++17', '-O1', '-g', '-fPIC', '-fno-builtin',
                 '-dynamiclib' if sys.platform == 'darwin' else '-shared', str(local / 'system-allocator-interpose.cc'), '-o', str(library)])
        # Only the isolated test child receives this environment; never preload a shell or user application.
        env = dict(os.environ)
        env['DYLD_INSERT_LIBRARIES' if sys.platform == 'darwin' else 'LD_PRELOAD'] = str(library)
        for engine in ['upstream', 'rust']:
            if engine == 'rust':
                patch = ROOT / 'migration/patches/buffer/0003-string-storage.patch'
                subprocess.run(['git', 'apply', '--check', str(patch)], cwd=tree, check=True)
                subprocess.run(['git', 'apply', str(patch)], cwd=tree, check=True)
            binary = directory / engine
            command = ['c++', '-std=c++17', '-O1', '-g', '-fno-builtin', '-ffunction-sections', '-fdata-sections',
                       '-I'+str(local), '-I'+str(tree / 'include'), '-I'+str(ROOT / 'native/buffer'),
                       *[str(tree / name) for name in ['src/core/string.cc', 'src/core/base.cc', 'src/os/base.cc', 'src/core/base64.cc']],
                       str(local / 'system-allocator.cc'), str(library)]
            command += shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'openssl'], text=True))
            if engine == 'rust': command += [str(args.archive.resolve())]
            command += ['-Wl,-dead_strip' if sys.platform == 'darwin' else '-Wl,--gc-sections', '-lm']
            if sys.platform.startswith('linux'): command += ['-ldl', '-lpthread', '-lrt', '-lutil']
            compile(command + ['-o', str(binary)])
            if engine == 'rust':
                symbols = subprocess.check_output(['nm', '-g', str(binary)], text=True)
                if 'swr_v1_string_apply' not in symbols: raise RuntimeError('Candidate missing actual Rust String symbols')
            scenarios = [('cold', -1), *[('cold', i) for i in range(16)], ('malloc-failure', -1), ('calloc', -1), ('calloc-failure', -1), ('realloc-null', -1),
                         ('alias-defined', -1), ('zero-owned-grow', -1), ('zero-shrink', -1)]
            if engine == 'rust': scenarios += [('alias-rebase', -1), ('alias-rebase-failure', -1)]
            for scenario, index in scenarios:
                row = {'engine': engine, 'scenario': scenario, 'failure_index': index, 'passed': False}
                try:
                    r = run_isolated([str(binary), scenario, str(index)], timeout=5, env=env)
                    row.update(returncode=r.returncode, stdout=r.stdout, stderr=r.stderr)
                    observation = json.loads(r.stdout.splitlines()[-1]); row['observation'] = observation
                    valid = r.returncode == 0 and not observation['error'] and observation['live_after_cleanup'] == 0
                    events = observation['events']
                    if scenario == 'cold' and index == -1:
                        valid &= [(e['operation'], e['size'], e['moved']) for e in events] == [('m',64,False)] + [('r',256*i,True) for i in range(1,17)] + [('f',0,False)]
                    if scenario == 'cold' and index >= 0:
                        valid &= observation['operation_failed'] and sum(e['failed'] and e['operation']=='r' for e in events) == 1
                    if scenario == 'malloc-failure': valid &= observation['operation_failed'] and events[0]['operation']=='m' and events[0]['failed']
                    if scenario == 'calloc': valid &= events[0]['operation']=='c' and events[0]['size']==32
                    if scenario == 'calloc-failure': valid &= observation['operation_failed'] and events[0]['operation']=='c' and events[0]['failed']
                    if scenario == 'alias-rebase-failure': valid &= observation['operation_failed'] and any(e['operation']=='r' and e['failed'] for e in events)
                    # Known native zero-owner leak / host-dependent dangling shrink remain actual failed gates.
                    valid &= not observation['abandoned_zero_owners'] and not observation['dangling_owner']
                    row['passed'] = bool(valid)
                except Exception as e: row['error'] = f'{type(e).__name__}: {e}'
                report['results'].append(row); write_report(output, report)
            report.setdefault('binaries', {})[engine] = {'path': str(binary)}
        report['not_run'] = {'upstream_alias_rebase': 'Upstream realloc invalidates its still-used input pointer; no defined native oracle. Rust extension checked independently.'}
        report['passed'] = all(row['passed'] for row in report['results'])
    except Exception as e: report['error'] = f'{type(e).__name__}: {e}'
    write_report(output, report)
    print(json.dumps({'report': str(output), 'passed': report['passed'], 'failures': [{k:r.get(k) for k in ['engine','scenario','failure_index','error']} for r in report['results'] if not r['passed']], 'error': report.get('error')}))
    return int(not report['passed'])
if __name__ == '__main__': sys.exit(main())
