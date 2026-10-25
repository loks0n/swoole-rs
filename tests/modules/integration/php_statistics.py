#!/usr/bin/env python3
"""Compare ordinary read-only Coroutine statistics on source-attested production DSOs."""
import argparse
import json
from pathlib import Path
import sys
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, parse_engines, run_isolated, write_report
from tools.hybrid_identity import attest, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', action='append', required=True)
    parser.add_argument('--php', default='php')
    parser.add_argument('--php-extension', action='append', default=[])
    parser.add_argument('--build-manifest', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--source-ref', required=True)
    parser.add_argument('--selected-export', type=Path, required=True)
    parser.add_argument('--native-export', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    fixture = ROOT / 'tests/modules/phpcoroutines/statistics.php'
    report = dict(passed=False, scope=__doc__, commands=[], engines=[], runtime_scope='Read-only stats only; no Coroutine/Event creation, callbacks or lifecycle execution.',
                  limits=['No deferred/yield/autoload runtime, full original inventory, lifetime, sanitizer or performance claim.'])
    bound = {}
    def run(engine, *arguments):
        command = engine.command(*arguments)
        result = run_isolated(command, timeout=30)
        report['commands'].append(dict(command=command, returncode=result.returncode, stdout=result.stdout, stderr=result.stderr))
        write_report(args.output, report)
        if result.returncode or result.stderr:
            raise ValueError('Actual PHP query failed or warned; first output retained')
        return json.loads(result.stdout)
    try:
        source_ref = subprocess.check_output(['git', 'rev-parse', '--verify', '--end-of-options', args.source_ref + '^{commit}'], cwd=ROOT, text=True).strip()
        exports = {}
        for label, receipt in [('selected', args.selected_export), ('native', args.native_export)]:
            receipt = receipt.resolve(strict=True)
            data = json.loads(receipt.read_text())
            bound[str(receipt)] = sha(receipt)
            for name, item in data['files'].items():
                if Path(name).name != name:
                    raise ValueError('Invalid export member path')
                path = receipt.parent / name
                if sha(path) != item['sha256']:
                    raise ValueError('Export member differs')
                bound[str(path)] = item['sha256']
            if data['source_ref'] != source_ref:
                raise ValueError('Export source differs; pass an exact selected commit')
            exports[receipt.parent / 'swoole.so'] = label
        engines = parse_engines(args.engine, args.php, args.php_extension)
        if len(engines) != 2 or {engine.extension for engine in engines} != set(exports):
            raise ValueError('Require the exact two immutable exported DSOs')
        for engine in engines:
            identity = run(engine, '-r', "echo json_encode(['php'=>PHP_VERSION,'zts'=>PHP_ZTS,'rust_feature_bits'=>defined('SWOOLE_RS_FEATURE_BITS')?SWOOLE_RS_FEATURE_BITS:0]);")
            identity.update(name=engine.name, sha256=sha(engine.extension), extension=str(engine.extension))
            role = exports[engine.extension]
            if role == 'selected':
                report['source_attestation'] = attest(args.build_manifest, args.archive, identity, source_ref, 134217728)
            elif identity['rust_feature_bits']:
                raise ValueError('Native control unexpectedly has Rust features')
            fields = run(engine, str(fixture))
            if not isinstance(fields, list) or len(fields) != 2:
                raise ValueError('Expected two unchanged statistics observations')
            report['engines'].append(dict(role=role, identity=identity, observations=fields))
        if report['engines'][0]['observations'] != report['engines'][1]['observations']:
            raise ValueError('Native and selected ordinary statistics differ')
        if len({(row['identity']['php'], row['identity']['zts']) for row in report['engines']}) != 1:
            raise ValueError('Runtime profiles differ')
        if any(sha(path) != digest for path, digest in bound.items()):
            raise ValueError('Immutable export changed during execution')
        report.update(passed=True)
    except (OSError, ValueError, KeyError) as error:
        report['error'] = str(error)
    write_report(args.output, report)
    print(json.dumps(dict(passed=report['passed'], error=report.get('error'))))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())
