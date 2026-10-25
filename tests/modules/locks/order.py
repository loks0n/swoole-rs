#!/usr/bin/env python3
"""Bounded independent admission/lock/response traces; never an original PHPT pass."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from corpus.upstream.run import prepare
from tools.harness import parse_engines, run_isolated, write_report


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--engine', action='append', required=True)
    parser.add_argument('--php', default='php')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    witness = Path(__file__).with_suffix('.php')
    report = {'scope': __doc__, 'created_utc': datetime.now(timezone.utc).isoformat(),
              'original_assertions_unchanged': True, 'original_gate_passed': False,
              'planned_cases': ['parallel', 'two-first'], 'results': [], 'passed': False}
    try:
        for engine in parse_engines(args.engine, args.php):
            expected = sha(engine.extension)
            metadata = engine.metadata()
            for mode in report['planned_cases']:
                with tempfile.TemporaryDirectory(prefix='swr-lock-order-') as temporary:
                    sandbox = Path(temporary)
                    prepare(args.source, sandbox, [])
                    (sandbox / 'home').mkdir(); (sandbox / 'tmp').mkdir()
                    script = sandbox / 'diagnostic.php'; script.write_bytes(witness.read_bytes())
                    command = engine.command(script)
                    result = run_isolated(command, cwd=sandbox, timeout=30,
                        env={**os.environ, 'LOCK_ORDER_MODE': mode, 'HOME': str(sandbox / 'home'),
                             'TMPDIR': str(sandbox / 'tmp'), 'SKIP_ONLINE_TESTS': '1'})
                    row = {'engine': engine.name, 'mode': mode, 'metadata': metadata, 'command': command,
                           'exit': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr,
                           'extension_sha256_before': expected, 'extension_sha256_after': sha(engine.extension),
                           'status': 'failed'}
                    report['results'].append(row)
                    events = [json.loads(line.removeprefix('LOCKTRACE ')) for line in result.stderr.splitlines() if line.startswith('LOCKTRACE ')]
                    row['events'] = sorted(events, key=lambda event: event['sequence'])
                    if not result.returncode:
                        values = json.loads(result.stdout.strip().splitlines()[-1]); row['observations'] = values
                        row['event_sequences_valid'] = sorted(e['sequence'] for e in events) == list(range(1, values['event_count'] + 1))
                        row['admission_order'] = [e['request'] for e in row['events'] if e['event'] == 'server_enter']
                        row['acquisition_order'] = [e['request'] for e in row['events'] if e['event'] == 'acquired']
                        row['response_start_order'] = [e['request'] for e in row['events'] if e['event'] == 'before_response']
                        row['client_receive_order'] = [e['request'] for e in row['events'] if e['event'] == 'client_received']
                        valid = row['event_sequences_valid'] and sorted(values['received']) == [1, 2, 3] and \
                            values['handlers_completed'] == 3 and values['violations'] == 0 and values['holders_after'] == 0 and \
                            expected == row['extension_sha256_after'] and row['client_receive_order'] == values['received']
                        if mode == 'two-first': valid = valid and row['acquisition_order'][0] == 2 and values['received'][0] == 2
                        row['status'] = 'passed' if valid else 'failed'
                    write_report(args.output, report)
        report['passed'] = len(report['results']) == 2 * len(args.engine) and all(row['status'] == 'passed' for row in report['results'])
    except Exception as error:
        report['error'] = str(error)
    write_report(args.output, report)
    print(json.dumps({'passed': report['passed'], 'error': report.get('error'), 'orders': [
        {key: row.get(key) for key in ['engine', 'mode', 'status', 'admission_order', 'acquisition_order', 'client_receive_order']}
        for row in report['results']]}))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
