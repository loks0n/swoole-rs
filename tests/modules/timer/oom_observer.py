#!/usr/bin/env python3
"""Bounded native observation of the retained original Linux/PHP8.2 OOM timeout."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import parse_engines, run_isolated, write_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', action='append', required=True)
    parser.add_argument('--php', default='php')
    parser.add_argument('--php-config', default='php-config')
    parser.add_argument('--output', default='target/reports/timer-oom-observer.json')
    args = parser.parse_args()
    if sys.platform != 'linux' or len(args.engine) != 2:
        parser.error('Exactly two actual Linux engines: clean original then corrected timer')
    local = Path(__file__).resolve().parent
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'diagnostic_completed': False,
              'scope': 'Supplemental native observer stops its own event loop after exactly8 end rounds. Not a passing replacement for the unchanged failing repeating-OOM fixture, not a benchmark or sanitizer gate.',
              'fixed_native_round_budget': 8, 'process_limit_seconds': 5,
              'engines': [], 'results': [], 'commands': []}
    try:
        includes = shlex.split(subprocess.check_output([args.php_config, '--includes'], text=True))
        extensions = []
        if subprocess.check_output([args.php, '-n', '-r', 'echo extension_loaded("FFI") ? "yes" : "no";'], text=True) != 'yes':
            extensions.append('ffi')
        with tempfile.TemporaryDirectory(prefix='swr-timer-oom-observer-') as temporary:
            for engine in parse_engines(args.engine, args.php, extensions):
                metadata = engine.metadata()
                if not metadata['php'].startswith('8.2.'):
                    raise ValueError('Actual PHP8.2 runtime required')
                report['engines'].append(metadata)
                source = engine.extension.parents[1]
                manifest = source.parent / 'build-manifest.json'
                command = shlex.split(os.environ.get('CXX', 'c++')) + ['-std=c++17', '-O1', '-g', '-shared', '-fPIC', '-Wl,-Bsymbolic', '-DHAVE_CONFIG_H',
                    '-I' + str(source), '-I' + str(source / 'include'), *includes]
                if manifest.exists():
                    data = json.loads(manifest.read_text())
                    if data['extension_sha256'] != metadata['sha256']:
                        raise ValueError('Immutable extension hash mismatch')
                    command += ['-DSWOOLE_RS_TIMER=1', '-I' + str(source.parent / 'rust-prefix/include')]
                library = Path(temporary) / (engine.name + '.so')
                command += [str(local / 'oom_observer.cc'), '-o', str(library)]
                result = run_isolated(command, timeout=45)
                report['commands'].append({'argv': command, 'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
                if result.returncode:
                    raise RuntimeError('Observer compile failed')
                for mode in ['normal', 'oom']:
                    argv = engine.command('-d', 'memory_limit=-1', local / 'oom_observer.php', library, mode)
                    row = {'engine': engine.name, 'mode': mode, 'command': argv}
                    try:
                        result = run_isolated(argv, timeout=5)
                        traces = [json.loads(line[len('NATIVE '):]) for line in result.stderr.splitlines() if line.startswith('NATIVE ')]
                        row.update(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr, traces=traces,
                                   native_budget_reached=len(traces) == 8 and traces[-1]['step'] == 8)
                    except subprocess.TimeoutExpired as error:
                        row.update(error=str(error), stdout=str(error.stdout), stderr=str(error.stderr), native_budget_reached=False)
                    report['results'].append(row)
                    write_report(args.output, report)
        report['diagnostic_completed'] = len(report['results']) == 4 and all(r['native_budget_reached'] for r in report['results'])
    except Exception as error:
        report['error'] = str(error)
    write_report(args.output, report)
    print(json.dumps({'diagnostic_completed': report['diagnostic_completed'], 'error': report.get('error'),
                      'outcomes': [{k: r.get(k) for k in ['engine', 'mode', 'returncode', 'native_budget_reached']} for r in report['results']]}))
    return int(not report['diagnostic_completed'])


if __name__ == '__main__':
    sys.exit(main())
