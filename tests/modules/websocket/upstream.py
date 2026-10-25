#!/usr/bin/env python3
"""Whole pinned WebSocket PHPT directory through PHP's isolated official runner."""
import argparse
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from corpus.upstream.run import COMMIT, prepare, record_result, run_cases, save_report
from tools.harness import ROOT, parse_engines


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'target/upstream/src')
    parser.add_argument('--engine', action='append', required=True)
    parser.add_argument('--php', default='php')
    parser.add_argument('--php-extension', action='append', default=[])
    parser.add_argument('--case', action='append', default=[], help='Original basename without .phpt')
    parser.add_argument('--timeout', type=int, default=60)
    parser.add_argument('--output', type=Path, default=ROOT / 'target/reports/websocket-upstream.json')
    args = parser.parse_args()
    paths = subprocess.check_output(['git', '-C', str(args.source), 'ls-tree', '-r', '--name-only', COMMIT,
                                    'tests/swoole_websocket_server'], text=True).splitlines()
    paths = sorted(path for path in paths if path.endswith('.phpt'))
    if len(paths) != 34 or set(args.case) - {Path(path).stem for path in paths}:
        parser.error('Pinned 34-case inventory differs or unknown case name')
    if args.timeout < 1:
        parser.error('--timeout must be positive')
    cases = [{'path': path, 'module': 'websocket', 'sha256': hashlib.sha256(subprocess.check_output(
        ['git', '-C', str(args.source), 'show', f'{COMMIT}:{path}'])).hexdigest()}
        for path in paths if not args.case or Path(path).stem in args.case]
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'upstream_commit': COMMIT,
              'scope': 'Original WebSocket directory; assertions/expected outputs untouched; serial official runner.',
              'inventory_count': len(paths), 'selected_cases': [case['path'] for case in cases],
              'unmeasured_cases': [path for path in paths if path not in {case['path'] for case in cases}],
              'engines': [], 'results': [], 'batches': [], 'passed': False, 'execution_status': 'running'}
    try:
        for engine in parse_engines(args.engine, args.php, args.php_extension):
            metadata = engine.metadata()
            report['engines'].append(metadata)
            with tempfile.TemporaryDirectory(prefix='swr-websocket-original-') as temporary:
                sandbox = Path(temporary)
                prepare(args.source, sandbox, cases)
                (sandbox / 'home').mkdir()
                (sandbox / 'tmp').mkdir()
                for case in cases:
                    artifact = args.output.resolve().parent / (args.output.stem + '-artifacts') / engine.name / Path(case['path']).stem
                    missing = {'websocket', 'websocket_codec', 'processes', 'coroutine_http_client', 'sync_tcp_client'} - set(metadata['capabilities'])
                    if missing:
                        record_result(report, engine, case, {'status': 'unsupported', 'detail': f'Missing capabilities: {sorted(missing)}'})
                    else:
                        # Two originals use fixed listeners. Refuse occupied ports;
                        # do not kill an unrelated listener or rewrite the tests.
                        ports = {'empty_message': [9501], 'listener': [9506]}.get(Path(case['path']).stem, [])
                        try:
                            for port in ports:
                                with socket.socket() as guard:
                                    guard.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                                    guard.bind(('127.0.0.1', port))
                        except OSError as error:
                            record_result(report, engine, case, {'status': 'failed', 'detail': f'Original fixed port unavailable: {error}'})
                            save_report(args.output, report)
                            continue
                        results, timing = run_cases(engine, [case], sandbox, artifact, args.timeout, 1)
                        report['batches'].append({'engine': engine.name, **timing})
                        record_result(report, engine, case, results[case['path']])
                    save_report(args.output, report)
        report['execution_status'] = 'complete'
        report['passed'] = bool(report['results']) and all(row['status'] == 'passed' for row in report['results'])
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
        report['execution_status'] = 'failed'
        print(report['error'], file=sys.stderr)
    finally:
        save_report(args.output, report)
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
