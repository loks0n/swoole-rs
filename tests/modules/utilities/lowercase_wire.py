#!/usr/bin/env python3
"""Supplemental ordinary trailer wire witness; selected source credit requires lowercase_runtime.py."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import uuid

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.harness import parse_engines, run_isolated, write_report
from corpus.upstream.run import prepare


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_wire(source, engines, output):
    work = output.resolve().parent / ('lowercase-wire-' + uuid.uuid4().hex)
    work.mkdir(parents=True)
    prepare(source, work, [])
    fixture = Path(__file__).with_suffix('.php')
    shutil.copy2(fixture, work / fixture.name)
    report = dict(passed=False, work=str(work), scope=__doc__, results=[])
    for engine in engines:
        identity = engine.metadata()
        if not {'http', 'processes', 'php_sockets', 'upstream_test_bootstrap'} <= set(identity['capabilities']):
            raise ValueError('Wire witness requires native PHP sockets, server and original support APIs')
        log = work / (engine.name + '-server.log')
        result = run_isolated(engine.command('-d', 'zend.assertions=1', str(work / fixture.name)),
                              timeout=30, env={**os.environ, 'HOME': str(work), 'TMPDIR': str(work),
                                               'M14_WIRE_SUPPORT': str(work), 'M14_WIRE_LOG': str(log)})
        row = dict(engine=engine.name, identity=identity, exit=result.returncode, stdout=result.stdout,
                   stderr=result.stderr, server_log=log.read_text() if log.exists() else '',
                   extension_sha256_after=sha(identity['extension']), passed=False)
        report['results'].append(row)
        if result.returncode == 0 and not result.stderr and '\tWARNING\t' not in row['server_log'] and row['extension_sha256_after'] == identity['sha256']:
            row['summary'] = json.loads(result.stdout)
            row['passed'] = row['summary']['timed_out'] is False and row['summary']['duplicate_last'] is True
        write_report(output, report)
    report['passed'] = bool(report['results']) and all(row['passed'] for row in report['results'])
    write_report(output, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--engine', action='append', required=True)
    parser.add_argument('--php', default='php')
    parser.add_argument('--php-extension', action='append', default=[])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    engines = parse_engines(args.engine, args.php, args.php_extension)
    if any(engine.metadata()['rust_feature_bits'] for engine in engines):
        raise ValueError('Standalone CLI is a native baseline; use source-bound lowercase_runtime.py for selected qualification')
    report = run_wire(args.source, engines, args.output)
    print(json.dumps(dict(passed=report['passed'], new_rust_qualified=False)))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
