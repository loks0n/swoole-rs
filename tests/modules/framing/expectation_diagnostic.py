#!/usr/bin/env python3
"""Adapted expectation diagnostic, never an untouched original-test gate."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from corpus.upstream.run import COMMIT, prepare, run_cases, save_report
from tools.harness import Engine, parse_engines
from upstream import blob

CASE = 'tests/swoole_server/wrong_eof_setting.phpt'


class BacktraceEngine(Engine):
    def command(self, *args):
        if args and str(args[0]).endswith('run-tests.php'):
            return super().command(args[0], '-d', 'fatal_error_backtraces=On', *args[1:])
        return super().command(*args)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def sections(raw):
    headers = list(re.finditer(rb'^--([A-Z0-9_]+)--\r?\n', raw, re.M))
    return [(m.group(1).decode(), m.group(0), raw[m.end():headers[n+1].start() if n+1 < len(headers) else len(raw)])
            for n, m in enumerate(headers)]


def adapted(raw, version):
    original = sections(raw)
    values = {name: body for name, _, body in original}
    if len(values) != len(original) or not {'FILE', 'SKIPIF', 'EXPECTF', 'EXPECTF_85'} <= values.keys():
        raise ValueError('Unexpected pinned section structure')
    chosen = 'EXPECTF_85' if tuple(map(int, version.split('.')[:2])) >= (8, 5) else 'EXPECTF'
    result = b''.join(b'--EXPECTF--\n' + values[chosen] if name == 'EXPECTF'
                      else header + body for name, header, body in original if name != 'EXPECTF_85')
    after = {name: body for name, _, body in sections(result)}
    if after['FILE'] != values['FILE'] or after['SKIPIF'] != values['SKIPIF'] or after['EXPECTF'] != values[chosen]:
        raise ValueError('Adaptation changed protected body bytes')
    return result, {'selected_section': chosen, 'bodies_preserved': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--engine', action='append', required=True)
    parser.add_argument('--php', default='php')
    parser.add_argument('--php-extension', action='append', default=[])
    parser.add_argument('--runner-fatal-backtraces', action='store_true',
                        help='Explicit PHP8.5 diagnostic runner INI, preserving upstream backtrace expectation')
    parser.add_argument('--official-runner', type=Path,
                        help='Use the matching PHP installation official runner when source is mounted from another host')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raw = blob(args.source, CASE)
    case = {'path': CASE, 'module': 'framing', 'sha256': digest(raw), 'requires': ['upstream_test_bootstrap']}
    report = {'scope': __doc__, 'upstream_commit': COMMIT,
              'official_runner_ini': {'fatal_error_backtraces': 'On'} if args.runner_fatal_backtraces else {},
              'official_runner_override': str(args.official_runner) if args.official_runner else None,
              'engines': [], 'results': [], 'adaptations': {},
              'untouched_original_gate_passed': False, 'full_inventory_passed': False,
              'unselected_original_count': 46, 'passed': False}
    for engine in parse_engines(args.engine, args.php, args.php_extension):
        metadata = engine.metadata()
        if args.runner_fatal_backtraces:
            if tuple(map(int, metadata['php'].split('.')[:2])) < (8, 5):
                raise ValueError('Backtrace diagnostic is only for PHP8.5+')
            engine = BacktraceEngine(engine.name, engine.extension, engine.php, engine.php_extensions)
        report['engines'].append(metadata)
        candidate, proof = adapted(raw, metadata['php'])
        report['adaptations'][engine.name] = proof
        with tempfile.TemporaryDirectory(prefix='swr-expectation-diagnostic-') as directory:
            sandbox = Path(directory)
            prepare(args.source, sandbox, [case])
            if args.official_runner:
                runner = sandbox / 'run-tests.php'
                runner.unlink()
                runner.write_bytes(args.official_runner.read_bytes())
            (sandbox / 'home').mkdir()
            (sandbox / 'tmp').mkdir()
            (sandbox / CASE).write_bytes(candidate)
            artifacts = args.output.resolve().parent / (args.output.stem + '-artifacts') / engine.name
            rows, _ = run_cases(engine, [case], sandbox, artifacts, 45, 1)
            report['results'].append({'engine': engine.name, **rows[CASE]})
            save_report(args.output, report)
    report['passed'] = len(report['results']) == len(report['engines']) and all(r['status'] == 'passed' for r in report['results'])
    save_report(args.output, report)
    print(json.dumps({'diagnostic_passed': report['passed'], 'untouched_original_gate_passed': False,
                      'results': [{'engine': r['engine'], 'status': r['status']} for r in report['results']]}))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
