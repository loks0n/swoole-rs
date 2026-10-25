#!/usr/bin/env python3
"""Inventory and run original MQTT/Redis/SOCKS5 PHPTs with the official runner."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from corpus.upstream.run import COMMIT, prepare, run_cases, save_report
from tools.harness import ROOT, parse_engines

PREFIXES = ['tests/swoole_server/mqtt', 'tests/swoole_redis_server',
            'tests/swoole_client_sync/socks5_proxy.phpt',
            'tests/swoole_http_client_coro/socks5_proxy.phpt',
            'tests/swoole_http_client_coro/socks5_proxy_ipv6.phpt']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--engine', action='append', required=True)
    parser.add_argument('--php', default='php')
    parser.add_argument('--php-extension', action='append', default=[])
    parser.add_argument('--timeout', type=int, default=30)
    parser.add_argument('--composer-autoload', type=Path, help='Explicit private Composer fixture; original test bodies and SKIPIF stay unchanged')
    parser.add_argument('--require-all', action='store_true', help='Also fail on missing dependencies and original skips')
    parser.add_argument('--output', type=Path, default=ROOT / 'target/reports/protocols-phpt.json')
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error('Timeout must be positive')
    show = lambda path: subprocess.check_output(['git', '-C', str(args.source), 'show', f'{COMMIT}:{path}'])
    inventory = subprocess.check_output(['git', '-C', str(args.source), 'ls-tree', '-r', '--name-only', COMMIT, *PREFIXES], text=True).splitlines()
    cases = []
    for path in sorted(p for p in inventory if p.endswith('.phpt')):
        source = show(path)
        dependencies = ['Swoole\\Server']
        if 'swoole_redis_server' in path:
            dependencies += ['Swoole\\Redis\\Server']
        if b'Predis\\Client' in source:
            dependencies += ['Predis\\Client']
        if b'new redis;' in source.lower():
            dependencies += ['Redis']
        cases.append({'path': path, 'sha256': hashlib.sha256(source).hexdigest(),
                      'module': 'mqtt' if '/mqtt/' in path else 'redis' if 'swoole_redis_server' in path else 'socks5',
                      'dependencies': dependencies})
    if not cases:
        parser.error('No original protocol inventory found')
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'upstream_pin': COMMIT,
              'scope': 'Complete original PHPT inventory for the reserved MQTT/Redis/SOCKS5 directories/files. Bodies, SKIPIF, assertions and expected outputs untouched. Missing client dependencies are explicitly unsupported, never passed.',
              'support_adapter': 'corpus/upstream/README.md local helper autoload and remote-object exclusion; optional explicit Composer fixture is appended only to the disposable support autoloader',
              'inventory': cases, 'execution_status': 'running', 'engines': [], 'results': []}
    artifacts = args.output.resolve().with_suffix('').with_name(args.output.stem + '-artifacts')
    save_report(args.output, report)
    try:
        with tempfile.TemporaryDirectory(prefix='swr-protocols-phpt-') as directory:
            sandbox = Path(directory)
            prepare(args.source, sandbox, cases)
            support_autoload = sandbox / 'tests/include/lib/vendor/autoload.php'
            if args.composer_autoload:
                fixture = args.composer_autoload.resolve(strict=True)
                literal = "'" + str(fixture).replace('\\', '\\\\').replace("'", "\\'") + "'"
                with support_autoload.open('a') as handle:
                    handle.write('\nrequire_once ' + literal + ';\n')
                lock = fixture.parent.parent / 'composer.lock'
                report['composer_fixture'] = {'autoload': str(fixture),
                    'packages': [{key: package.get(key) for key in ['name', 'version', 'source', 'dist']}
                                 for package in json.loads(lock.read_text()).get('packages', [])]
                                if lock.is_file() else []}
            (sandbox / 'home').mkdir()
            (sandbox / 'tmp').mkdir()
            classes = sorted({item for case in cases for item in case['dependencies']})
            code = 'require $argv[1];$result=[];foreach(json_decode($argv[2],true) as $class){$result[$class]=class_exists($class);}echo json_encode($result,JSON_THROW_ON_ERROR);'
            for engine in parse_engines(args.engine, args.php, args.php_extension):
                metadata = engine.metadata()
                probe = subprocess.run(engine.command('-r', code, str(sandbox / 'tests/include/bootstrap.php'), json.dumps(classes)), capture_output=True, text=True, timeout=10)
                if probe.returncode or probe.stderr:
                    raise RuntimeError('Dependency probe failed: ' + probe.stderr + probe.stdout)
                dependencies = json.loads(probe.stdout)
                report['engines'].append({**metadata, 'dependency_probe': dependencies})
                for index, case in enumerate(cases):
                    missing = [name for name in case['dependencies'] if not dependencies[name]]
                    if missing:
                        result = {'status': 'unsupported', 'not_run_reason': 'Missing prerequisite: ' + ', '.join(missing),
                                  'missing_dependencies': missing}
                    else:
                        rows, _ = run_cases(engine, [case], sandbox, artifacts / engine.name / str(index), args.timeout, 1)
                        result = rows[case['path']]
                    report['results'].append({'engine': engine.name, **case, **result})
                    print(engine.name, case['path'], result['status'], flush=True)
                    save_report(args.output, report)
            report['execution_status'] = 'complete'
    finally:
        if report['execution_status'] == 'running':
            report['execution_status'] = 'interrupted'
        report['summary'] = dict(Counter(row['status'] for row in report['results']))
        save_report(args.output, report)
    return int(any(row['status'] == 'failed' or args.require_all and row['status'] != 'passed' for row in report['results']))


if __name__ == '__main__':
    sys.exit(main())
